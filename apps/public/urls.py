from django.urls import path
from .views import (
    RegisterView,
    DownloadTicketView,
    ViewTicketPDFView,
    LoginView,
    ProfileView,
    RatingView,
    TicketView,
    SubscribeView,
    logout_view,
    get_districts_by_region,
    check_subscription,
    send_verification_code,
    verify_phone_code,
)

app_name = "public"

urlpatterns = [
    path("", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path("ticket/", TicketView.as_view(), name="view_ticket"),
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
]

