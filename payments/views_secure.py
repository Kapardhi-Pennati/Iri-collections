"""
SECURE PAYMENT PROCESSING - Stripe integration with security hardening
"""

import json
import logging
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
import stripe

from core.security import audit_log, get_client_ip
from store.models import Order, Transaction

logger = logging.getLogger(__name__)

# Configure Stripe SDK
stripe.api_key = settings.STRIPE_SECRET_KEY


# ─────────────────────────────────────────────────────────────────────────────
# CREATE CHECKOUT SESSION
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_checkout_session(request):
    """
    Create a Stripe Checkout Session for an order.

    Security features:
    ✅ Requires authentication
    ✅ Validates order belongs to user
    ✅ Prevents duplicate payment
    ✅ Amount validation
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
    if order.total_amount <= 0 or order.total_amount > 999999:
        audit_log(
            action="PAYMENT_INVALID_AMOUNT",
            user_id=request.user.id,
            details={"order_id": order_id, "amount": float(order.total_amount)},
            severity="CRITICAL"
        )
        return Response(
            {"error": "Invalid order amount."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # ✅ Build line items from order items
    line_items = []
    for item in order.items.all():
        line_items.append({
            "price_data": {
                "currency": "inr",
                "product_data": {
                    "name": item.product_name,
                },
                "unit_amount": int(item.price_at_purchase * 100),  # Convert to paise
            },
            "quantity": item.quantity,
        })

    # ✅ Add shipping fee as a line item if applicable
    if order.shipping_fee > 0:
        line_items.append({
            "price_data": {
                "currency": "inr",
                "product_data": {
                    "name": "Shipping Fee",
                },
                "unit_amount": int(order.shipping_fee * 100),
            },
            "quantity": 1,
        })

    # ✅ Create Stripe Checkout Session
    try:
        # Build success/cancel URLs from the request origin
        origin = request.META.get("HTTP_ORIGIN", request.build_absolute_uri("/"))
        success_url = f"{origin}/api/payments/success/?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{origin}/orders/"

        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=line_items,
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=str(order.id),
            customer_email=request.user.email,
            metadata={
                "order_id": str(order.id),
                "order_number": order.order_number,
                "user_id": str(request.user.id),
            },
        )
    except stripe.error.StripeError as e:
        logger.error(f"Stripe checkout session creation failed: {str(e)}")
        audit_log(
            action="PAYMENT_STRIPE_ERROR",
            user_id=request.user.id,
            details={"order_id": order_id, "error": str(e)},
            severity="CRITICAL"
        )
        return Response(
            {"error": "Payment gateway error. Please try again later."},
            status=status.HTTP_502_BAD_GATEWAY
        )

    # ✅ Create or update transaction record
    Transaction.objects.update_or_create(
        order=order,
        defaults={
            "stripe_checkout_session_id": checkout_session.id,
            "amount": order.total_amount,
            "status": "created",
        },
    )

    audit_log(
        action="PAYMENT_INITIATED",
        user_id=request.user.id,
        details={
            "order_id": order_id,
            "amount": float(order.total_amount),
            "session_id": checkout_session.id,
        },
        severity="INFO"
    )

    return Response(
        {
            "checkout_url": checkout_session.url,
            "session_id": checkout_session.id,
            "publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
            "order_number": order.order_number,
        },
        status=status.HTTP_200_OK
    )


# ─────────────────────────────────────────────────────────────────────────────
# PAYMENT SUCCESS (redirect landing page)
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def payment_success(request):
    """
    Handle redirect after successful Stripe Checkout.
    Verifies the session and returns order confirmation details.

    Note: The actual payment confirmation happens via the webhook.
    This endpoint is for the frontend redirect only.
    """
    session_id = request.query_params.get("session_id")

    if not session_id:
        return Response(
            {"error": "Session ID required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        # ✅ Retrieve session from Stripe to verify it's real
        session = stripe.checkout.Session.retrieve(session_id)
    except stripe.error.StripeError:
        return Response(
            {"error": "Invalid session."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # ✅ Verify the session belongs to this user
    try:
        transaction = Transaction.objects.get(
            stripe_checkout_session_id=session_id
        )
        if transaction.order.user != request.user:
            return Response(
                {"error": "Access denied."},
                status=status.HTTP_403_FORBIDDEN
            )
    except Transaction.DoesNotExist:
        return Response(
            {"error": "Transaction not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    return Response({
        "message": "Payment completed successfully.",
        "order_number": transaction.order.order_number,
        "status": transaction.order.status,
        "payment_status": session.payment_status,
    })


# ─────────────────────────────────────────────────────────────────────────────
# WEBHOOK (Async Payment Notifications)
# ─────────────────────────────────────────────────────────────────────────────

@csrf_exempt  # ✅ OK: Stripe webhook signature verification replaces CSRF
@api_view(["POST"])
@permission_classes([AllowAny])  # ✅ Async webhook, no user context
def stripe_webhook(request):
    """
    Handle Stripe webhook for payment confirmation.

    Security features:
    ✅ Signature verification (Stripe signing secret)
    ✅ Idempotent (prevents double-processing)
    ✅ Audit logging
    ✅ Error handling

    Stripe sends: Stripe-Signature header with timestamp + HMAC(body, secret)
    """

    # ✅ Extract and verify signature
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    payload = request.body

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        # Invalid payload
        logger.error("Stripe webhook: invalid payload")
        return Response(
            {"error": "Invalid payload."},
            status=status.HTTP_400_BAD_REQUEST
        )
    except stripe.error.SignatureVerificationError:
        audit_log(
            action="WEBHOOK_INVALID_SIGNATURE",
            details={
                "ip": get_client_ip(request),
            },
            severity="CRITICAL"
        )
        logger.error("Invalid webhook signature from Stripe")
        return Response(
            {"error": "Invalid signature."},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        # ✅ Handle checkout.session.completed event
        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            session_id = session["id"]
            payment_intent_id = session.get("payment_intent", "")

            try:
                transaction = Transaction.objects.get(
                    stripe_checkout_session_id=session_id
                )

                # ✅ Idempotent: only process if not already paid
                if transaction.status != "paid":
                    transaction.stripe_payment_intent_id = payment_intent_id
                    transaction.status = "paid"
                    transaction.save()

                    transaction.order.status = "confirmed"
                    transaction.order.save()

                    audit_log(
                        action="WEBHOOK_PAYMENT_COMPLETED",
                        details={
                            "order_id": transaction.order.id,
                            "session_id": session_id,
                            "payment_intent_id": payment_intent_id,
                        },
                        severity="INFO"
                    )

            except Transaction.DoesNotExist:
                logger.warning(
                    f"Webhook received for unknown session: {session_id}"
                )

        # ✅ Handle checkout.session.expired event
        elif event["type"] == "checkout.session.expired":
            session = event["data"]["object"]
            session_id = session["id"]

            try:
                transaction = Transaction.objects.get(
                    stripe_checkout_session_id=session_id
                )
                if transaction.status == "created":
                    transaction.status = "failed"
                    transaction.save()

                    audit_log(
                        action="WEBHOOK_SESSION_EXPIRED",
                        details={"order_id": transaction.order.id},
                        severity="WARNING"
                    )

            except Transaction.DoesNotExist:
                pass

        # ✅ Handle payment_intent.payment_failed event
        elif event["type"] == "payment_intent.payment_failed":
            payment_intent = event["data"]["object"]
            payment_intent_id = payment_intent["id"]

            try:
                transaction = Transaction.objects.get(
                    stripe_payment_intent_id=payment_intent_id
                )
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
            details={"event_type": event["type"]},
            severity="INFO"
        )

    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)}")
        audit_log(
            action="WEBHOOK_PROCESSING_ERROR",
            details={"event_type": event.get("type", "unknown"), "error": str(e)},
            severity="CRITICAL"
        )

    # ✅ Always return 200 OK to acknowledge receipt
    return Response({"status": "ok"}, status=status.HTTP_200_OK)
