import hmac
import hashlib
import razorpay
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from store.models import Order, Transaction


def get_razorpay_client():
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_payment(request):
    """Create a Razorpay order for a given internal order."""
    order_id = request.data.get('order_id')
    try:
        order = Order.objects.get(id=order_id, user=request.user)
    except Order.DoesNotExist:
        return Response({'error': 'Order not found.'}, status=status.HTTP_404_NOT_FOUND)

    # Check if transaction already exists
    if hasattr(order, 'transaction') and order.transaction.status == 'paid':
        return Response({'error': 'Order already paid.'}, status=status.HTTP_400_BAD_REQUEST)

    amount_paise = int(order.total_amount * 100)

    try:
        client = get_razorpay_client()
        razorpay_order = client.order.create({
            'amount': amount_paise,
            'currency': 'INR',
            'receipt': order.order_number,
            'payment_capture': 1,
        })
    except Exception as e:
        return Response({'error': f'Payment gateway error: {str(e)}'}, status=status.HTTP_502_BAD_GATEWAY)

    # Create or update transaction
    transaction, _ = Transaction.objects.update_or_create(
        order=order,
        defaults={
            'razorpay_order_id': razorpay_order['id'],
            'amount': order.total_amount,
            'status': 'created',
        }
    )

    return Response({
        'razorpay_order_id': razorpay_order['id'],
        'razorpay_key_id': settings.RAZORPAY_KEY_ID,
        'amount': amount_paise,
        'currency': 'INR',
        'order_number': order.order_number,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def verify_payment(request):
    """Verify payment signature from client-side callback."""
    razorpay_order_id = request.data.get('razorpay_order_id')
    razorpay_payment_id = request.data.get('razorpay_payment_id')
    razorpay_signature = request.data.get('razorpay_signature')

    if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
        return Response({'error': 'Missing payment details.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        client = get_razorpay_client()
        client.utility.verify_payment_signature({
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature,
        })
    except razorpay.errors.SignatureVerificationError:
        return Response({'error': 'Payment verification failed.'}, status=status.HTTP_400_BAD_REQUEST)

    # Update transaction
    try:
        transaction = Transaction.objects.get(razorpay_order_id=razorpay_order_id)
        transaction.razorpay_payment_id = razorpay_payment_id
        transaction.razorpay_signature = razorpay_signature
        transaction.status = 'paid'
        transaction.save()

        # Update order status
        transaction.order.status = 'confirmed'
        transaction.order.save()

        return Response({
            'message': 'Payment verified successfully.',
            'order_number': transaction.order.order_number,
            'status': 'confirmed',
        })
    except Transaction.DoesNotExist:
        return Response({'error': 'Transaction not found.'}, status=status.HTTP_404_NOT_FOUND)


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def payment_webhook(request):
    """Handle Razorpay webhook for async payment confirmation.
    Verified via Razorpay signature in webhook header."""
    webhook_secret = settings.RAZORPAY_KEY_SECRET
    webhook_signature = request.headers.get('X-Razorpay-Signature', '')

    # Verify webhook signature
    expected_signature = hmac.new(
        key=webhook_secret.encode('utf-8'),
        msg=request.body,
        digestmod=hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, webhook_signature):
        return Response({'error': 'Invalid signature.'}, status=status.HTTP_400_BAD_REQUEST)

    payload = request.data
    event = payload.get('event', '')

    if event == 'payment.captured':
        payment_entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
        razorpay_order_id = payment_entity.get('order_id')
        razorpay_payment_id = payment_entity.get('id')

        try:
            transaction = Transaction.objects.get(razorpay_order_id=razorpay_order_id)
            if transaction.status != 'paid':
                transaction.razorpay_payment_id = razorpay_payment_id
                transaction.status = 'paid'
                transaction.save()
                transaction.order.status = 'confirmed'
                transaction.order.save()
        except Transaction.DoesNotExist:
            pass

    elif event == 'payment.failed':
        payment_entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
        razorpay_order_id = payment_entity.get('order_id')

        try:
            transaction = Transaction.objects.get(razorpay_order_id=razorpay_order_id)
            transaction.status = 'failed'
            transaction.save()
        except Transaction.DoesNotExist:
            pass

    return Response({'status': 'ok'})
