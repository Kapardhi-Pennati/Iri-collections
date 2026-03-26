"""
SECURE STORE VIEWS - Production-hardened order and product management
Merged with original application logic for full functionality.
"""

import logging
import socket
import urllib.request
import urllib.error
from urllib.parse import urljoin
import json
from datetime import timedelta
from typing import Tuple

from rest_framework import generics, status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import transaction
from django.db.models import Sum, Count, F
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.utils.html import escape

from core.security import audit_log, get_client_ip
from core.validators import InputValidator
from core.throttling import PincodeVerifyThrottle

from .models import Category, Product, Cart, CartItem, Order, OrderItem, Transaction, Wishlist
from .serializers import (
    CategorySerializer,
    ProductSerializer,
    ProductAdminSerializer,
    CartSerializer,
    CartItemSerializer,
    OrderSerializer,
    OrderCreateSerializer,
)

logger = logging.getLogger(__name__)

# ─── Permission helpers ────────────────────────────────────────
class IsAdminRole(IsAuthenticated):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return request.user.role == "admin" or request.user.is_superuser


# ─── Public: Categories ────────────────────────────────────────
class CategoryListView(generics.ListAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    pagination_class = None


# ─── Public: Products ──────────────────────────────────────────
class ProductListView(generics.ListAPIView):
    serializer_class = ProductSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        qs = Product.objects.filter(is_active=True).select_related("category")
        category = self.request.query_params.get("category")
        search = self.request.query_params.get("search")
        featured = self.request.query_params.get("featured")
        sort = self.request.query_params.get("sort")

        if category:
            qs = qs.filter(category__slug=category)
        if search:
            qs = qs.filter(name__icontains=search)
        if featured:
            qs = qs.filter(is_featured=True)
        if sort == "price_low":
            qs = qs.order_by("price")
        elif sort == "price_high":
            qs = qs.order_by("-price")
        elif sort == "newest":
            qs = qs.order_by("-created_at")
        return qs


class ProductDetailView(generics.RetrieveAPIView):
    queryset = Product.objects.filter(is_active=True).select_related("category")
    serializer_class = ProductSerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"


# ─── Cart ──────────────────────────────────────────────────────
class CartView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        return Response(CartSerializer(cart).data)

    def post(self, request):
        """Add item to cart."""
        cart, _ = Cart.objects.get_or_create(user=request.user)
        product_id = request.data.get("product_id")
        
        try:
            quantity = int(request.data.get("quantity", 1))
        except (ValueError, TypeError):
            return Response({"error": "Invalid quantity."}, status=status.HTTP_400_BAD_REQUEST)

        if quantity <= 0:
            return Response(
                {"error": "Quantity must be at least 1."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            product = Product.objects.get(id=product_id, is_active=True)
        except Product.DoesNotExist:
            return Response(
                {"error": "Product not found."}, status=status.HTTP_404_NOT_FOUND
            )

        if quantity > product.stock:
            return Response(
                {"error": "Not enough stock."}, status=status.HTTP_400_BAD_REQUEST
            )

        item, created = CartItem.objects.get_or_create(cart=cart, product=product)
        if not created:
            item.quantity += quantity
        else:
            item.quantity = quantity
        
        if item.quantity > product.stock:
             return Response(
                {"error": "Total quantity exceeds available stock."}, status=status.HTTP_400_BAD_REQUEST
            )
            
        item.save()
        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)

    def patch(self, request):
        """Update item quantity."""
        cart = Cart.objects.get(user=request.user)
        item_id = request.data.get("item_id")
        try:
            quantity = int(request.data.get("quantity", 1))
        except (ValueError, TypeError):
             return Response({"error": "Invalid quantity."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            item = CartItem.objects.get(id=item_id, cart=cart)
        except CartItem.DoesNotExist:
            return Response(
                {"error": "Item not found in cart."}, status=status.HTTP_404_NOT_FOUND
            )

        if quantity <= 0:
            item.delete()
        else:
            if quantity > item.product.stock:
                return Response(
                    {"error": "Not enough stock."}, status=status.HTTP_400_BAD_REQUEST
                )
            item.quantity = quantity
            item.save()
        return Response(CartSerializer(cart).data)

    def delete(self, request):
        """Remove item from cart or clear cart."""
        cart = Cart.objects.get(user=request.user)
        item_id = request.data.get("item_id") or request.query_params.get("item_id")
        if item_id:
            CartItem.objects.filter(id=item_id, cart=cart).delete()
        else:
            cart.items.all().delete()
        return Response(CartSerializer(cart).data)


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
        # Note: Original used 'shipping_address', Secure uses 'address_text'. 
        # Checking serializer field names from context if possible, but I'll use what's in views_secure.
        address_text = serializer.validated_data.get("address_text") or serializer.validated_data.get("shipping_address")
        if not address_text:
             return Response({"error": "Address is required."}, status=status.HTTP_400_BAD_REQUEST)
             
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
                shipping_address=sanitized_address,  # Sanitized
                phone=normalized_phone,  # Normalized
                notes=escape(serializer.validated_data.get("notes", ""))[:500],  # Escaped & capped
            )
            
            # ✅ Create order items and deduct stock
            for data in order_items_data:
                item = data["item"]
                product = data["product"]
                
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
    """
    address_lower = address.lower()
    chennai_indicators = ["chennai", "600", "601", "kanchipuram", "tiruvallur"]
    if any(indicator in address_lower for indicator in chennai_indicators):
        return 50
    return 80


# ─────────────────────────────────────────────────────────────────────────────
# PINCODE VERIFICATION (Secure with SSRF protection)
# ─────────────────────────────────────────────────────────────────────────────

class PincodeVerifyView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PincodeVerifyThrottle]
    
    PINCODE_API_DOMAIN = "api.postalpincode.in"
    REQUEST_TIMEOUT = 5
    
    def post(self, request):
        pincode = str(request.data.get("pincode", "")).strip()
        
        is_valid, validated_pincode = InputValidator.validate_pincode(pincode)
        if not is_valid:
            return Response(
                {"error": "Invalid pincode format. Please enter 6 digits."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        url = f"https://{self.PINCODE_API_DOMAIN}/pincode/{validated_pincode}"
        if not InputValidator.is_valid_url(url, allowed_domains=[self.PINCODE_API_DOMAIN]):
            return Response(
                {"error": "Invalid external service configuration."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        try:
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'Iri-Collections/1.0', 'Accept': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=self.REQUEST_TIMEOUT) as response:
                data = json.loads(response.read().decode())
            
            if not isinstance(data, list) or len(data) == 0:
                return Response({"error": "Invalid pincode."}, status=status.HTTP_400_BAD_REQUEST)
            
            result = data[0]
            if result.get("Status") != "Success":
                 return Response({"error": "Pincode not found."}, status=status.HTTP_400_BAD_REQUEST)
            
            post_offices = result.get("PostOffice", [])
            if not post_offices:
                return Response({"error": "No data found."}, status=status.HTTP_400_BAD_REQUEST)
            
            first_office = post_offices[0]
            district = escape(first_office.get("District", "")).lower()
            state = escape(first_office.get("State", "")).lower()
            shipping_fee = _calculate_shipping_fee(f"{district} {state}")
            
            return Response({
                "valid": True,
                "pincode": validated_pincode,
                "district": first_office.get("District", ""),
                "state": first_office.get("State", ""),
                "shipping_fee": shipping_fee,
            })
        except Exception as e:
            logger.error(f"Pincode verify error: {str(e)}")
            return Response({"error": "Service unavailable."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


# ─── Wishlist (Secure) ──────────────────────────────────────────
class WishlistView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
        return Response(ProductSerializer(wishlist.products.filter(is_active=True), many=True).data)
    
    def post(self, request):
        product_id = request.data.get("product_id")
        try:
            product_id = int(product_id)
        except (TypeError, ValueError):
            return Response({"error": "Invalid product ID."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            product = Product.objects.get(id=product_id, is_active=True)
            wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
            wishlist.products.add(product)
            audit_log(
                action="WISHLIST_ADD",
                user_id=request.user.id,
                details={"product_id": product_id},
                severity="INFO"
            )
            return Response({"message": "Added to wishlist."})
        except Product.DoesNotExist:
            return Response({"error": "Product not found."}, status=status.HTTP_404_NOT_FOUND)
    
    def delete(self, request):
        product_id = request.data.get("product_id") or request.query_params.get("product_id")
        try:
            product_id = int(product_id)
        except (TypeError, ValueError):
            return Response({"error": "Invalid product ID."}, status=status.HTTP_400_BAD_REQUEST)
        wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
        wishlist.products.remove(product_id)
        audit_log(
            action="WISHLIST_REMOVE",
            user_id=request.user.id,
            details={"product_id": product_id},
            severity="INFO"
        )
        return Response({"message": "Removed from wishlist."})


class WishlistToggleView(APIView):
    """
    Toggle a product in/out of the user's wishlist.
    Returns {"added": true/false} so the frontend can update the UI.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        product_id = request.data.get("product_id")
        try:
            product_id = int(product_id)
        except (TypeError, ValueError):
            return Response({"error": "Invalid product ID."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            product = Product.objects.get(id=product_id, is_active=True)
        except Product.DoesNotExist:
            return Response({"error": "Product not found."}, status=status.HTTP_404_NOT_FOUND)

        wishlist, _ = Wishlist.objects.get_or_create(user=request.user)

        if wishlist.products.filter(id=product.id).exists():
            wishlist.products.remove(product)
            audit_log(
                action="WISHLIST_TOGGLE_REMOVE",
                user_id=request.user.id,
                details={"product_id": product_id},
                severity="INFO"
            )
            return Response({"added": False, "message": "Removed from wishlist."})
        else:
            wishlist.products.add(product)
            audit_log(
                action="WISHLIST_TOGGLE_ADD",
                user_id=request.user.id,
                details={"product_id": product_id},
                severity="INFO"
            )
            return Response({"added": True, "message": "Added to wishlist."})


# ─── Orders List & Detail ──────────────────────────────────────
class OrderListView(generics.ListAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related(
            "items", "transaction"
        )


class OrderDetailView(generics.RetrieveAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.role == "admin":
            return Order.objects.all().prefetch_related("items", "transaction")
        return Order.objects.filter(user=self.request.user).prefetch_related(
            "items", "transaction"
        )


class CancelOrderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            order = Order.objects.get(pk=pk, user=request.user)
            if order.status not in ["pending", "confirmed"]:
                return Response({"error": "Order cannot be cancelled at this stage."}, status=status.HTTP_400_BAD_REQUEST)
            order.status = "cancelled"
            order.save()
            return Response({"message": "Order cancelled successfully."})
        except Order.DoesNotExist:
            return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)


# ─── Admin: Products CRUD ──────────────────────────────────────
class AdminProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all().select_related("category")
    serializer_class = ProductAdminSerializer
    permission_classes = [IsAdminRole]

    def get_serializer_class(self):
        if self.action in ("list", "retrieve"):
            return ProductSerializer
        return ProductAdminSerializer


class AdminCategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminRole]


# ─── Admin: Orders & Analytics ────────────────────────────────
class AdminOrderListView(generics.ListAPIView):
    queryset = Order.objects.all().prefetch_related("items", "transaction").select_related("user")
    serializer_class = OrderSerializer
    permission_classes = [IsAdminRole]


class AdminOrderDetailView(generics.RetrieveDestroyAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [IsAdminRole]


class AdminOrderStatusView(APIView):
    permission_classes = [IsAdminRole]

    def patch(self, request, pk):
        try:
            order = Order.objects.get(pk=pk)
            new_status = request.data.get("status")
            order.status = new_status
            order.save()
            return Response(OrderSerializer(order).data)
        except Order.DoesNotExist:
            return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)


class AdminOrderTrackingUploadView(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request, pk):
        try:
            order = Order.objects.get(pk=pk)
            image = request.FILES.get("tracking_image")
            if not image:
                return Response({"error": "tracking_image is required."}, status=status.HTTP_400_BAD_REQUEST)
            order.tracking_image = image
            order.save()
            return Response({"message": "Tracking image uploaded."})
        except Order.DoesNotExist:
            return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)


class AdminAnalyticsView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)
        total_revenue = Order.objects.filter(status__in=["confirmed", "shipped", "delivered"]).aggregate(total=Sum("total_amount"))["total"] or 0
        total_orders = Order.objects.count()
        pending_orders = Order.objects.filter(status="pending").count()
        total_products = Product.objects.filter(is_active=True).count()
        low_stock = Product.objects.filter(stock__lte=5, is_active=True).count()

        return Response({
            "total_revenue": float(total_revenue),
            "total_orders": total_orders,
            "pending_orders": pending_orders,
            "total_products": total_products,
            "low_stock_products": low_stock,
        })
