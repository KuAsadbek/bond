from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.http import HttpResponse, JsonResponse
from django.views import View
import json
import os
import requests
from django.conf import settings

from .models import Participant, PhoneVerification, OlympiadSettings, Order, Subject, Achievement, AchievementImage, GuideVideo, Partner, ContactMessage
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
        olympiad = OlympiadSettings.get_active()
        return render(
            request, "public/register.html", {
                "form": form, 
                "regions": regions,
                "olympiad": olympiad
            }
        )

    def post(self, request):
        form = ParticipantRegistrationForm(request.POST)
        if form.is_valid():
            participant = form.save()
            # Log in the user
            request.session["participant_id"] = str(participant.id)
            return redirect("public:profile")
        regions = load_regions()
        olympiad = OlympiadSettings.get_active()
        return render(
            request, "public/register.html", {
                "form": form, 
                "regions": regions,
                "olympiad": olympiad
            }
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
            phone_number = form.cleaned_data["phone_number"]
            password = form.cleaned_data["password"]

            try:
                participant = Participant.objects.get(phone_number=phone_number)
                if participant.check_password(password):
                    request.session["participant_id"] = str(participant.id)
                    return redirect("public:profile")
                else:
                    form.add_error(None, "Неверный номер или пароль")
            except Participant.DoesNotExist:
                form.add_error(None, "Неверный номер или пароль")

        return render(request, "public/login.html", {"form": form})


class ProfileView(View):
    """Profile page view."""

    def get(self, request):
        participant_id = request.session.get("participant_id")
        participant = None
        paid_olympiad_ids = set()
        has_unpaid_subjects = set()

        if participant_id:
            participant = get_object_or_404(Participant, id=participant_id)
            
            # Get IDs of olympiads that have at least one paid order
            paid_olympiad_ids = set(Order.objects.filter(
                participant=participant,
                status='paid',
                olympiad__isnull=False
            ).values_list('olympiad_id', flat=True))
            
            # Check which paid olympiads still have un-purchased subjects
            for oid in paid_olympiad_ids:
                total_subjects = Subject.objects.filter(olympiad_id=oid, ticket_price__gt=0).count()
                purchased_subjects = Order.objects.filter(
                    participant=participant, olympiad_id=oid, status='paid',
                    subject__isnull=False
                ).values_list('subject_id', flat=True).distinct().count()
                if purchased_subjects < total_subjects:
                    has_unpaid_subjects.add(oid)

        olympiads = OlympiadSettings.objects.filter(is_active=True).order_by('event_date')

        # Leaderboard data
        leaderboard = Participant.objects.all().order_by("-score")[:5]
        newest_participants = Participant.objects.all().order_by("-created_at")[:5]
        user_rank = 0
        if participant:
            user_rank = Participant.objects.filter(score__gt=participant.score).count() + 1
        
        # Total students count for stats
        total_students = Participant.objects.count()

        # Partners
        partners = Partner.objects.filter(is_active=True).order_by("order", "-created_at")

        # Available subjects for purchase (exclude already paid)
        available_subjects = []
        if participant:
            purchased_subject_ids = Order.objects.filter(
                participant=participant,
                status='paid',
                subject__isnull=False
            ).values_list('subject_id', flat=True)
            available_subjects = Subject.objects.filter(
                olympiad__is_active=True,
                ticket_price__gt=0
            ).exclude(id__in=purchased_subject_ids).select_related('olympiad')
        else:
            available_subjects = Subject.objects.filter(
                olympiad__is_active=True,
                ticket_price__gt=0
            ).select_related('olympiad')

        # Hall of Fame achievements
        achievements = Achievement.objects.filter(is_active=True).order_by("order", "-created_at")

        # Guide video
        guide_video = GuideVideo.objects.filter(is_active=True).first()

        return render(request, "public/profile.html", {
            "participant": participant,
            "olympiads": olympiads,
            "paid_olympiad_ids": paid_olympiad_ids,
            "has_unpaid_subjects": has_unpaid_subjects,
            "leaderboard": leaderboard,
            "newest_participants": newest_participants,
            "user_rank": user_rank,
            "total_students": total_students,
            "achievements": achievements,
            "guide_video": guide_video,
            "partners": partners,
            "available_subjects": available_subjects,
        })


class ContactSubmitView(View):
    """View to handle Contact form submission via AJAX."""

    def post(self, request, *args, **kwargs):
        name = request.POST.get("name")
        phone = request.POST.get("phone")
        message = request.POST.get("message")

        if not name or not phone or not message:
            return JsonResponse({"status": "error", "message": "Barcha maydonlarni to'ldiring!"}, status=400)

        ContactMessage.objects.create(
            name=name,
            phone=phone,
            message=message
        )

        return JsonResponse({"status": "success", "message": "Xabaringiz muvaffaqiyatli yuborildi!"})


class SettingsView(View):
    """Settings page view for user profile settings."""

    def get(self, request):
        participant_id = request.session.get("participant_id")
        if not participant_id:
            return redirect("public:login")

        participant = get_object_or_404(Participant, id=participant_id)
        regions = load_regions()
        districts = load_districts()

        return render(request, "public/settings.html", {
            "participant": participant,
            "regions": regions,
            "districts": districts
        })


def logout_view(request):
    """Logout and redirect to login page."""
    request.session.flush()
    return redirect("public:home")


class TicketView(View):
    """Ticket view page - shows QR code and allows downloading PDF."""

    def get(self, request):
        participant_id = request.session.get("participant_id")
        if not participant_id:
            return redirect("public:login")

        participant = get_object_or_404(Participant, id=participant_id)
        
        olympiad_id = request.GET.get("olympiad_id")
        olympiad = None

        if olympiad_id:
            # Check for specific olympiad payment
            olympiad = get_object_or_404(OlympiadSettings, id=olympiad_id)
            has_paid = Order.objects.filter(
                participant=participant,
                olympiad=olympiad,
                status='paid'
            ).exists()
            
            # Check if any subject has a price > 0 for this olympiad
            has_priced_subject = Subject.objects.filter(olympiad=olympiad, ticket_price__gt=0).exists()
            if has_priced_subject and not has_paid:
                # Redirect to payment for this specific olympiad
                return redirect(f"{reverse('public:payment')}?olympiad_id={olympiad.id}")
        else:
            # Try to find the latest PAID olympiad for this user
            last_paid_order = Order.objects.filter(
                participant=participant,
                status='paid',
                olympiad__isnull=False
            ).order_by('-created_at').first()

            if last_paid_order:
                olympiad = last_paid_order.olympiad
            else:
                # Fallback to active if no paid orders, trigger payment check
                olympiad = OlympiadSettings.get_active()
                if olympiad and Subject.objects.filter(olympiad=olympiad, ticket_price__gt=0).exists():
                    return redirect("public:payment")

        # Get all purchased subjects for this olympiad
        purchased_subjects = []
        if olympiad:
            purchased_subjects = Subject.objects.filter(
                orders__participant=participant,
                orders__olympiad=olympiad,
                orders__status='paid'
            ).distinct()

        return render(request, "public/ticket_view.html", {
            "participant": participant,
            "olympiad": olympiad,
            "purchased_subjects": purchased_subjects,
        })


class RatingView(View):
    """Rating page showing user score and leaderboard."""

    def get(self, request):
        participant_id = request.session.get("participant_id")
        if not participant_id:
            return redirect("public:login")

        participant = get_object_or_404(Participant, id=participant_id)

        # leaderboard logic (top 50 by score)
        leaderboard = Participant.objects.filter(score__gt=0).order_by("-score")[:50]
        
        # find user rank
        user_rank = Participant.objects.filter(score__gt=participant.score).count() + 1
        
        return render(request, "public/rating.html", {
            "participant": participant,
            "leaderboard": leaderboard,
            "user_rank": user_rank
        })


class DownloadTicketView(View):
    """PDF ticket download view."""

    def get(self, request, uuid):
        participant = get_object_or_404(Participant, id=uuid)
        # In a real app, you might check session ownership or validation here
        
        # Verify payment again before download
        # Logic simplified: assuming download link is protected or obscure enough
        # Ideally check Order status here too if strictly required
        
        olympiad = OlympiadSettings.get_active() # Or pass via GET
        
        buffer = generate_ticket_pdf(participant, olympiad)
        return FileResponse(buffer, as_attachment=True, filename=f"ticket_{participant.fullname}.pdf")


class ViewTicketPDFView(View):
    """PDF ticket inline view - for embedding in browser."""

    def get(self, request, uuid):
        participant = get_object_or_404(Participant, id=uuid)
        olympiad = OlympiadSettings.get_active() 
        
        buffer = generate_ticket_pdf(participant, olympiad)
        return FileResponse(buffer, content_type='application/pdf')


class PaymentView(View):
    """Payment page for ticket purchase."""

    def get(self, request):
        participant_id = request.session.get("participant_id")
        if not participant_id:
            return redirect("public:login")

        participant = get_object_or_404(Participant, id=participant_id)
        
        target_olympiad_id = request.GET.get("olympiad_id")
        
        # Get subjects with prices — filter by olympiad if specified
        subject_qs = Subject.objects.filter(
            olympiad__is_active=True, 
            ticket_price__gt=0
        ).select_related('olympiad')
        
        if target_olympiad_id:
            subject_qs = subject_qs.filter(olympiad_id=target_olympiad_id)
        
        # Exclude subjects already purchased by this participant
        purchased_subject_ids = Order.objects.filter(
            participant=participant,
            status='paid',
            subject__isnull=False
        ).values_list('subject_id', flat=True)
        
        subjects = subject_qs.exclude(id__in=purchased_subject_ids).order_by('olympiad__event_date', 'name')
        
        # If specific olympiad requested, redirect only if ALL subjects are paid
        if target_olympiad_id:
            total_subjects = Subject.objects.filter(
                olympiad_id=target_olympiad_id, ticket_price__gt=0
            ).count()
            paid_orders = Order.objects.filter(
                participant=participant,
                olympiad_id=target_olympiad_id,
                status='paid'
            ).count()
            if total_subjects > 0 and paid_orders >= total_subjects:
                return redirect(f"{reverse('public:view_ticket')}?olympiad_id={target_olympiad_id}")

        # Get pending order if exists
        pending_order = Order.objects.filter(
            participant=participant,
            status='pending'
        ).first()
        
        return render(request, "public/payment.html", {
            "participant": participant,
            "subjects": subjects,
            "pending_order": pending_order,
            "target_olympiad_id": int(target_olympiad_id) if target_olympiad_id else None
        })


class SubscribeView(View):
    """Page requiring Telegram channel subscription."""

    def get(self, request):
        participant_id = request.session.get("participant_id")
        if not participant_id:
            return redirect("public:login")

        participant = get_object_or_404(Participant, id=participant_id)
        
        # If already subscribed, redirect to profile
        if participant.telegram_subscribed:
            return redirect("public:profile")
        
        redirect_to = request.GET.get("redirect", "ticket")
        return render(request, "public/subscribe.html", {
            "participant": participant,
            "redirect_to": redirect_to
        })


def check_subscription(request):
    """API endpoint to check Telegram channel subscription."""
    participant_id = request.session.get("participant_id")
    if not participant_id:
        return JsonResponse({"error": "not_authenticated"}, status=401)

    try:
        participant = Participant.objects.get(id=participant_id)
    except Participant.DoesNotExist:
        return JsonResponse({"error": "participant_not_found"}, status=404)

    # Check if we have Telegram user ID
    if not participant.telegram_user_id:
        return JsonResponse({"subscribed": False, "error": "no_telegram_id"})

    # Check subscription via Telegram Bot API
    bot_token = settings.TELEGRAM_BOT_TOKEN
    channel_id = settings.TELEGRAM_CHANNEL_ID
    user_id = participant.telegram_user_id

    try:
        url = f"https://api.telegram.org/bot{bot_token}/getChatMember"
        response = requests.get(url, params={
            "chat_id": channel_id,
            "user_id": user_id
        }, timeout=10)
        
        data = response.json()
        
        if data.get("ok"):
            status = data.get("result", {}).get("status", "")
            # member, administrator, creator are valid subscription statuses
            if status in ["member", "administrator", "creator"]:
                # Update participant's subscription status
                participant.telegram_subscribed = True
                participant.save()
                return JsonResponse({"subscribed": True})
        
        return JsonResponse({"subscribed": False})
    
    except requests.RequestException:
        return JsonResponse({"error": "telegram_api_error"}, status=500)


def send_verification_code(request):
    """API endpoint to send SMS verification code."""
    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    try:
        data = json.loads(request.body)
        phone_number = data.get("phone_number", "")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid_json"}, status=400)

    # Validate and format phone number
    digits = "".join(filter(str.isdigit, phone_number))
    print(digits)
    if digits.startswith("998"):
        digits = digits[3:]
    
    if len(digits) != 9:
        return JsonResponse({"error": "invalid_phone", "message": "Введите 9 цифр номера"}, status=400)

    formatted_phone = f"+998{digits}"

    # Check if phone already registered
    if Participant.objects.filter(phone_number=formatted_phone).exists():
        return JsonResponse({"error": "phone_exists", "message": "Этот номер уже зарегистрирован"}, status=400)

    # Send verification code
    try:
        from .services import EskizSMS
        sms_service = EskizSMS()
        result = sms_service.send_verification_code(formatted_phone)

        if result["success"]:
            return JsonResponse({"success": True, "message": "Код отправлен"})
        else:
            return JsonResponse({"success": False, "error": result.get("error", "sms_error"), "message": result.get("error", "Ошибка отправки SMS")}, status=500)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"success": False, "error": str(e), "message": f"Ошибка: {str(e)}"}, status=500)


def verify_phone_code(request):
    """API endpoint to verify SMS code."""
    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    try:
        data = json.loads(request.body)
        phone_number = data.get("phone_number", "")
        code = data.get("code", "")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid_json"}, status=400)

    # Format phone number
    digits = "".join(filter(str.isdigit, phone_number))
    if digits.startswith("998"):
        digits = digits[3:]
    formatted_phone = f"+998{digits}"

    # Verify code
    from .services import EskizSMS
    sms_service = EskizSMS()
    result = sms_service.verify_code(formatted_phone, code)

    if result["success"]:
        # Store verified phone in session
        request.session["verified_phone"] = formatted_phone
        return JsonResponse({"success": True})
    else:
        error = result.get("error", "unknown")
        if error == "code_expired":
            return JsonResponse({"success": False, "error": "code_expired", "message": "Код истёк"}, status=400)
        else:
            return JsonResponse({"success": False, "error": "invalid_code", "message": "Неверный код"}, status=400)


def change_password(request):
    """API endpoint to change user password."""
    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    participant_id = request.session.get("participant_id")
    if not participant_id:
        return JsonResponse({"error": "not_authenticated"}, status=401)

    try:
        participant = Participant.objects.get(id=participant_id)
    except Participant.DoesNotExist:
        return JsonResponse({"error": "participant_not_found"}, status=404)

    try:
        data = json.loads(request.body)
        current_password = data.get("current_password", "")
        new_password = data.get("new_password", "")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid_json"}, status=400)

    if not current_password or not new_password:
        return JsonResponse({"success": False, "message": "Заполните все поля"}, status=400)

    if not participant.check_password(current_password):
        return JsonResponse({"success": False, "message": "Неверный текущий пароль"}, status=400)

    if len(new_password) < 4:
        return JsonResponse({"success": False, "message": "Пароль должен быть минимум 4 символа"}, status=400)

    participant.set_password(new_password)
    participant.save()

    return JsonResponse({"success": True, "message": "Пароль успешно изменён"})


class ForgotPasswordView(View):
    """Forgot password page view with phone verification."""

    def get(self, request):
        # If already logged in, redirect to profile
        if "participant_id" in request.session:
            return redirect("public:profile")
        return render(request, "public/forgot_password.html")


def send_password_reset_code(request):
    """API endpoint to send SMS code for password reset."""
    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    try:
        data = json.loads(request.body)
        phone_number = data.get("phone_number", "")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid_json"}, status=400)

    # Validate and format phone number
    digits = "".join(filter(str.isdigit, phone_number))
    if digits.startswith("998"):
        digits = digits[3:]
    
    if len(digits) != 9:
        return JsonResponse({"error": "invalid_phone", "message": "Введите 9 цифр номера"}, status=400)

    formatted_phone = f"+998{digits}"

    # Check if phone is registered (opposite of send_verification_code)
    if not Participant.objects.filter(phone_number=formatted_phone).exists():
        return JsonResponse({"error": "phone_not_found", "message": "Этот номер не зарегистрирован"}, status=400)

    # Send verification code
    try:
        from .services import EskizSMS
        sms_service = EskizSMS()
        result = sms_service.send_verification_code(formatted_phone)

        if result["success"]:
            return JsonResponse({"success": True, "message": "Код отправлен"})
        else:
            return JsonResponse({"success": False, "error": result.get("error", "sms_error"), "message": result.get("error", "Ошибка отправки SMS")}, status=500)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"success": False, "error": str(e), "message": f"Ошибка: {str(e)}"}, status=500)


def reset_password_with_phone(request):
    """API endpoint to reset password after phone verification."""
    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    try:
        data = json.loads(request.body)
        phone_number = data.get("phone_number", "")
        code = data.get("code", "")
        new_password = data.get("new_password", "")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid_json"}, status=400)

    if not phone_number or not code or not new_password:
        return JsonResponse({"success": False, "message": "Заполните все поля"}, status=400)

    # Format phone number
    digits = "".join(filter(str.isdigit, phone_number))
    if digits.startswith("998"):
        digits = digits[3:]
    formatted_phone = f"+998{digits}"

    # Verify code first
    from .services import EskizSMS
    sms_service = EskizSMS()
    result = sms_service.verify_code(formatted_phone, code)

    if not result["success"]:
        error = result.get("error", "unknown")
        if error == "code_expired":
            return JsonResponse({"success": False, "error": "code_expired", "message": "Код истёк"}, status=400)
        else:
            return JsonResponse({"success": False, "error": "invalid_code", "message": "Неверный код"}, status=400)

    # Find participant and reset password
    try:
        participant = Participant.objects.get(phone_number=formatted_phone)
    except Participant.DoesNotExist:
        return JsonResponse({"success": False, "message": "Пользователь не найден"}, status=404)

    if len(new_password) < 4:
        return JsonResponse({"success": False, "message": "Пароль должен быть минимум 4 символа"}, status=400)

    participant.set_password(new_password)
    participant.save()

    return JsonResponse({"success": True, "message": "Пароль успешно изменён"})


class AchievementDetailView(View):
    """Detail page for a single Achievement (Shon-sharaf zali card)."""

    def get(self, request, pk):
        achievement = get_object_or_404(Achievement, pk=pk, is_active=True)
        gallery_images = achievement.gallery_images.all()
        return render(request, "public/detail_card.html", {
            "achievement": achievement,
            "gallery_images": gallery_images,
        })

