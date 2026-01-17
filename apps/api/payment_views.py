"""
Payme Merchant API Integration Views (JSON-RPC 2.0).

Endpoints:
- POST /api/payme/callback/          Payme Merchant API endpoint (JSON-RPC)
- POST /api/payment/initiate/        Create/return pending order and payment URL
- GET  /api/payment/status/          Check participant payment status

Notes:
- While PAYME_KEY is empty/not set, callback endpoint works in "stub mode":
  it returns valid JSON-RPC replies WITHOUT auth checks. Use only to create cashbox.
- After cashbox creation, set PAYME_ID and PAYME_KEY in settings.py and redeploy.
"""

import base64
import json
from typing import Any, Dict, Optional

from django.conf import settings
from django.http import JsonResponse, HttpRequest
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils import timezone

from apps.public.models import Order, Participant, OlympiadSettings

# Payme / Paycom error codes (commonly used)
ERROR_INTERNAL_SERVER = -32400
ERROR_INSUFFICIENT_PRIVILEGE = -32504
ERROR_INVALID_JSON_RPC_OBJECT = -32600
ERROR_METHOD_NOT_FOUND = -32601
ERROR_INVALID_PARAMS = -32602

ERROR_INVALID_AMOUNT = -31001
ERROR_ORDER_NOT_FOUND = -31050
ERROR_CANT_PERFORM_OPERATION = -31008
ERROR_ORDER_ALREADY_PAID = -31051
ERROR_TRANSACTION_NOT_FOUND = -31003

def generate_pay_link(order_id: int, amount_tiyin: int, return_url: Optional[str] = None) -> str:
    """
    Generate Payme checkout URL.

    amount_tiyin: integer (1 sum = 100 tiyin)
    """
    merchant_id = getattr(settings, "PAYME_ID", None)
    if not merchant_id:
        # Without merchant ID checkout link cannot be built
        raise RuntimeError("PAYME_ID is not set. Create cashbox and set PAYME_ID in settings.")

    params = f"m={merchant_id};ac.order_id={order_id};a={int(amount_tiyin)}"
    if return_url:
        params += f";c={return_url}"

    encoded = base64.b64encode(params.encode("utf-8")).decode("utf-8")

    base_url = "https://checkout.test.paycom.uz" if settings.DEBUG else "https://checkout.test.uz"
    return f"{base_url}/{encoded}"


class InitiatePaymentView(View):
    """
    Create order and return Payme payment URL.

    POST /api/payment/initiate/
    """

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post(self, request: HttpRequest):
        participant_id = request.session.get("participant_id")
        if not participant_id:
            return JsonResponse({"success": False, "error": "Unauthorized"}, status=401)

        try:
            participant = Participant.objects.get(id=participant_id)
        except Participant.DoesNotExist:
            return JsonResponse({"success": False, "error": "Participant not found"}, status=404)

        if participant.is_paid:
            return JsonResponse({"success": False, "error": "Already paid"}, status=400)

        olympiad = OlympiadSettings.get_active()
        if not olympiad or olympiad.ticket_price <= 0:
            return JsonResponse({"success": False, "error": "Ticket price not configured"}, status=400)

        pending_order = Order.objects.filter(participant=participant, status="pending").first()
        if pending_order:
            amount_tiyin = int(pending_order.total_amount * 100)
            pay_url = generate_pay_link(
                order_id=pending_order.id,
                amount_tiyin=amount_tiyin,
                return_url=request.build_absolute_uri("/ticket/"),
            )
            return JsonResponse({
                "success": True,
                "order_id": pending_order.id,
                "amount": float(pending_order.total_amount),
                "pay_url": pay_url,
            })

        order = Order.objects.create(
            participant=participant,
            total_amount=olympiad.ticket_price,
            status="pending",
            payment_method="payme",
        )

        amount_tiyin = int(olympiad.ticket_price * 100)
        pay_url = generate_pay_link(
            order_id=order.id,
            amount_tiyin=amount_tiyin,
            return_url=request.build_absolute_uri("/ticket/"),
        )

        return JsonResponse({
            "success": True,
            "order_id": order.id,
            "amount": float(olympiad.ticket_price),
            "pay_url": pay_url,
        })


class CheckPaymentStatusView(View):
    """
    Check payment status.

    GET /api/payment/status/
    """

    def get(self, request: HttpRequest):
        participant_id = request.session.get("participant_id")
        if not participant_id:
            return JsonResponse({"success": False, "error": "Unauthorized"}, status=401)

        try:
            participant = Participant.objects.get(id=participant_id)
        except Participant.DoesNotExist:
            return JsonResponse({"success": False, "error": "Participant not found"}, status=404)

        return JsonResponse({
            "success": True,
            "is_paid": participant.is_paid,
            "paid_at": participant.paid_at.isoformat() if participant.paid_at else None,
        })


@method_decorator(csrf_exempt, name="dispatch")
class PaymeCallBackAPIView(View):
    """
    Payme Merchant API callback handler (JSON-RPC 2.0).

    POST /api/payme/callback/

    Implements:
    - CheckPerformTransaction
    - CreateTransaction
    - PerformTransaction
    - CancelTransaction
    - CheckTransaction

    Stub mode:
    - If settings.PAYME_KEY is missing/empty, responds with valid JSON-RPC success
      for any known method. Use only for initial cashbox creation.
    """

    # ---------- JSON-RPC helpers ----------
    def _success(self, rpc_id: Any, result: Dict[str, Any]) -> JsonResponse:
        return JsonResponse({"jsonrpc": "2.0", "id": rpc_id, "result": result}, status=200)

    def _error(self, rpc_id: Any, code: int, message: str, data: Optional[str] = None) -> JsonResponse:
        err: Dict[str, Any] = {
            "code": code,
            "message": {"ru": message, "uz": message, "en": message},
        }
        if data is not None:
            err["data"] = data
        return JsonResponse({"jsonrpc": "2.0", "id": rpc_id, "error": err}, status=200)

    def _parse_json(self, request: HttpRequest) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(request.body.decode("utf-8"))
        except Exception:
            return None

    # ---------- auth ----------
    def _verify_auth(self, request: HttpRequest) -> bool:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(auth_header.split(" ", 1)[1]).decode("utf-8")
            username, password = decoded.split(":", 1)
            return username == "Paycom" and password == settings.PAYME_KEY
        except Exception:
            return False

    # ---------- order helpers ----------
    def _get_order_id(self, params: Dict[str, Any]) -> Optional[int]:
        account = params.get("account") or {}
        order_id = account.get("order_id")
        if order_id is None:
            return None
        try:
            return int(order_id)
        except Exception:
            return None

    def _get_order(self, order_id: int) -> Optional[Order]:
        try:
            return Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return None

    # ---------- main handler ----------
    def post(self, request: HttpRequest):
        data = self._parse_json(request)
        if not data:
            return self._error(None, ERROR_INVALID_JSON_RPC_OBJECT, "Invalid JSON-RPC object")

        rpc_id = data.get("id")
        method = data.get("method")
        params = data.get("params") or {}

        # Stub mode for cashbox creation (no PAYME_KEY yet)
        if not getattr(settings, "PAYME_KEY", None):
            # Return minimal valid replies to make Payme happy during setup
            if method == "CheckPerformTransaction":
                return self._success(rpc_id, {"allow": True})
            if method == "CreateTransaction":
                return self._success(rpc_id, {
                    "create_time": int(timezone.now().timestamp() * 1000),
                    "transaction": "stub",
                    "state": 1
                })
            if method == "PerformTransaction":
                return self._success(rpc_id, {
                    "perform_time": int(timezone.now().timestamp() * 1000),
                    "transaction": "stub",
                    "state": 2
                })
            if method == "CancelTransaction":
                return self._success(rpc_id, {
                    "cancel_time": int(timezone.now().timestamp() * 1000),
                    "transaction": "stub",
                    "state": -1
                })
            if method == "CheckTransaction":
                return self._success(rpc_id, {
                    "create_time": int(timezone.now().timestamp() * 1000),
                    "perform_time": 0,
                    "cancel_time": 0,
                    "transaction": "stub",
                    "state": 1,
                    "reason": None,
                })
            return self._error(rpc_id, ERROR_METHOD_NOT_FOUND, f"Method not found: {method}")

        # Production mode: require auth
        if not self._verify_auth(request):
            return self._error(None, ERROR_INSUFFICIENT_PRIVILEGE, "Unauthorized")

        # Route methods
        handlers = {
            "CheckPerformTransaction": self._check_perform_transaction,
            "CreateTransaction": self._create_transaction,
            "PerformTransaction": self._perform_transaction,
            "CancelTransaction": self._cancel_transaction,
            "CheckTransaction": self._check_transaction,
        }
        handler = handlers.get(method)
        if not handler:
            return self._error(rpc_id, ERROR_METHOD_NOT_FOUND, f"Method not found: {method}")

        try:
            return handler(rpc_id, params)
        except Exception:
            # Never return non-200; Payme treats it as -32400
            return self._error(rpc_id, ERROR_INTERNAL_SERVER, "Internal server error")

    # ---------- method implementations ----------
    def _check_perform_transaction(self, rpc_id: Any, params: Dict[str, Any]) -> JsonResponse:
        order_id = self._get_order_id(params)
        if order_id is None:
            return self._error(rpc_id, ERROR_INVALID_PARAMS, "Invalid Params", "order_id")

        order = self._get_order(order_id)
        if not order:
            return self._error(rpc_id, ERROR_ORDER_NOT_FOUND, "Order not found", "order_id")

        if order.status == "paid":
            return self._error(rpc_id, ERROR_ORDER_ALREADY_PAID, "Order already paid", "order_id")

        amount = params.get("amount")
        if amount is None:
            return self._error(rpc_id, ERROR_INVALID_PARAMS, "Invalid Params", "amount")

        expected_amount = int(order.total_amount * 100)
        if int(amount) != expected_amount:
            return self._error(rpc_id, ERROR_INVALID_AMOUNT, "Invalid amount", "amount")

        return self._success(rpc_id, {"allow": True})

    def _create_transaction(self, rpc_id: Any, params: Dict[str, Any]) -> JsonResponse:
        order_id = self._get_order_id(params)
        if order_id is None:
            return self._error(rpc_id, ERROR_INVALID_PARAMS, "Invalid Params", "order_id")

        order = self._get_order(order_id)
        if not order:
            return self._error(rpc_id, ERROR_ORDER_NOT_FOUND, "Order not found", "order_id")

        transaction_id = params.get("id")
        if not transaction_id:
            return self._error(rpc_id, ERROR_INVALID_PARAMS, "Invalid Params", "id")

        # If your Order model has payme_transaction_id field
        if getattr(order, "payme_transaction_id", None):
            if order.payme_transaction_id != transaction_id:
                return self._error(rpc_id, ERROR_CANT_PERFORM_OPERATION, "Order has different transaction", "id")
        else:
            order.payme_transaction_id = transaction_id
            order.save(update_fields=["payme_transaction_id"])

        create_time = params.get("time") or int(timezone.now().timestamp() * 1000)

        return self._success(rpc_id, {
            "create_time": int(create_time),
            "transaction": str(transaction_id),
            "state": 1,
        })

    def _perform_transaction(self, rpc_id: Any, params: Dict[str, Any]) -> JsonResponse:
        transaction_id = params.get("id")
        if not transaction_id:
            return self._error(rpc_id, ERROR_INVALID_PARAMS, "Invalid Params", "id")

        try:
            order = Order.objects.get(payme_transaction_id=transaction_id)
        except Order.DoesNotExist:
            return self._error(rpc_id, ERROR_TRANSACTION_NOT_FOUND, "Transaction not found", "id")

        if order.status == "paid":
            return self._success(rpc_id, {
                "perform_time": int((order.updated_at or timezone.now()).timestamp() * 1000),
                "transaction": str(transaction_id),
                "state": 2,
            })

        order.status = "paid"
        order.updated_at = timezone.now() if hasattr(order, "updated_at") else timezone.now()
        order.save(update_fields=["status", "updated_at"] if hasattr(order, "updated_at") else ["status"])

        participant = order.participant
        participant.is_paid = True
        participant.paid_at = timezone.now()
        participant.save(update_fields=["is_paid", "paid_at"])

        return self._success(rpc_id, {
            "perform_time": int(timezone.now().timestamp() * 1000),
            "transaction": str(transaction_id),
            "state": 2,
        })

    def _cancel_transaction(self, rpc_id: Any, params: Dict[str, Any]) -> JsonResponse:
        transaction_id = params.get("id")
        if not transaction_id:
            return self._error(rpc_id, ERROR_INVALID_PARAMS, "Invalid Params", "id")

        reason = params.get("reason")  # optional

        try:
            order = Order.objects.get(payme_transaction_id=transaction_id)
        except Order.DoesNotExist:
            return self._error(rpc_id, ERROR_TRANSACTION_NOT_FOUND, "Transaction not found", "id")

        was_paid = (order.status == "paid")

        order.status = "cancelled"
        order.updated_at = timezone.now() if hasattr(order, "updated_at") else timezone.now()
        order.save(update_fields=["status", "updated_at"] if hasattr(order, "updated_at") else ["status"])

        if was_paid:
            participant = order.participant
            participant.is_paid = False
            participant.paid_at = None
            participant.save(update_fields=["is_paid", "paid_at"])

        state = -2 if was_paid else -1

        return self._success(rpc_id, {
            "cancel_time": int(timezone.now().timestamp() * 1000),
            "transaction": str(transaction_id),
            "state": state,
        })

    def _check_transaction(self, rpc_id: Any, params: Dict[str, Any]) -> JsonResponse:
        transaction_id = params.get("id")
        if not transaction_id:
            return self._error(rpc_id, ERROR_INVALID_PARAMS, "Invalid Params", "id")

        try:
            order = Order.objects.get(payme_transaction_id=transaction_id)
        except Order.DoesNotExist:
            return self._error(rpc_id, ERROR_TRANSACTION_NOT_FOUND, "Transaction not found", "id")

        if order.status == "paid":
            state = 2
        elif order.status == "cancelled":
            state = -1
        else:
            state = 1

        created_ms = int(order.created_at.timestamp() * 1000) if hasattr(order, "created_at") and order.created_at else 0
        updated_ms = int(order.updated_at.timestamp() * 1000) if hasattr(order, "updated_at") and order.updated_at else 0

        return self._success(rpc_id, {
            "create_time": created_ms,
            "perform_time": updated_ms if order.status == "paid" else 0,
            "cancel_time": updated_ms if order.status == "cancelled" else 0,
            "transaction": str(transaction_id),
            "state": state,
            "reason": None,
        })
