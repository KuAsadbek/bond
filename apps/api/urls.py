from django.urls import path
from .payment_views import PaymeCallBackAPIView, InitiatePaymentView, CheckPaymentStatusView

app_name = 'api'

urlpatterns = [
    path("payme/callback/", PaymeCallBackAPIView.as_view(), name="payme_callback"),
    path("payment/initiate/", InitiatePaymentView.as_view(), name="initiate_payment"),
    path("payment/status/", CheckPaymentStatusView.as_view(), name="payment_status"),
]
