from django.urls import path
from . import views

urlpatterns = [
    path("create/", views.create_payment, name="create-payment"),
    path("verify/", views.verify_payment, name="verify-payment"),
    path("webhook/", views.payment_webhook, name="payment-webhook"),
]
