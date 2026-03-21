"""
SECURE STORE VIEWS - Production-hardened order and product management
"""

import logging
import socket
import urllib.request
import urllib.error
from urllib.parse import urljoin
import json
from typing import Tuple

from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import transaction
from django.utils.html import escape

from core.security import audit_log, get_client_ip
from core.validators import InputValidator
from core.throttling import PincodeVerifyThrottle

from store.models import Order, Cart, Product, Wishlist
from store.serializers import OrderSerializer, OrderCreateSerializer

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# ORDER CREATION (Secure)
# ─────────────────────────────────────────────────────────────────────────────

class OrderCreateView(APIView):
    """
    Create order from cart with inventory locking.
    
    Security features:
    ✅ User authentication required
    ✅ Input validation with sanitization
    ✅ Database transaction with row locking (prevents race conditions)
    ✅ Stock validation
    ✅ Audit logging
    """
    permission_classes = [IsAuthenticated]
    
    @transaction.atomic
    def post(self, request):
        # ✅ Validate input
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            cart = Cart.objects.prefetch_related("items__product").get(
                user=request.user
            )
        except Cart.DoesNotExist:
            return Response(
                {"error": "Cart is empty or not found."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if cart.items.count() == 0:
            return Response(
                {"error": "Cannot create order from empty cart."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # ✅ Validate shipping address
        address_text = serializer.validated_data["address_text"]
        is_valid, sanitized_address = InputValidator.validate_address(address_text)
        if not is_valid:
            return Response(
                {"error": "Invalid shipping address."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # ✅ Validate phone number
        phone = serializer.validated_data["phone"]
        is_valid, normalized_phone = InputValidator.validate_phone(phone)
        if not is_valid:
            return Response(
                {"error": "Invalid phone number."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            # ✅ CRITICAL: Lock products to prevent stock depletion race condition
            product_ids = [item.product_id for item in cart.items.all()]
            products = Product.objects.select_for_update().filter(id__in=product_ids)
            product_map = {p.id: p for p in products}
            
            # ✅ Validate stock against locked rows
            order_items_data = []
            for item in cart.items.all():
                if item.product.stock <= 0:
                    continue  # Skip out-of-stock items
                
                locked_product = product_map.get(item.product_id)
                if not locked_product or item.quantity > locked_product.stock:
                    audit_log(
                        action="ORDER_INSUFFICIENT_STOCK",
                        user_id=request.user.id,
                        details={
                            "product_id": item.product_id,
                            "product_name": item.product.name,
                            "requested": item.quantity,
                            "available": locked_product.stock if locked_product else 0
                        },
                        severity="WARNING"
                    )
                    return Response(
                        {"error": f"Insufficient stock for {item.product.name}."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                order_items_data.append({
                    "item": item,
                    "product": locked_product
                })
            
            # ✅ Calculate shipping fee
            shipping_fee = _calculate_shipping_fee(sanitized_address)
            final_total = cart.total + shipping_fee
            
            # ✅ Prevent negative/suspicious amounts
            if final_total <= 0 or final_total > 999999:
                audit_log(
                    action="ORDER_INVALID_TOTAL",
                    user_id=request.user.id,
                    details={"total": final_total},
                    severity="CRITICAL"
                )
                return Response(
                    {"error": "Invalid order total."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # ✅ Create order
            order = Order.objects.create(
                user=request.user,
                total_amount=final_total,
                shipping_fee=shipping_fee,
                shipping_address=sanitized_address,  # Sanitized
                phone=normalized_phone,  # Normalized
                notes=escape(serializer.validated_data.get("notes", ""))[:500],  # Escaped & capped
            )
            
            # ✅ Create order items and deduct stock
            for data in order_items_data:
                item = data["item"]
                product = data["product"]
                
                from store.models import OrderItem
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    product_name=product.name,
                    quantity=item.quantity,
                    price_at_purchase=product.price,
                )
                
                product.stock -= item.quantity
                product.save()
            
            # ✅ Clear cart after successful order
            cart.items.all().delete()
            
            audit_log(
                action="ORDER_CREATED",
                user_id=request.user.id,
                details={
                    "order_id": order.id,
                    "order_number": order.order_number,
                    "total": float(order.total_amount),
                    "items_count": len(order_items_data)
                },
                severity="INFO"
            )
        
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


def _calculate_shipping_fee(address: str) -> int:
    """
    Calculate shipping fee based on address.
    
    Security: Simple local calculation, no external API calls
    """
    address_lower = address.lower()
    
    # Chennai metro: Rs. 50
    chennai_indicators = ["chennai", "600", "601", "kanchipuram", "tiruvallur"]
    if any(indicator in address_lower for indicator in chennai_indicators):
        return 50
    
    # Other areas: Rs. 80
    return 80


# ─────────────────────────────────────────────────────────────────────────────
# PINCODE VERIFICATION (Secure with SSRF protection)
# ─────────────────────────────────────────────────────────────────────────────

class PincodeVerifyView(APIView):
    """
    Verify pincode against external postal service.
    
    Security features:
    ✅ Input validation (pincode format)
    ✅ Rate limiting (20 calls/hour per IP)
    ✅ URL validation (SSRF prevention)
    ✅ Request timeout (prevent hanging)
    ✅ Exception handling
    ✅ No sensitive data in errors
    ✅ Whitelisting external domain
    """
    permission_classes = [AllowAny]
    throttle_classes = [PincodeVerifyThrottle]
    
    PINCODE_API_DOMAIN = "api.postalpincode.in"  # Whitelisted external API
    REQUEST_TIMEOUT = 5  # seconds
    
    def post(self, request):
        pincode = request.data.get("pincode", "").strip()
        
        # ✅ Validate pincode format
        is_valid, validated_pincode = InputValidator.validate_pincode(pincode)
        if not is_valid:
            return Response(
                {"error": "Invalid pincode format. Please enter 6 digits."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # ✅ Construct and validate URL (SSRF prevention)
        url = f"https://{self.PINCODE_API_DOMAIN}/pincode/{validated_pincode}"
        if not InputValidator.is_valid_url(url, allowed_domains=[self.PINCODE_API_DOMAIN]):
            audit_log(
                action="PINCODE_VERIFY_SSRF_ATTEMPT",
                details={"url": url, "ip": get_client_ip(request)},
                severity="CRITICAL"
            )
            return Response(
                {"error": "Invalid external service configuration."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        try:
            # ✅ Create request with timeout and User-Agent
            req = urllib.request.Request(
                url,
                headers={
                    'User-Agent': 'Iri-Collections/1.0 (+https://iri-collections.com)',
                    'Accept': 'application/json'
                }
            )
            
            # ✅ Set request timeout to prevent hanging
            with urllib.request.urlopen(req, timeout=self.REQUEST_TIMEOUT) as response:
                data = json.loads(response.read().decode())
            
            # ✅ Validate response structure
            if not isinstance(data, list) or len(data) == 0:
                return Response(
                    {"error": "Invalid pincode."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            result = data[0]
            
            if result.get("Status") != "Success":
                return Response(
                    {"error": "Pincode not found."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            post_offices = result.get("PostOffice", [])
            if not post_offices:
                return Response(
                    {"error": "No postal data available."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            first_office = post_offices[0]
            
            # ✅ Extract and sanitize address components
            district = escape(first_office.get("District", "")).lower()
            state = escape(first_office.get("State", "")).lower()
            
            # ✅ Calculate shipping fee
            shipping_fee = _calculate_shipping_fee(f"{district} {state}")
            
            return Response(
                {
                    "valid": True,
                    "pincode": validated_pincode,
                    "district": first_office.get("District", ""),
                    "state": first_office.get("State", ""),
                    "shipping_fee": shipping_fee,
                }
            )
            
        except urllib.error.URLError as e:
            logger.error(f"Pincode API error: {str(e)}")
            audit_log(
                action="PINCODE_VERIFY_API_ERROR",
                details={"error": str(e)},
                severity="WARNING"
            )
            return Response(
                {"error": "Postal service temporarily unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except socket.timeout:
            logger.error(f"Pincode API timeout for pincode: {validated_pincode}")
            return Response(
                {"error": "Postal service timeout. Please try again."},
                status=status.HTTP_504_GATEWAY_TIMEOUT
            )
        except Exception as e:
            logger.error(f"Unexpected error in pincode verification: {str(e)}")
            audit_log(
                action="PINCODE_VERIFY_ERROR",
                details={"error": str(e)},
                severity="CRITICAL"
            )
            return Response(
                {"error": "An unexpected error occurred."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ─────────────────────────────────────────────────────────────────────────────
# WISHLIST (Secure)
# ─────────────────────────────────────────────────────────────────────────────

class WishlistView(APIView):
    """
    Manage user wishlist (add/remove/list products).
    
    Security: User authentication required, users can only access own wishlist
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Retrieve user's wishlist."""
        wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
        from store.serializers import ProductSerializer
        return Response(ProductSerializer(wishlist.products.all(), many=True).data)
    
    def post(self, request):
        """Add product to wishlist."""
        product_id = request.data.get("product_id")
        
        if not product_id:
            return Response(
                {"error": "Product ID required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            product = Product.objects.get(id=product_id, is_active=True)
        except Product.DoesNotExist:
            return Response(
                {"error": "Product not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
        
        if not wishlist.products.filter(id=product_id).exists():
            wishlist.products.add(product)
            audit_log(
                action="WISHLIST_PRODUCT_ADDED",
                user_id=request.user.id,
                details={"product_id": product_id},
                severity="INFO"
            )
        
        return Response({"message": "Added to wishlist."})
    
    def delete(self, request):
        """Remove product from wishlist."""
        product_id = (
            request.data.get("product_id") or 
            request.query_params.get("product_id")
        )
        
        if not product_id:
            return Response(
                {"error": "Product ID required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return Response(
                {"error": "Product not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
        wishlist.products.remove(product)
        
        audit_log(
            action="WISHLIST_PRODUCT_REMOVED",
            user_id=request.user.id,
            details={"product_id": product_id},
            severity="INFO"
        )
        
        return Response({"message": "Removed from wishlist."})
