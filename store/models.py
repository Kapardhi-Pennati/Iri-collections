import uuid
from django.db import models
from django.conf import settings
from django.utils.text import slugify
from django.core.mail import send_mail


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="categories/", blank=True, null=True)

    class Meta:
        db_table = "categories"
        verbose_name_plural = "Categories"
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    compare_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    stock = models.PositiveIntegerField(default=0)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="products"
    )
    image = models.ImageField(upload_to="products/", blank=True, null=True)
    image_url = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    material = models.CharField(max_length=100, blank=True)
    weight = models.CharField(max_length=50, blank=True, help_text="e.g. 5.2g")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "products"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(price__gte=0), name="product_price_positive"
            ),
            models.CheckConstraint(
                check=models.Q(stock__gte=0), name="product_stock_positive"
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while Product.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @property
    def in_stock(self):
        return self.stock > 0

    @property
    def display_image(self):
        if self.image:
            return self.image.url
        return self.image_url or ""


class Cart(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "carts"

    def __str__(self):
        return f"Cart of {self.user.email}"

    @property
    def total(self):
        return sum(item.subtotal for item in self.items.all())

    @property
    def item_count(self):
        return sum(item.quantity for item in self.items.all() if item.product.stock > 0)


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "cart_items"
        unique_together = ("cart", "product")
        constraints = [
            models.CheckConstraint(
                check=models.Q(quantity__gt=0), name="cartitem_quantity_positive"
            )
        ]

    def __str__(self):
        return f"{self.quantity}x {self.product.name}"

    @property
    def subtotal(self):
        if self.product.stock <= 0:
            return 0
        return self.product.price * self.quantity


class Order(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("shipped", "Shipped"),
        ("delivered", "Delivered"),
        ("cancelled", "Cancelled"),
    )
    order_number = models.CharField(max_length=20, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="orders"
    )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    shipping_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default="pending", db_index=True
    )
    shipping_address = models.TextField()
    phone = models.CharField(max_length=15, blank=True)
    notes = models.TextField(blank=True)
    tracking_image = models.ImageField(upload_to="tracking/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "orders"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(total_amount__gte=0), name="order_total_positive"
            )
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_status = self.status

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = f"IRI-{uuid.uuid4().hex[:8].upper()}"

        # If image uploaded while shipped -> move to delivered
        if self.status == "shipped" and self.tracking_image and not getattr(self, "_delivering", False):
            self.status = "delivered"
            self._delivering = True

        super().save(*args, **kwargs)

        # Triggers email if status changed (except delivered)
        if self.pk and getattr(self, "_original_status", self.status) != self.status:
            if self.status != "delivered":
                try:
                    subject = f"Order {self.order_number} Status Update"
                    message = f"Hello {self.user.username},\n\nYour order {self.order_number} status is now: {self.status.upper()}.\n\nThank you for shopping with us!"
                    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [self.user.email], fail_silently=True)
                except Exception:
                    pass
            
            # Auto refund email if cancelled
            if self.status == "cancelled":
                try:
                    subject = f"Order {self.order_number} Cancelled & Refund Initiated"
                    message = f"Hello {self.user.username},\n\nYour order {self.order_number} has been cancelled. If any payment was deducted, a refund has been initiated to your original payment method.\n\nThank you."
                    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [self.user.email], fail_silently=True)
                except Exception:
                    pass

            self._original_status = self.status

    def __str__(self):
        return self.order_number


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    product_name = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField()
    price_at_purchase = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = "order_items"
        constraints = [
            models.CheckConstraint(
                check=models.Q(quantity__gt=0), name="orderitem_quantity_positive"
            ),
            models.CheckConstraint(
                check=models.Q(price_at_purchase__gte=0),
                name="orderitem_price_positive",
            ),
        ]

    def __str__(self):
        return f"{self.quantity}x {self.product_name}"

    @property
    def subtotal(self):
        return self.price_at_purchase * self.quantity


class Transaction(models.Model):
    STATUS_CHOICES = (
        ("created", "Created"),
        ("paid", "Paid"),
        ("failed", "Failed"),
    )
    order = models.OneToOneField(
        Order, on_delete=models.CASCADE, related_name="transaction"
    )
    stripe_checkout_session_id = models.CharField(max_length=255, blank=True, db_index=True)
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default="created", db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Cancel order automatically if payment failed
        if self.status == "failed" and self.order.status != "cancelled":
            self.order.status = "cancelled"
            self.order.save()

    def __str__(self):
        return f"Txn {self.stripe_checkout_session_id} - {self.status}"


class Wishlist(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist"
    )
    products = models.ManyToManyField(Product, related_name="wishlisted_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "wishlists"

    def __str__(self):
        return f"Wishlist of {self.user.email}"
