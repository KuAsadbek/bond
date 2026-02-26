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
        # Filter participants by registration date (12.02.2026 and later)
        from datetime import datetime, timezone as tz
        cutoff_date = datetime(2026, 2, 12, 0, 0, 0, tzinfo=tz.utc)
        recent_participants = Participant.objects.filter(created_at__gte=cutoff_date)
        
        # Get basic stats (only recent participants)
        total_participants = recent_participants.count()
        checked_in = recent_participants.filter(is_checked_in=True).count()
        not_checked_in = total_participants - checked_in

        # Calculate check-in rate
        checkin_rate = (
            round((checked_in / total_participants * 100), 1)
            if total_participants > 0
            else 0
        )

        # Participants by subject (through Order model) - only recent
        by_subject = (
            Subject.objects.annotate(
                participant_count=Count("orders__participant", distinct=True, filter=Q(orders__participant__created_at__gte=cutoff_date))
            )
            .filter(participant_count__gt=0)
            .order_by("-participant_count")
        )

        # Participants by grade - only recent
        by_grade_list = (
            recent_participants.values("grade")
            .annotate(count=Count("id"))
            .order_by("grade")
        )
        by_grade = list(by_grade_list)
        max_grade_count = max([g['count'] for g in by_grade], default=0)

        # Participants by district - only recent
        by_district = (
            recent_participants.values("district")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        )

        # Recent registrations (last 10) - only recent
        recent_registrations = recent_participants.order_by("-created_at")[:10]

        # Registrations by date (last 7 days)
        seven_days_ago = timezone.now() - timezone.timedelta(days=7)
        registrations_by_date = (
            Participant.objects.filter(created_at__gte=seven_days_ago)
            .annotate(date=TruncDate("created_at"))
            .values("date")
            .annotate(count=Count("id"))
            .order_by("date")
        )

        # Language statistics - only recent
        ru_count = recent_participants.filter(test_language='ru').count()
        uz_count = recent_participants.filter(test_language='uz').count()

        # Olympiad statistics
        now = timezone.now()
        olympiads = OlympiadSettings.objects.all().order_by('-event_date')
        olympiad_stats = []
        for olympiad in olympiads:
            # Determine age group based on olympiad name
            is_preschool = "bog'cha" in olympiad.event_name.lower() or "maktabgacha" in olympiad.event_name.lower()
            
            # Participants with any orders for this olympiad (regardless of status)
            all_orders = Order.objects.filter(olympiad=olympiad)
            all_registered_ids = set(
                all_orders.values_list('participant_id', flat=True).distinct()
            )
            
            # For Maktabgacha: show ALL who registered (any grade)
            # For regular olympiad: show only specific age group (grades 1-11)
            if is_preschool and "maktabgacha" in olympiad.event_name.lower():
                # For Maktabgacha: take all recent participants who have orders for this olympiad
                all_participants = recent_participants.filter(id__in=all_registered_ids)
            else:
                # For regular olympiad: filter by age group
                if is_preschool:
                    age_group_filter = Q(grade=0)
                else:
                    age_group_filter = Q(grade__in=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11])
                all_participants = recent_participants.filter(age_group_filter)
            
            # Paid participants (Ishtirokchilar = те кто оплатил)
            paid_orders = all_orders.filter(status='paid')
            paid_participant_ids = set(paid_orders.values_list(
                'participant_id', flat=True
            ).distinct())
            
            # Filter paid participants to only from correct group
            paid_in_group = all_participants.filter(id__in=paid_participant_ids)
            
            # Total participants (including those without orders)
            total_count = all_participants.count()
            
            # Only paid participants for Ishtirokchilar display
            participant_count = paid_in_group.count()

            # Checked-in participants (must be paid and checked in)
            checked_in_count = paid_in_group.filter(
                is_checked_in=True
            ).count()

            # Total revenue (only from paid orders in this age group)
            total_revenue = paid_orders.filter(
                participant__id__in=all_participants.values_list('id', flat=True)
            ).aggregate(total=Sum('total_amount'))['total'] or 0
            
            # Count unpaid participants (Kutmoqda = не оплатили, включая тех без заказов)
            unpaid_participant_count = total_count - participant_count

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

            # Fetch a few participants for the tooltip/modal (e.g., first 15)
            # We want paid participants who belong to this olympiad's group
            group_participants_list = list(
                paid_in_group.order_by('-created_at').values('fullname', 'phone_number')[:15]
            )

            olympiad_stats.append({
                'olympiad': olympiad,
                'participant_count': participant_count,
                'checked_in_count': checked_in_count,
                'checkin_rate': (
                    round(checked_in_count / participant_count * 100, 1)
                    if participant_count > 0 else 0
                ),
                'total_revenue': total_revenue,
                'unpaid_participant_count': unpaid_participant_count,
                'subjects_stats': subjects_stats,
                'is_upcoming': is_upcoming,
                'participants_list': group_participants_list,
            })

        total_olympiads = olympiads.count()
        total_paid_orders = Order.objects.filter(status='paid').count()

        # Shared participants between two specific olympiads
        shared_participants = []
        o1_query = 'BOND Olimpiadasi'
        o2_query = "Maktabgacha yoshdagi bolalar uchun BOND Olimpiadasi 2"
        
        # More robust lookup
        o1 = OlympiadSettings.objects.filter(event_name__icontains='BOND Olimpiadasi').exclude(event_name__icontains='2').first()
        o2 = OlympiadSettings.objects.filter(
            Q(event_name__icontains='BOND Olimpiadasi') &
            Q(event_name__icontains='2')
        ).first()
        
        o1_name = o1.event_name if o1 else o1_query
        o2_name = o2.event_name if o2 else o2_query
        
        if o1 and o2:
            p1_ids = Order.objects.filter(olympiad=o1).values_list('participant_id', flat=True).distinct()
            p2_ids = Order.objects.filter(olympiad=o2).values_list('participant_id', flat=True).distinct()
            shared_ids = set(p1_ids) & set(p2_ids)
            shared_participants = Participant.objects.filter(id__in=shared_ids).values('fullname', 'phone_number')

        context = {
            "total_participants": total_participants,
            "checked_in": checked_in,
            "not_checked_in": not_checked_in,
            "checkin_rate": checkin_rate,
            "by_subject": by_subject,
            "by_grade": by_grade,
            "max_grade_count": max_grade_count,
            "by_district": by_district,
            "recent_registrations": recent_registrations,
            "registrations_by_date": list(registrations_by_date),
            "ru_count": ru_count,
            "uz_count": uz_count,
            "olympiad_stats": olympiad_stats,
            "total_olympiads": total_olympiads,
            "total_paid_orders": total_paid_orders,
            "shared_participants": list(shared_participants),
            "shared_olympiad_names": [o1_name, o2_name],
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
