from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.utils import timezone

from apps.public.models import Participant, Subject, OlympiadSettings, Order


class AdminLoginView(View):
    """Admin login page."""

    def get(self, request):
        if request.user.is_authenticated:
            return redirect("admin_panel:dashboard")
        return render(request, "admin_panel/login.html")

    def post(self, request):
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        if user is not None and user.is_staff:
            login(request, user)
            return redirect("admin_panel:dashboard")

        return render(
            request, "admin_panel/login.html", {"error": "Неверный логин или пароль"}
        )


def admin_logout(request):
    """Logout admin user."""
    logout(request)
    return redirect("admin_panel:login")


class DashboardView(LoginRequiredMixin, View):
    """Main dashboard with statistics."""

    login_url = "/panel/login/"

    def get(self, request):
        # Get basic stats
        total_participants = Participant.objects.count()
        checked_in = Participant.objects.filter(is_checked_in=True).count()
        not_checked_in = total_participants - checked_in

        # Calculate check-in rate
        checkin_rate = (
            round((checked_in / total_participants * 100), 1)
            if total_participants > 0
            else 0
        )

        # Participants by subject (through Order model)
        by_subject = (
            Subject.objects.annotate(
                participant_count=Count("orders__participant", distinct=True)
            )
            .filter(participant_count__gt=0)
            .order_by("-participant_count")
        )

        # Participants by grade
        by_grade = (
            Participant.objects.values("grade")
            .annotate(count=Count("id"))
            .order_by("grade")
        )

        # Participants by district
        by_district = (
            Participant.objects.values("district")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        )

        # Recent registrations (last 10)
        recent_registrations = Participant.objects.order_by("-created_at")[:10]

        # Registrations by date (last 7 days)
        seven_days_ago = timezone.now() - timezone.timedelta(days=7)
        registrations_by_date = (
            Participant.objects.filter(created_at__gte=seven_days_ago)
            .annotate(date=TruncDate("created_at"))
            .values("date")
            .annotate(count=Count("id"))
            .order_by("date")
        )

        # Language statistics
        ru_count = Participant.objects.filter(test_language='ru').count()
        uz_count = Participant.objects.filter(test_language='uz').count()

        # Olympiad statistics
        now = timezone.now()
        olympiads = OlympiadSettings.objects.all().order_by('-event_date')
        olympiad_stats = []
        for olympiad in olympiads:
            # Participants who have paid orders for this olympiad
            paid_orders = Order.objects.filter(
                olympiad=olympiad, status='paid'
            )
            participant_ids = paid_orders.values_list(
                'participant_id', flat=True
            ).distinct()
            participant_count = participant_ids.count()

            # Checked-in participants for this olympiad
            checked_in_count = Participant.objects.filter(
                id__in=participant_ids, is_checked_in=True
            ).count()

            # Total revenue
            total_revenue = paid_orders.aggregate(
                total=Sum('total_amount')
            )['total'] or 0

            # Total orders (all statuses)
            all_orders_count = Order.objects.filter(olympiad=olympiad).count()
            pending_orders = Order.objects.filter(
                olympiad=olympiad, status='pending'
            ).count()

            # Subject breakdown for this olympiad
            subjects_stats = (
                Subject.objects.filter(olympiad=olympiad)
                .annotate(
                    paid_count=Count(
                        'orders__participant',
                        filter=Q(orders__status='paid'),
                        distinct=True,
                    )
                )
                .order_by('-paid_count')
            )

            # Is upcoming or past
            is_upcoming = olympiad.event_date > now

            olympiad_stats.append({
                'olympiad': olympiad,
                'participant_count': participant_count,
                'checked_in_count': checked_in_count,
                'checkin_rate': (
                    round(checked_in_count / participant_count * 100, 1)
                    if participant_count > 0 else 0
                ),
                'total_revenue': total_revenue,
                'all_orders_count': all_orders_count,
                'pending_orders': pending_orders,
                'subjects_stats': subjects_stats,
                'is_upcoming': is_upcoming,
            })

        total_olympiads = olympiads.count()
        total_paid_orders = Order.objects.filter(status='paid').count()

        context = {
            "total_participants": total_participants,
            "checked_in": checked_in,
            "not_checked_in": not_checked_in,
            "checkin_rate": checkin_rate,
            "by_subject": by_subject,
            "by_grade": by_grade,
            "by_district": by_district,
            "recent_registrations": recent_registrations,
            "registrations_by_date": list(registrations_by_date),
            "ru_count": ru_count,
            "uz_count": uz_count,
            "olympiad_stats": olympiad_stats,
            "total_olympiads": total_olympiads,
            "total_paid_orders": total_paid_orders,
        }

        return render(request, "admin_panel/dashboard.html", context)


class ParticipantListView(LoginRequiredMixin, View):
    """List all participants with filtering."""

    login_url = "/panel/login/"

    def get(self, request):
        participants = Participant.objects.all()

        # Search
        search = request.GET.get("search", "")
        if search:
            participants = participants.filter(
                Q(fullname__icontains=search)
                | Q(school__icontains=search)
                | Q(phone_number__icontains=search)
            )

        # Filter by subject
        subject_id = request.GET.get("subject")
        if subject_id:
            participants = participants.filter(subject_id=subject_id)

        # Filter by grade
        grade = request.GET.get("grade")
        if grade:
            participants = participants.filter(grade=grade)

        # Filter by check-in status
        checkin_status = request.GET.get("checkin")
        if checkin_status == "yes":
            participants = participants.filter(is_checked_in=True)
        elif checkin_status == "no":
            participants = participants.filter(is_checked_in=False)

        subjects = Subject.objects.all()

        context = {
            "participants": participants,
            "subjects": subjects,
            "search": search,
            "selected_subject": subject_id,
            "selected_grade": grade,
            "selected_checkin": checkin_status,
        }

        return render(request, "admin_panel/participants.html", context)


class ParticipantDetailView(LoginRequiredMixin, View):
    """View participant details."""

    login_url = "/panel/login/"

    def get(self, request, pk):
        participant = get_object_or_404(Participant, pk=pk)
        return render(
            request, "admin_panel/participant_detail.html", {"participant": participant}
        )


@login_required(login_url="/panel/login/")
def checkin_participant(request, pk):
    """Toggle participant check-in status."""
    if request.method == "POST":
        participant = get_object_or_404(Participant, pk=pk)

        if participant.is_checked_in:
            participant.is_checked_in = False
            participant.checked_in_at = None
        else:
            participant.is_checked_in = True
            participant.checked_in_at = timezone.now()

        participant.save()

        return JsonResponse(
            {
                "success": True,
                "is_checked_in": participant.is_checked_in,
                "checked_in_at": (
                    participant.checked_in_at.strftime("%d.%m.%Y %H:%M")
                    if participant.checked_in_at
                    else None
                ),
            }
        )

    return JsonResponse({"success": False}, status=400)


@login_required(login_url="/panel/login/")
def update_score(request, pk):
    """Update participant score."""
    if request.method == "POST":
        participant = get_object_or_404(Participant, pk=pk)

        try:
            import json

            data = json.loads(request.body)
            score = int(data.get("score", 0))
            participant.score = score
            participant.save()

            return JsonResponse(
                {
                    "success": True,
                    "score": participant.score,
                }
            )
        except (ValueError, json.JSONDecodeError):
            return JsonResponse(
                {"success": False, "error": "Invalid score"}, status=400
            )

    return JsonResponse({"success": False}, status=400)
