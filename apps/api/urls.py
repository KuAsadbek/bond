from django.urls import path
from .payment_views import (
    PaymeCallBackAPIView, 
    InitiatePaymentView, 
    CheckPaymentStatusView,
    ClickCallbackView,
    InitiateClickPaymentView,
)

from .views import (
    RegisterAPIView,
    LoginAPIView,
    SendVerificationAPIView,
    VerifyPhoneAPIView,
)

app_name = 'api'

urlpatterns = [
    path("register/", RegisterAPIView.as_view(), name="register"),
    path("login/", LoginAPIView.as_view(), name="login"),
    path("send-code/", SendVerificationAPIView.as_view(), name="send_code"),
    path("verify-phone/", VerifyPhoneAPIView.as_view(), name="verify_phone"),

    path("payme/callback/", PaymeCallBackAPIView.as_view(), name="payme_callback"),
    path("payment/initiate/", InitiatePaymentView.as_view(), name="initiate_payment"),
    path("payment/status/", CheckPaymentStatusView.as_view(), name="payment_status"),
    # Click payment
    path("click/callback/", ClickCallbackView.as_view(), name="click_callback"),
    path("payment/initiate-click/", InitiateClickPaymentView.as_view(), name="initiate_click_payment"),
]
