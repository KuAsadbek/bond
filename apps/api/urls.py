from django.urls import path
from .payment_views import (
    PaymeCallBackAPIView, 
    InitiatePaymentView, 
    CheckPaymentStatusView,
    ClickCallbackView,
    InitiateClickPaymentView,
)

app_name = 'api'

urlpatterns = [
    path("payme/callback/", PaymeCallBackAPIView.as_view(), name="payme_callback"),
    path("payment/initiate/", InitiatePaymentView.as_view(), name="initiate_payment"),
    path("payment/status/", CheckPaymentStatusView.as_view(), name="payment_status"),
    # Click payment
    path("click/callback/", ClickCallbackView.as_view(), name="click_callback"),
    path("payment/initiate-click/", InitiateClickPaymentView.as_view(), name="initiate_click_payment"),
]
