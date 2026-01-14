"""
Eskiz SMS API Service for sending verification codes.
"""
import random
import requests
from django.conf import settings


class EskizSMS:
    """Service for sending SMS via Eskiz.uz API."""

    BASE_URL = "https://notify.eskiz.uz/api"

    def __init__(self):
        self.token = settings.ESKIZ_TOKEN

    def generate_code(self):
        """Generate a 6-digit verification code."""
        return str(random.randint(100000, 999999))

    def send_sms(self, phone_number: str, message: str) -> dict:
        """
        Send SMS to the given phone number.
        
        Args:
            phone_number: Phone number in format +998XXXXXXXXX
            message: SMS text message
            
        Returns:
            dict with status and message
        """
        # Remove + from phone number for API
        phone = phone_number.replace("+", "")
        
        headers = {
            "Authorization": f"Bearer {self.token}",
        }
        
        data = {
            "mobile_phone": phone,
            "message": message,
            "from": "4546",  # Sender ID
        }
        
        print(f"[DEBUG] Sending SMS to {phone}")
        print(f"[DEBUG] Token: {self.token[:50]}...")
        
        try:
            response = requests.post(
                f"{self.BASE_URL}/message/sms/send",
                headers=headers,
                data=data,
                timeout=10
            )
            
            print(f"[DEBUG] Response status: {response.status_code}")
            print(f"[DEBUG] Response body: {response.text}")
            
            result = response.json()
            
            if response.status_code == 200 and result.get("status") == "success":
                return {"success": True, "message_id": result.get("id")}
            else:
                return {"success": False, "error": result.get("message", "Unknown error")}
                
        except requests.RequestException as e:
            print(f"[DEBUG] Request error: {e}")
            return {"success": False, "error": str(e)}

    def send_verification_code(self, phone_number: str) -> dict:
        """
        Generate and send verification code to the phone number.
        
        Args:
            phone_number: Phone number in format +998XXXXXXXXX
            
        Returns:
            dict with success status and code (for storing)
        """
        from .models import PhoneVerification
        
        code = self.generate_code()
        message = f"BOND Olimpiadasida telefon raqamni tastiqlash kodi: {code}"
        
        # Delete old verification codes for this number
        PhoneVerification.objects.filter(phone_number=phone_number).delete()
        
        # Send SMS
        result = self.send_sms(phone_number, message)
        
        if result["success"]:
            # Store verification code
            PhoneVerification.objects.create(
                phone_number=phone_number,
                code=code
            )
            return {"success": True, "code": code}
        else:
            return result

    def verify_code(self, phone_number: str, code: str) -> dict:
        """
        Verify the code for the given phone number.
        
        Args:
            phone_number: Phone number in format +998XXXXXXXXX
            code: 6-digit verification code
            
        Returns:
            dict with verification result
        """
        from .models import PhoneVerification
        
        try:
            verification = PhoneVerification.objects.filter(
                phone_number=phone_number,
                code=code,
                is_verified=False
            ).latest("created_at")
            
            if not verification.is_valid():
                return {"success": False, "error": "code_expired"}
            
            verification.is_verified = True
            verification.save()
            
            return {"success": True}
            
        except PhoneVerification.DoesNotExist:
            return {"success": False, "error": "invalid_code"}
