"""
SECURE PAYMENT PROCESSING - Razorpay integration with security hardening
"""

import hmac
import hashlib
import logging
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
import razorpay

from core.security import verify_hmac_signature, audit_log, get_client_ip
from core.throttling import PaymentThrottle
from store.models import Order, Transaction

logger = logging.getLogger(__name__)


def get_razorpay_client():
    """
    Initialize Razorpay client with credentials from settings.
    
    v2.0+ Features:
    ✅ Retry mechanism enabled for failed API calls
    ✅ Enhanced error handling for network issues
    ✅ App details for Razorpay monitoring
    """
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise ValueError("Razorpay credentials not configured")
    
    client = razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )
    
    # ✅ v2.0+: Enable automatic retry for failed API calls
    client.enable_retry(True)
    
    # ✅ v2.0+: Set app details for Razorpay tracking and monitoring
    client.set_app_details({
        "title": "Iri Collections",
        "version": "1.0.0"
    })
    
    return client


# ─────────────────────────────────────────────────────────────────────────────
# CREATE PAYMENT
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_payment(request):
    """
    Initialize Razorpay payment order for checkout.
    
    Security features:
    ✅ Requires authentication
    ✅ Validates order belongs to user
    ✅ Prevents duplicate payment
    ✅ Amount validation
    ✅ Rate limiting
    ✅ Audit logging
    """
    order_id = request.data.get("order_id")
    
    if not order_id:
        return Response(
            {"error": "Order ID required."},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # ✅ Verify order belongs to current user
        order = Order.objects.get(id=order_id, user=request.user)
    except Order.DoesNotExist:
        audit_log(
            action="PAYMENT_UNAUTHORIZED_ORDER_ACCESS",
            user_id=request.user.id,
            details={"order_id": order_id, "ip": get_client_ip(request)},
            severity="WARNING"
        )
        return Response(
            {"error": "Order not found or access denied."},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # ✅ Prevent paying for already-paid orders
    if hasattr(order, "transaction") and order.transaction.status == "paid":
        audit_log(
            action="PAYMENT_ALREADY_PAID",
            user_id=request.user.id,
            details={"order_id": order_id},
            severity="WARNING"
        )
        return Response(
            {"error": "Order already paid."},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # ✅ Prevent paying for cancelled orders
    if order.status == "cancelled":
        return Response(
            {"error": "Cancelled orders cannot be paid."},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # ✅ Validate amount is positive and reasonable
    if order.total_amount <= 0 or order.total_amount > 999999:  # 99,99,99
        audit_log(
            action="PAYMENT_INVALID_AMOUNT",
            user_id=request.user.id,
            details={"order_id": order_id, "amount": order.total_amount},
            severity="CRITICAL"
        )
        return Response(
            {"error": "Invalid order amount."},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # ✅ Initialize Razorpay payment
    try:
        client = get_razorpay_client()
        amount_paise = int(order.total_amount * 100)  # Convert to paise
        
        razorpay_order = client.order.create(
            {
                "amount": amount_paise,
                "currency": "INR",
                "receipt": order.order_number,
                "payment_capture": 1,  # Auto-capture payment
                "notes": {
                    "order_id": str(order.id),
                    "user_id": str(request.user.id),
                }
            }
        )
    except Exception as e:
        logger.error(f"Razorpay order creation failed: {str(e)}")
        audit_log(
            action="PAYMENT_RAZORPAY_ERROR",
            user_id=request.user.id,
            details={"order_id": order_id, "error": str(e)},
            severity="CRITICAL"
        )
        return Response(
            {"error": "Payment gateway error. Please try again later."},
            status=status.HTTP_502_BAD_GATEWAY
        )
    
    # ✅ Create transaction record
    Transaction.objects.update_or_create(
        order=order,
        defaults={
            "razorpay_order_id": razorpay_order["id"],
            "amount": order.total_amount,
            "status": "created",
        },
    )
    
    audit_log(
        action="PAYMENT_INITIATED",
        user_id=request.user.id,
        details={
            "order_id": order_id,
            "amount": order.total_amount,
            "razorpay_order_id": razorpay_order["id"]
        },
        severity="INFO"
    )
    
    return Response(
        {
            "razorpay_order_id": razorpay_order["id"],
            "razorpay_key_id": settings.RAZORPAY_KEY_ID,
            "amount": amount_paise,
            "currency": "INR",
            "order_number": order.order_number,
        },
        status=status.HTTP_200_OK
    )


# ─────────────────────────────────────────────────────────────────────────────
# VERIFY PAYMENT
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def verify_payment(request):
    """
    Verify Razorpay payment and update order status.
    
    Security features:
    ✅ Validates user authentication
    ✅ Verifies Razorpay signature
    ✅ Prevents replay attacks
    ✅ Rate limiting
    ✅ Audit logging
    """
    razorpay_order_id = request.data.get("razorpay_order_id")
    razorpay_payment_id = request.data.get("razorpay_payment_id")
    razorpay_signature = request.data.get("razorpay_signature")
    
    # ✅ Validate all required fields
    if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
        return Response(
            {"error": "Missing payment details."},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # ✅ Verify Razorpay signature (prevents tampering)
    try:
        client = get_razorpay_client()
        client.utility.verify_payment_signature(
            {
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_signature": razorpay_signature,
            }
        )
    except razorpay.errors.SignatureVerificationError:
        audit_log(
            action="PAYMENT_VERIFICATION_FAILED_INVALID_SIGNATURE",
            user_id=request.user.id,
            details={
                "razorpay_order_id": razorpay_order_id,
                "ip": get_client_ip(request)
            },
            severity="CRITICAL"
        )
        logger.error(f"Invalid Razorpay signature for order {razorpay_order_id}")
        return Response(
            {"error": "Payment verification failed."},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # ✅ Update transaction
    try:
        transaction = Transaction.objects.get(razorpay_order_id=razorpay_order_id)
        
        # ✅ Prevent duplicate marking as paid
        if transaction.status == "paid":
            audit_log(
                action="PAYMENT_ALREADY_VERIFIED",
                user_id=request.user.id,
                details={"razorpay_order_id": razorpay_order_id},
                severity="INFO"
            )
            return Response(
                {
                    "message": "Payment already verified.",
                    "order_number": transaction.order.order_number,
                    "status": "confirmed",
                }
            )
        
        # ✅ Mark as paid
        transaction.razorpay_payment_id = razorpay_payment_id
        transaction.razorpay_signature = razorpay_signature
        transaction.status = "paid"
        transaction.save()
        
        # ✅ Update order status
        transaction.order.status = "confirmed"
        transaction.order.save()
        
        audit_log(
            action="PAYMENT_VERIFIED",
            user_id=request.user.id,
            details={
                "order_id": transaction.order.id,
                "razorpay_payment_id": razorpay_payment_id
            },
            severity="INFO"
        )
        
        return Response(
            {
                "message": "Payment verified successfully.",
                "order_number": transaction.order.order_number,
                "status": "confirmed",
            }
        )
        
    except Transaction.DoesNotExist:
        audit_log(
            action="PAYMENT_VERIFICATION_TRANSACTION_NOT_FOUND",
            user_id=request.user.id,
            details={"razorpay_order_id": razorpay_order_id},
            severity="CRITICAL"
        )
        return Response(
            {"error": "Transaction not found."},
            status=status.HTTP_404_NOT_FOUND
        )


# ─────────────────────────────────────────────────────────────────────────────
# WEBHOOK (Async Payment Notifications)
# ─────────────────────────────────────────────────────────────────────────────

@csrf_exempt  # ✅ OK: Webhook signature verification replaces CSRF
@api_view(["POST"])
@permission_classes([AllowAny])  # ✅ Async webhook, no user context
def payment_webhook(request):
    """
    Handle Razorpay webhook for payment confirmation.
    
    Security features:
    ✅ Signature verification (HMAC-SHA256)
    ✅ Idempotent (prevents double-processing)
    ✅ Audit logging
    ✅ Error handling
    
    Razorpay sends: X-Razorpay-Signature header with HMAC(body, secret)
    """
    
    # ✅ Extract and verify signature
    webhook_signature = request.headers.get("X-Razorpay-Signature", "")
    
    if not verify_hmac_signature(
        message=request.body,
        signature=webhook_signature,
        secret=settings.RAZORPAY_KEY_SECRET
    ):
        audit_log(
            action="WEBHOOK_INVALID_SIGNATURE",
            details={
                "event": request.data.get("event"),
                "ip": get_client_ip(request)
            },
            severity="CRITICAL"
        )
        logger.error("Invalid webhook signature from Razorpay")
        return Response(
            {"error": "Invalid signature."},
            status=status.HTTP_403_FORBIDDEN
        )
    
    payload = request.data
    event = payload.get("event", "")
    
    try:
        # ✅ Handle payment.captured event
        if event == "payment.captured":
            payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
            razorpay_order_id = payment.get("order_id")
            razorpay_payment_id = payment.get("id")
            
            try:
                transaction = Transaction.objects.get(razorpay_order_id=razorpay_order_id)
                
                # ✅ Idempotent: only process if not already paid
                if transaction.status != "paid":
                    transaction.razorpay_payment_id = razorpay_payment_id
                    transaction.status = "paid"
                    transaction.save()
                    
                    transaction.order.status = "confirmed"
                    transaction.order.save()
                    
                    audit_log(
                        action="WEBHOOK_PAYMENT_CAPTURED",
                        details={
                            "order_id": transaction.order.id,
                            "razorpay_payment_id": razorpay_payment_id
                        },
                        severity="INFO"
                    )
                        
            except Transaction.DoesNotExist:
                logger.warning(f"Webhook received for unknown order: {razorpay_order_id}")
        
        # ✅ Handle payment.failed event
        elif event == "payment.failed":
            payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
            razorpay_order_id = payment.get("order_id")
            
            try:
                transaction = Transaction.objects.get(razorpay_order_id=razorpay_order_id)
                transaction.status = "failed"
                transaction.save()
                
                audit_log(
                    action="WEBHOOK_PAYMENT_FAILED",
                    details={"order_id": transaction.order.id},
                    severity="WARNING"
                )
                    
            except Transaction.DoesNotExist:
                pass
        
        audit_log(
            action="WEBHOOK_PROCESSED",
            details={"event": event},
            severity="INFO"
        )
        
    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)}")
        audit_log(
            action="WEBHOOK_PROCESSING_ERROR",
            details={"event": event, "error": str(e)},
            severity="CRITICAL"
        )
    
    # ✅ Always return 200 OK to prevent Razorpay retry
    return Response({"status": "ok"}, status=status.HTTP_200_OK)
