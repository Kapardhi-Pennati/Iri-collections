from rest_framework import generics, status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import transaction
from django.db.models import Sum, Count, F
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import timedelta
import urllib.request
import json

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
        quantity = int(request.data.get("quantity", 1))

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
        item.save()
        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)

    def patch(self, request):
        """Update item quantity."""
        cart = Cart.objects.get(user=request.user)
        item_id = request.data.get("item_id")
        quantity = int(request.data.get("quantity", 1))

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


# ─── Orders ────────────────────────────────────────────────────
class OrderCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            cart = Cart.objects.prefetch_related("items__product").get(
                user=request.user
            )
        except Cart.DoesNotExist:
            return Response(
                {"error": "Cart is empty."}, status=status.HTTP_400_BAD_REQUEST
            )

        if cart.items.count() == 0:
            return Response(
                {"error": "Cart is empty."}, status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            # Lock the products to prevent concurrent stock depletion (Race Condition Fix)
            product_ids = [item.product_id for item in cart.items.all()]
            products = Product.objects.select_for_update().filter(id__in=product_ids)
            product_map = {p.id: p for p in products}

            # Validate stock against locked rows
            for item in cart.items.all():
                # NOTE: We allow out_of_stock items to exist in cart but ignore them in Order (handled below via continue)
                if item.product.stock <= 0:
                    continue

                locked_product = product_map.get(item.product_id)
                if not locked_product or item.quantity > locked_product.stock:
                    return Response(
                        {"error": f"Not enough stock for {item.product.name}."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            
            address_text = serializer.validated_data["shipping_address"]

            # Calculate shipping fee for Chennai vs others
            is_chennai = "chennai" in address_text.lower() or "600" in address_text or "601" in address_text
            shipping_fee = 50 if is_chennai else 80
            final_total = cart.total + shipping_fee

            # Create order
            order = Order.objects.create(
                user=request.user,
                total_amount=final_total,
                shipping_address=address_text,
                phone=serializer.validated_data["phone"],
                notes=serializer.validated_data.get("notes", ""),
            )

            # Create order items and reduce stock
            for item in cart.items.all():
                if item.product.stock <= 0:
                    continue  # Ignore out of stock at creation
                locked_product = product_map[item.product_id]
                OrderItem.objects.create(
                    order=order,
                    product=locked_product,
                    product_name=locked_product.name,
                    quantity=item.quantity,
                    price_at_purchase=locked_product.price,
                )
                locked_product.stock -= item.quantity
                locked_product.save()

            # Clear cart
            cart.items.all().delete()

        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

class PincodeVerifyView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        pincode = request.data.get("pincode")
        if not pincode:
            return Response({"error": "Pincode is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            url = f"https://api.postalpincode.in/pincode/{pincode}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
                
                if data and isinstance(data, list):
                    result = data[0]
                    if result.get("Status") == "Success":
                        post_offices = result.get("PostOffice", [])
                        if not post_offices:
                            return Response({"error": "No details found for this pincode."}, status=status.HTTP_400_BAD_REQUEST)
                        
                        first_office = post_offices[0]
                        city_district = first_office.get("District", "").lower()
                        state = first_office.get("State", "").lower()
                        
                        # Calculate shipping fee: 50 for Chennai, 80 else
                        is_chennai = "chennai" in city_district or "kanchipuram" in city_district or "tiruvallur" in city_district or str(pincode).startswith("600") or str(pincode).startswith("601")
                        shipping_fee = 50 if is_chennai else 80
                        
                        return Response({
                            "valid": True,
                            "pincode": pincode,
                            "district": first_office.get("District"),
                            "state": first_office.get("State"),
                            "shipping_fee": shipping_fee
                        })
                    else:
                        return Response({"error": "Invalid pincode."}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": "Failed to verify pincode. Service might be down."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class WishlistView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
        return Response(ProductSerializer(wishlist.products.all(), many=True).data)

    def post(self, request):
        wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
        product_id = request.data.get("product_id")
        try:
            product = Product.objects.get(id=product_id, is_active=True)
            wishlist.products.add(product)
            return Response({"message": "Added to wishlist"})
        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request):
        wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
        product_id = request.data.get("product_id") or request.query_params.get("product_id")
        try:
            product = Product.objects.get(id=product_id)
            wishlist.products.remove(product)
            return Response({"message": "Removed from wishlist"})
        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

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
            return Response({"message": "Order cancelled successfully.", "order": OrderSerializer(order).data})
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


# ─── Admin: Order Status ───────────────────────────────────────
class AdminOrderListView(generics.ListAPIView):
    queryset = (
        Order.objects.all()
        .prefetch_related("items", "transaction")
        .select_related("user")
    )
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
        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND
            )

        new_status = request.data.get("status")
        valid = [c[0] for c in Order.STATUS_CHOICES]
        if new_status not in valid:
            return Response(
                {"error": f"Invalid status. Choose from: {valid}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.status = new_status
        order.save()
        return Response(OrderSerializer(order).data)


class AdminOrderTrackingUploadView(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request, pk):
        try:
            order = Order.objects.get(pk=pk)
            image = request.FILES.get("tracking_image")
            if not image:
                return Response({"error": "tracking_image is required."}, status=status.HTTP_400_BAD_REQUEST)
            if order.status != "shipped":
                return Response({"error": "Order must be 'shipped' before uploading tracking image."}, status=status.HTTP_400_BAD_REQUEST)
            
            order.tracking_image = image
            order.save() # Custom save logic automatically shifts to 'delivered'
            return Response({
                "message": "Tracking image uploaded successfully. Order moved to delivered.",
                "order": OrderSerializer(order).data
            })
        except Order.DoesNotExist:
            return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)


# ─── Admin: Analytics ──────────────────────────────────────────
class AdminAnalyticsView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)

        total_revenue = (
            Order.objects.filter(
                status__in=["confirmed", "shipped", "delivered"]
            ).aggregate(total=Sum("total_amount"))["total"]
            or 0
        )

        total_orders = Order.objects.count()
        pending_orders = Order.objects.filter(status="pending").count()
        total_products = Product.objects.filter(is_active=True).count()
        low_stock = Product.objects.filter(stock__lte=5, is_active=True).count()

        # Daily revenue for last 30 days
        daily_revenue = (
            Order.objects.filter(
                created_at__gte=thirty_days_ago,
                status__in=["confirmed", "shipped", "delivered"],
            )
            .annotate(date=TruncDate("created_at"))
            .values("date")
            .annotate(revenue=Sum("total_amount"), count=Count("id"))
            .order_by("date")
        )

        # Top products
        top_products = (
            OrderItem.objects.values("product_name")
            .annotate(
                total_sold=Sum("quantity"),
                total_revenue=Sum(F("price_at_purchase") * F("quantity")),
            )
            .order_by("-total_sold")[:5]
        )

        # Orders by status
        status_breakdown = (
            Order.objects.values("status")
            .annotate(count=Count("id"))
            .order_by("status")
        )

        return Response(
            {
                "total_revenue": float(total_revenue),
                "total_orders": total_orders,
                "pending_orders": pending_orders,
                "total_products": total_products,
                "low_stock_products": low_stock,
                "daily_revenue": list(daily_revenue),
                "top_products": list(top_products),
                "status_breakdown": list(status_breakdown),
            }
        )
