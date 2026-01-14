from django.urls import path
from . import views

app_name = "admin_panel"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("participants/", views.ParticipantListView.as_view(), name="participants"),
    path(
        "participants/<uuid:pk>/",
        views.ParticipantDetailView.as_view(),
        name="participant_detail",
    ),
    path("participants/<uuid:pk>/checkin/", views.checkin_participant, name="checkin"),
    path("participants/<uuid:pk>/score/", views.update_score, name="update_score"),
    path("login/", views.AdminLoginView.as_view(), name="login"),
    path("logout/", views.admin_logout, name="logout"),
]
