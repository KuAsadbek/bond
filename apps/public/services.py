"""
Eskiz SMS API Service with automatic token management.

Token is stored in a local JSON file and automatically refreshed
when expired or missing. Falls back to login if refresh fails.
"""
import json
import os
import random
import time
import requests
from pathlib import Path
from django.conf import settings


# Token storage file path
TOKEN_FILE = Path(settings.BASE_DIR) / ".eskiz_token.json"


class EskizSMS:
    """Service for sending SMS via Eskiz.uz API with auto token refresh."""

    BASE_URL = "https://notify.eskiz.uz/api"

    def __init__(self):
        self.token = self._load_token()

    # ─── Token Management ────────────────────────────────────────

    def _load_token(self) -> str:
        """Load token from file. If missing or invalid, obtain a new one."""
        if TOKEN_FILE.exists():
            try:
                data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
                token = data.get("token", "")
                if token:
                    return token
            except (json.JSONDecodeError, OSError):
                pass

        # No valid token in file — get a fresh one
        return self._login()

    def _save_token(self, token: str):
        """Persist token to file."""
        try:
            TOKEN_FILE.write_text(
                json.dumps({"token": token, "updated_at": time.time()}),
                encoding="utf-8",
            )
        except OSError as e:
            print(f"[ESKIZ] Warning: could not save token file: {e}")

    def _login(self) -> str:
        """Authenticate with email/password and obtain a new token."""
        email = getattr(settings, "ESKIZ_EMAIL", "")
        password = getattr(settings, "ESKIZ_PASSWORD", "")

        if not email or not password:
            raise RuntimeError(
                "ESKIZ_EMAIL and ESKIZ_PASSWORD must be set in settings.py"
            )

        print(f"[ESKIZ] Logging in with {email}...")

        try:
            resp = requests.post(
                f"{self.BASE_URL}/auth/login",
                data={"email": email, "password": password},
                timeout=15,
            )
            result = resp.json()

            if resp.status_code == 200 and result.get("data", {}).get("token"):
                token = result["data"]["token"]
                self._save_token(token)
                print("[ESKIZ] Login successful — new token saved.")
                return token
            else:
                raise RuntimeError(
                    f"Eskiz login failed: {result.get('message', resp.text)}"
                )
        except requests.RequestException as e:
            raise RuntimeError(f"Eskiz login request failed: {e}")

    def _refresh_token(self) -> str:
        """Try to refresh the current token. Falls back to login on failure."""
        print("[ESKIZ] Attempting token refresh...")

        try:
            resp = requests.patch(
                f"{self.BASE_URL}/auth/refresh",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=15,
            )
            result = resp.json()

            if resp.status_code == 200 and result.get("data", {}).get("token"):
                token = result["data"]["token"]
                self._save_token(token)
                print("[ESKIZ] Token refreshed successfully.")
                return token
        except requests.RequestException:
            pass

        # Refresh failed — fall back to full login
        print("[ESKIZ] Refresh failed, falling back to login...")
        return self._login()

    # ─── SMS Sending ─────────────────────────────────────────────

    def generate_code(self) -> str:
        """Generate a 6-digit verification code."""
        return str(random.randint(100000, 999999))

    def _send_request(self, phone: str, message: str) -> requests.Response:
        """Send a single SMS request with the current token."""
        return requests.post(
            f"{self.BASE_URL}/message/sms/send",
            headers={"Authorization": f"Bearer {self.token}"},
            data={
                "mobile_phone": phone,
                "message": message,
                "from": "4546",
            },
            timeout=10,
        )

    def send_sms(self, phone_number: str, message: str) -> dict:
        """
        Send SMS with automatic token retry.

        If the first attempt returns 401/403 or 'Expired',
        refreshes the token and retries once.
        """
        phone = phone_number.replace("+", "")

        # First attempt
        try:
            resp = self._send_request(phone, message)
            result = resp.json()

            # Check for token expiration
            if self._is_token_error(resp, result):
                # Refresh and retry
                self.token = self._refresh_token()
                resp = self._send_request(phone, message)
                result = resp.json()

            if resp.status_code == 200 and result.get("status") in (
                "success",
                "waiting",
            ):
                return {"success": True, "message_id": result.get("id")}
            else:
                return {
                    "success": False,
                    "error": result.get("message", "Unknown error"),
                }

        except requests.RequestException as e:
            return {"success": False, "error": str(e)}

    def _is_token_error(self, resp: requests.Response, result: dict) -> bool:
        """Check if the response indicates an expired or invalid token."""
        if resp.status_code in (401, 403):
            return True

        msg = str(result.get("message", "")).lower()
        status = str(result.get("status", "")).lower()

        if "expired" in msg or "expired" in status:
            return True
        if "token" in msg and ("invalid" in msg or "not found" in msg):
            return True

        return False

    # ─── Verification Code Flow ──────────────────────────────────

    def send_verification_code(self, phone_number: str) -> dict:
        """Generate and send verification code to the phone number."""
        from .models import PhoneVerification

        code = self.generate_code()
        message = f"BOND Olimpiadasida telefon raqamni tastiqlash kodi: {code}"

        # Delete old verification codes for this number
        PhoneVerification.objects.filter(phone_number=phone_number).delete()

        # Send SMS
        result = self.send_sms(phone_number, message)

        if result["success"]:
            PhoneVerification.objects.create(
                phone_number=phone_number, code=code
            )
            return {"success": True, "code": code}
        else:
            return result

    def verify_code(self, phone_number: str, code: str) -> dict:
        """Verify the code for the given phone number."""
        from .models import PhoneVerification

        try:
            verification = PhoneVerification.objects.filter(
                phone_number=phone_number,
                code=code,
                is_verified=False,
            ).latest("created_at")

            if not verification.is_valid():
                return {"success": False, "error": "code_expired"}

            verification.is_verified = True
            verification.save()

            return {"success": True}

        except PhoneVerification.DoesNotExist:
            return {"success": False, "error": "invalid_code"}
