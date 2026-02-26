import json
from django.http import JsonResponse, HttpRequest
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth.hashers import check_password
from apps.public.models import Participant, PhoneVerification
from apps.public.services import EskizSMS

@method_decorator(csrf_exempt, name="dispatch")
class SendVerificationAPIView(View):
    """API endpoint to send SMS verification code."""
    
    def post(self, request: HttpRequest):
        try:
            data = json.loads(request.body)
            phone_number = data.get("phone_number", "")
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": "invalid_json", "message": "Некорректный JSON"}, status=400)

        # Validate and format phone number
        digits = "".join(filter(str.isdigit, phone_number))
        if digits.startswith("998"):
            digits = digits[3:]
        
        if len(digits) != 9:
            return JsonResponse({"success": False, "error": "invalid_phone", "message": "Введите 9 цифр номера"}, status=400)

        formatted_phone = f"+998{digits}"

        # Check if phone already registered
        if Participant.objects.filter(phone_number=formatted_phone).exists():
            return JsonResponse({"success": False, "error": "phone_exists", "message": "Этот номер уже зарегистрирован"}, status=400)

        # Send verification code
        try:
            sms_service = EskizSMS()
            result = sms_service.send_verification_code(formatted_phone)

            if result["success"]:
                return JsonResponse({"success": True, "message": "Код отправлен"})
            else:
                return JsonResponse({"success": False, "error": result.get("error", "sms_error"), "message": result.get("error", "Ошибка отправки SMS")}, status=500)
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e), "message": f"Ошибка: {str(e)}"}, status=500)

@method_decorator(csrf_exempt, name="dispatch")
class VerifyPhoneAPIView(View):
    """API endpoint to verify SMS code."""
    
    def post(self, request: HttpRequest):
        try:
            data = json.loads(request.body)
            phone_number = data.get("phone_number", "")
            code = data.get("code", "")
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": "invalid_json", "message": "Некорректный JSON"}, status=400)

        # Format phone number
        digits = "".join(filter(str.isdigit, phone_number))
        if digits.startswith("998"):
            digits = digits[3:]
        formatted_phone = f"+998{digits}"

        # Verify code
        sms_service = EskizSMS()
        result = sms_service.verify_code(formatted_phone, code)

        if result["success"]:
            # Store verified phone in session
            request.session["verified_phone"] = formatted_phone
            return JsonResponse({"success": True})
        else:
            error = result.get("error", "unknown")
            message = "Неверный код"
            if error == "code_expired":
                message = "Код истёк"
            return JsonResponse({"success": False, "error": error, "message": message}, status=400)

@method_decorator(csrf_exempt, name="dispatch")
class RegisterAPIView(View):
    """API endpoint for user registration."""

    def post(self, request: HttpRequest):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": "invalid_json", "message": "Некорректный JSON"}, status=400)

        # Required fields
        required_fields = [
            "fullname", "phone_number", "password", "password_confirm",
            "region", "district", "school", "grade", 
            "teacher_fullname", "test_language"
        ]
        
        for field in required_fields:
            if not data.get(field):
                return JsonResponse({"success": False, "error": f"missing_{field}", "message": f"Поле {field} обязательно"}, status=400)

        if data["password"] != data["password_confirm"]:
            return JsonResponse({"success": False, "error": "password_mismatch", "message": "Пароли не совпадают"}, status=400)

        # Format phone number
        digits = "".join(filter(str.isdigit, data["phone_number"]))
        if digits.startswith("998"):
            digits = digits[3:]
        formatted_phone = f"+998{digits}"

        # Check if phone verified in session
        if request.session.get("verified_phone") != formatted_phone:
            return JsonResponse({"success": False, "error": "phone_not_verified", "message": "Номер телефона не подтвержден"}, status=400)

        # Check if already exists (again, to be safe)
        if Participant.objects.filter(phone_number=formatted_phone).exists():
            return JsonResponse({"success": False, "error": "phone_exists", "message": "Этот номер уже зарегистрирован"}, status=400)

        try:
            participant = Participant(
                username=formatted_phone,
                fullname=data["fullname"],
                phone_number=formatted_phone,
                region=data["region"],
                district=data["district"],
                school=data["school"],
                grade=data["grade"],
                teacher_fullname=data["teacher_fullname"],
                test_language=data["test_language"],
            )
            participant.set_password(data["password"])
            participant.save()

            # Log in the user
            request.session["participant_id"] = str(participant.id)
            # Remove verified phone from session
            if "verified_phone" in request.session:
                del request.session["verified_phone"]

            return JsonResponse({"success": True, "message": "Регистрация успешна"})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e), "message": "Ошибка при регистрации"}, status=500)

@method_decorator(csrf_exempt, name="dispatch")
class LoginAPIView(View):
    """API endpoint for user login."""

    def post(self, request: HttpRequest):
        try:
            data = json.loads(request.body)
            phone_number = data.get("phone_number", "")
            password = data.get("password", "")
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": "invalid_json", "message": "Некорректный JSON"}, status=400)

        if not phone_number or not password:
            return JsonResponse({"success": False, "error": "missing_credentials", "message": "Введите номер и пароль"}, status=400)

        # Format phone number
        digits = "".join(filter(str.isdigit, phone_number))
        if digits.startswith("998"):
            digits = digits[3:]
        formatted_phone = f"+998{digits}"

        try:
            participant = Participant.objects.get(phone_number=formatted_phone)
            if participant.check_password(password):
                request.session["participant_id"] = str(participant.id)
                return JsonResponse({"success": True, "message": "Вход выполнен"})
            else:
                return JsonResponse({"success": False, "error": "invalid_credentials", "message": "Неверный номер или пароль"}, status=400)
        except Participant.DoesNotExist:
            return JsonResponse({"success": False, "error": "invalid_credentials", "message": "Неверный номер или пароль"}, status=400)
