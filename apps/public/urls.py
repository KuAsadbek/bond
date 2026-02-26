from django.urls import path
from .views import (
    RegisterView,
    DownloadTicketView,
    ViewTicketPDFView,
    LoginView,
    ProfileView,
    SettingsView,
    RatingView,
    TicketView,
    SubscribeView,
    ForgotPasswordView,
    PaymentView,
    AchievementDetailView,
    logout_view,
    get_districts_by_region,
    check_subscription,
    send_verification_code,
    verify_phone_code,
    change_password,
    send_password_reset_code,
    reset_password_with_phone,
    ContactSubmitView,
)

app_name = "public"

urlpatterns = [
    path("", ProfileView.as_view(), name="home"),
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path("settings/", SettingsView.as_view(), name="settings"),
    path("ticket/", TicketView.as_view(), name="view_ticket"),
    path("payment/", PaymentView.as_view(), name="payment"),
    path("rating/", RatingView.as_view(), name="rating"),
    path("subscribe/", SubscribeView.as_view(), name="subscribe"),
    path("logout/", logout_view, name="logout"),
    path(
        "ticket/<uuid:uuid>/download/",
        DownloadTicketView.as_view(),
        name="download_ticket",
    ),
    path(
        "ticket/<uuid:uuid>/view/", ViewTicketPDFView.as_view(), name="view_ticket_pdf"
    ),
    path(
        "api/districts/<int:region_id>/", get_districts_by_region, name="get_districts"
    ),
    path("api/check-subscription/", check_subscription, name="check_subscription"),
    path("api/send-code/", send_verification_code, name="send_verification_code"),
    path("api/verify-code/", verify_phone_code, name="verify_phone_code"),
    path("api/change-password/", change_password, name="change_password"),
    path("forgot-password/", ForgotPasswordView.as_view(), name="forgot_password"),
    path("api/send-reset-code/", send_password_reset_code, name="send_reset_code"),
    path("api/reset-password/", reset_password_with_phone, name="reset_password"),
    path("contact-submit/", ContactSubmitView.as_view(), name="contact_submit"),
    path("achievement/<int:pk>/", AchievementDetailView.as_view(), name="achievement_detail"),
]



