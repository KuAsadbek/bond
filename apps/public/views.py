from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.views import View
import json
import os
from django.conf import settings

from .models import Participant
from .forms import ParticipantRegistrationForm, LoginForm
from .utils import generate_ticket_pdf


def load_regions():
    """Load regions from JSON file."""
    json_path = os.path.join(settings.BASE_DIR, "regions.json")
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_districts():
    """Load districts from JSON file."""
    json_path = os.path.join(settings.BASE_DIR, "districts.json")
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_districts_by_region(request, region_id):
    """API endpoint to get districts by region ID."""
    districts = load_districts()
    filtered = [d for d in districts if d["region_id"] == region_id]
    return JsonResponse({"districts": filtered})


class RegisterView(View):
    """Registration page view."""

    def get(self, request):
        # If already logged in, redirect to profile
        if "participant_id" in request.session:
            return redirect("public:profile")
        form = ParticipantRegistrationForm()
        regions = load_regions()
        return render(
            request, "public/register.html", {"form": form, "regions": regions}
        )

    def post(self, request):
        form = ParticipantRegistrationForm(request.POST)
        if form.is_valid():
            participant = form.save()
            # Log in the user
            request.session["participant_id"] = str(participant.id)
            return redirect("public:profile")
        regions = load_regions()
        return render(
            request, "public/register.html", {"form": form, "regions": regions}
        )


class LoginView(View):
    """Login page view."""

    def get(self, request):
        # If already logged in, redirect to profile
        if "participant_id" in request.session:
            return redirect("public:profile")
        form = LoginForm()
        return render(request, "public/login.html", {"form": form})

    def post(self, request):
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data["username"]
            password = form.cleaned_data["password"]

            try:
                participant = Participant.objects.get(username=username)
                if participant.check_password(password):
                    request.session["participant_id"] = str(participant.id)
                    return redirect("public:profile")
                else:
                    form.add_error(None, "Неверный логин или пароль")
            except Participant.DoesNotExist:
                form.add_error(None, "Неверный логин или пароль")

        return render(request, "public/login.html", {"form": form})


class ProfileView(View):
    """Profile page view."""

    def get(self, request):
        participant_id = request.session.get("participant_id")
        if not participant_id:
            return redirect("public:login")

        participant = get_object_or_404(Participant, id=participant_id)
        return render(request, "public/profile.html", {"participant": participant})


def logout_view(request):
    """Logout and redirect to login page."""
    if "participant_id" in request.session:
        del request.session["participant_id"]
    return redirect("public:login")


class TicketView(View):
    """Ticket view page - shows QR code and allows downloading PDF."""

    def get(self, request):
        participant_id = request.session.get("participant_id")
        if not participant_id:
            return redirect("public:login")

        participant = get_object_or_404(Participant, id=participant_id)
        return render(request, "public/ticket_view.html", {"participant": participant})


class RatingView(View):
    """Rating page showing user score and leaderboard."""

    def get(self, request):
        participant_id = request.session.get("participant_id")
        if not participant_id:
            return redirect("public:login")

        participant = get_object_or_404(Participant, id=participant_id)

        # Get total participants count
        total_participants = Participant.objects.count()

        # Calculate user rank (based on score, higher is better)
        user_rank = Participant.objects.filter(score__gt=participant.score).count() + 1

        # Get top 20 leaderboard
        leaderboard = Participant.objects.order_by("-score", "fullname")[:20]

        context = {
            "participant": participant,
            "user_rank": user_rank,
            "total_participants": total_participants,
            "leaderboard": leaderboard,
        }

        return render(request, "public/rating.html", context)


class DownloadTicketView(View):
    """PDF ticket download view."""

    def get(self, request, uuid):
        participant = get_object_or_404(Participant, id=uuid)

        # Generate PDF
        pdf_bytes = generate_ticket_pdf(participant)

        # Create response
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        filename = f'ticket_{participant.fullname.replace(" ", "_")}.pdf'
        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        return response


class ViewTicketPDFView(View):
    """PDF ticket inline view - for embedding in browser."""

    def get(self, request, uuid):
        participant = get_object_or_404(Participant, id=uuid)

        # Generate PDF
        pdf_bytes = generate_ticket_pdf(participant)

        # Create response - inline instead of attachment
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        filename = f'ticket_{participant.fullname.replace(" ", "_")}.pdf'
        response["Content-Disposition"] = f'inline; filename="{filename}"'

        return response
