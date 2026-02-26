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
from django.db import transaction
from typing import Any, Dict, Optional
from decimal import Decimal,InvalidOperation
from django.conf import settings
from django.http import JsonResponse, HttpRequest
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils import timezone

from apps.public.models import Order, Participant, OlympiadSettings, Subject

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

    base_url = "https://checkout.paycom.uz"
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

        # Get subject_ids from request body
        try:
            body = json.loads(request.body) if request.body else {}
        except Exception:
            body = {}
        subject_ids = body.get("subject_ids", [])

        if not subject_ids:
            return JsonResponse({"success": False, "error": "No subjects selected"}, status=400)

        subjects = Subject.objects.select_related('olympiad').filter(
            id__in=subject_ids, olympiad__is_active=True, ticket_price__gt=0
        )

        if not subjects.exists():
            return JsonResponse({"success": False, "error": "Subjects not found"}, status=404)

        total_amount = sum(s.ticket_price for s in subjects)
        olympiad = subjects.first().olympiad

        # Cancel any existing pending orders for this participant
        Order.objects.filter(participant=participant, status="pending").update(status="cancelled")

        # Create one order per subject
        # The first order carries the TOTAL amount (used for payment link).
        # Additional orders track individual subjects with their own price.
        subject_list = list(subjects)
        first_order = Order.objects.create(
            participant=participant,
            olympiad=subject_list[0].olympiad,
            subject=subject_list[0],
            total_amount=total_amount,
            status="pending",
            payment_method="payme",
        )

        for subj in subject_list[1:]:
            Order.objects.create(
                participant=participant,
                olympiad=subj.olympiad,
                subject=subj,
                total_amount=subj.ticket_price,
                status="pending",
                payment_method="payme",
            )

        amount_tiyin = int(total_amount * 100)
        pay_url = generate_pay_link(
            order_id=first_order.id,
            amount_tiyin=amount_tiyin,
            return_url=request.build_absolute_uri("/ticket/"),
        )

        return JsonResponse({
            "success": True,
            "order_id": first_order.id,
            "amount": float(total_amount),
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
    # ---------- JSON-RPC helpers ----------
    def _success(self, rpc_id: Any, result: Dict[str, Any]) -> JsonResponse:
        return JsonResponse({"jsonrpc": "2.0", "id": rpc_id, "result": result}, status=200)

    def _error(self, rpc_id: Any, code: int, message: str, data: Optional[str] = None) -> JsonResponse:
        err: Dict[str, Any] = {"code": code, "message": {"ru": message, "uz": message, "en": message}}
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
        auth_header = request.headers.get("Authorization") or request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(auth_header.split(" ", 1)[1]).decode("utf-8")
            username, password = decoded.split(":", 1)
            expected = (getattr(settings, "PAYME_KEY", "") or "").strip()
            return username == "Paycom" and password == expected
        except Exception:
            return False

    # ---------- helpers ----------
    def _now_ms(self) -> int:
        return int(timezone.now().timestamp() * 1000)

    def _get_order_id(self, params: Dict[str, Any]) -> Optional[int]:
        account = params.get("account") or {}
        order_id = account.get("order_id")
        if order_id is None:
            return None
        try:
            return int(order_id)
        except Exception:
            return None

    def _get_amount_tiyin(self, params: Dict[str, Any]) -> Optional[int]:
        amount = params.get("amount")
        if amount is None:
            return None
        try:
            return int(amount)
        except Exception:
            return None

    def _expected_amount_tiyin(self, order: Order) -> int:
        # total_amount stored in SUM; Payme sends TIYIN
        try:
            return int(Decimal(str(order.total_amount)) * Decimal("100"))
        except (InvalidOperation, TypeError):
            return int(Decimal(order.total_amount) * Decimal("100"))

    # ---------- main ----------
    def post(self, request: HttpRequest):
        data = self._parse_json(request)
        if not data:
            return self._error(None, ERROR_INVALID_JSON_RPC_OBJECT, "Invalid JSON-RPC object")

        rpc_id = data.get("id")
        method = data.get("method")
        params = data.get("params") or {}

        # require key always (you already have test key)
        if not (getattr(settings, "PAYME_KEY", None) or "").strip():
            return self._error(rpc_id, ERROR_INSUFFICIENT_PRIVILEGE, "Unauthorized")

        if not self._verify_auth(request):
            return self._error(rpc_id, ERROR_INSUFFICIENT_PRIVILEGE, "Unauthorized")

        handlers = {
            "CheckPerformTransaction": self._check_perform_transaction,
            "CreateTransaction": self._create_transaction,
            "PerformTransaction": self._perform_transaction,
            "CancelTransaction": self._cancel_transaction,
            "CheckTransaction": self._check_transaction,
            "GetStatement": self._get_statement,
        }
        handler = handlers.get(method)
        if not handler:
            return self._error(rpc_id, ERROR_METHOD_NOT_FOUND, f"Method not found: {method}")

        try:
            return handler(rpc_id, params)
        except Exception:
            return self._error(rpc_id, ERROR_INTERNAL_SERVER, "Internal server error")

    # ---------- methods ----------
    def _check_perform_transaction(self, rpc_id: Any, params: Dict[str, Any]) -> JsonResponse:
        order_id = self._get_order_id(params)
        if order_id is None:
            return self._error(rpc_id, ERROR_INVALID_PARAMS, "Invalid Params", "order_id")

        amount_tiyin = self._get_amount_tiyin(params)
        if amount_tiyin is None:
            return self._error(rpc_id, ERROR_INVALID_PARAMS, "Invalid Params", "amount")

        order = Order.objects.filter(id=order_id).first()
        if not order:
            return self._error(rpc_id, ERROR_ORDER_NOT_FOUND, "Order not found", "order_id")

        if order.status == "paid":
            return self._error(rpc_id, ERROR_ORDER_ALREADY_PAID, "Order already paid", "order_id")

        if order.status == "cancelled":
            # blocked -> must be in -31099..-31050 for tests
            return self._error(rpc_id, ERROR_ORDER_NOT_FOUND, "Order is blocked", "order_id")

        expected = self._expected_amount_tiyin(order)
        if amount_tiyin != expected:
            return self._error(rpc_id, ERROR_INVALID_AMOUNT, "Invalid amount", "amount")

        return self._success(rpc_id, {"allow": True})

    def _create_transaction(self, rpc_id: Any, params: Dict[str, Any]) -> JsonResponse:
        order_id = self._get_order_id(params)
        if order_id is None:
            return self._error(rpc_id, ERROR_INVALID_PARAMS, "Invalid Params", "order_id")

        amount_tiyin = self._get_amount_tiyin(params)
        if amount_tiyin is None:
            return self._error(rpc_id, ERROR_INVALID_PARAMS, "Invalid Params", "amount")

        transaction_id = params.get("id")
        if not transaction_id:
            return self._error(rpc_id, ERROR_INVALID_PARAMS, "Invalid Params", "id")

        create_time = params.get("time")
        if create_time is None:
            create_time = self._now_ms()

        with transaction.atomic():
            order = Order.objects.select_for_update().filter(id=order_id).first()
            if not order:
                return self._error(rpc_id, ERROR_ORDER_NOT_FOUND, "Order not found", "order_id")

            expected = self._expected_amount_tiyin(order)
            if amount_tiyin != expected:
                return self._error(rpc_id, ERROR_INVALID_AMOUNT, "Invalid amount", "amount")

            if order.status == "paid":
                return self._error(rpc_id, ERROR_ORDER_ALREADY_PAID, "Order already paid", "order_id")

            if order.status == "cancelled":
                return self._error(rpc_id, ERROR_ORDER_NOT_FOUND, "Order is blocked", "order_id")

            # if already has transaction
            if order.payme_transaction_id:
                # idempotent: same id -> must return SAME create_time/state
                if str(order.payme_transaction_id) == str(transaction_id):
                    stored_ct = int(order.payme_create_time or create_time)
                    stored_state = int(order.payme_state or 1)
                    return self._success(rpc_id, {
                        "create_time": stored_ct,
                        "transaction": str(order.payme_transaction_id),
                        "state": stored_state,
                    })

                # different transaction for same order -> "busy"
                return self._error(rpc_id, ERROR_ORDER_NOT_FOUND, "Order is busy", "order_id")

            # bind new transaction and persist
            order.payme_transaction_id = str(transaction_id)
            order.payme_create_time = int(create_time)
            order.payme_state = 1
            order.save(update_fields=["payme_transaction_id", "payme_create_time", "payme_state"])

        return self._success(rpc_id, {"create_time": int(create_time), "transaction": str(transaction_id), "state": 1})

    def _perform_transaction(self, rpc_id: Any, params: Dict[str, Any]) -> JsonResponse:
        transaction_id = params.get("id")
        if not transaction_id:
            return self._error(rpc_id, ERROR_INVALID_PARAMS, "Invalid Params", "id")

        with transaction.atomic():
            order = Order.objects.select_for_update().filter(payme_transaction_id=str(transaction_id)).first()
            if not order:
                return self._error(rpc_id, ERROR_TRANSACTION_NOT_FOUND, "Transaction not found", "id")

            # if cancelled -> cannot perform
            if order.payme_state in (-1, -2) or order.status == "cancelled":
                stored_cancel_time = int(order.payme_cancel_time or 0)
                stored_state = int(order.payme_state)
                return self._success(rpc_id, {
                    "cancel_time": stored_cancel_time,
                    "transaction": str(transaction_id),
                    "state": stored_state,
                })

            # idempotent: if already performed, return the SAME perform_time
            if order.payme_state == 2 or order.status == "paid":
                pt = int(order.payme_perform_time or 0)
                return self._success(rpc_id, {"perform_time": pt, "transaction": str(transaction_id), "state": 2})

            now_ms = self._now_ms()
            order.status = "paid"
            order.payme_state = 2
            order.payme_perform_time = now_ms
            order.save(update_fields=["status", "payme_state", "payme_perform_time", "updated_at"])

            # sync participant
            if order.participant_id:
                p = order.participant
                p.is_paid = True
                p.paid_at = timezone.now()
                p.save(update_fields=["is_paid", "paid_at"])

        return self._success(rpc_id, {"perform_time": int(now_ms), "transaction": str(transaction_id), "state": 2})

    def _cancel_transaction(self, rpc_id: Any, params: Dict[str, Any]) -> JsonResponse:
        transaction_id = params.get("id")
        if not transaction_id:
            return self._error(rpc_id, ERROR_INVALID_PARAMS, "Invalid Params", "id")

        reason = params.get("reason")

        with transaction.atomic():
            order = Order.objects.select_for_update().filter(payme_transaction_id=str(transaction_id)).first()
            if not order:
                return self._error(rpc_id, ERROR_TRANSACTION_NOT_FOUND, "Transaction not found", "id")

            perform_time_db = int(order.payme_perform_time or 0)
            was_performed = (perform_time_db > 0) or (order.payme_state == 2) or (order.status == "paid")

            # Если уже отменена — вернуть те же значения (идемпотентно),
            # но при необходимости нормализовать state для cancelled.
            if order.status == "cancelled" or order.payme_state in (-1, -2):
                expected_state = -2 if was_performed else -1

                # если у тебя в БД кривой state — исправим один раз, иначе тесты будут падать
                if int(order.payme_state or 0) != expected_state:
                    if not order.payme_cancel_time:
                        order.payme_cancel_time = self._now_ms()
                    order.payme_state = expected_state
                    if order.payme_cancel_reason is None:
                        order.payme_cancel_reason = int(reason) if reason is not None else (5 if was_performed else 3)
                    order.save(update_fields=["payme_state", "payme_cancel_time", "payme_cancel_reason", "updated_at"])

                return self._success(rpc_id, {
                    "cancel_time": int(order.payme_cancel_time or 0),
                    "transaction": str(transaction_id),
                    "state": int(order.payme_state),
                })

            # Первая отмена
            now_ms = self._now_ms()
            state = -2 if was_performed else -1

            if reason is None:
                reason = 5 if was_performed else 3

            order.status = "cancelled"
            order.payme_state = state
            order.payme_cancel_time = now_ms
            order.payme_cancel_reason = int(reason)

            # ВАЖНО: perform_time НЕ трогаем, если was_performed=True (нужно для state=-2)
            if not was_performed:
                order.payme_perform_time = 0

            order.save(update_fields=[
                "status",
                "payme_state",
                "payme_cancel_time",
                "payme_cancel_reason",
                "payme_perform_time",
                "updated_at",
            ])

            if was_performed and order.participant_id:
                p = order.participant
                p.is_paid = False
                p.paid_at = None
                p.save(update_fields=["is_paid", "paid_at"])

        return self._success(rpc_id, {
            "cancel_time": int(now_ms),
            "transaction": str(transaction_id),
            "state": int(state),
        })

    def _get_statement(self, rpc_id: Any, params: Dict[str, Any]) -> JsonResponse:
        from_ts = params.get("from")
        to_ts = params.get("to")

        # validate
        try:
            from_ts = int(from_ts)
            to_ts = int(to_ts)
        except Exception:
            return self._error(rpc_id, ERROR_INVALID_PARAMS, "Invalid Params", "from/to")

        if from_ts > to_ts:
            return self._error(rpc_id, ERROR_INVALID_PARAMS, "Invalid Params", "from>to")

        # Select orders with payme_create_time in range
        qs = Order.objects.filter(
            payme_transaction_id__isnull=False,
            payme_create_time__isnull=False,
            payme_create_time__gte=from_ts,
            payme_create_time__lte=to_ts,
        ).select_related("participant")

        transactions = []
        for o in qs:
            create_time = int(o.payme_create_time or 0)
            perform_time = int(o.payme_perform_time or 0)
            cancel_time = int(o.payme_cancel_time or 0)
            state = int(o.payme_state or 1)

            # amount in tiyin
            try:
                amount_tiyin = int(Decimal(str(o.total_amount)) * Decimal("100"))
            except Exception:
                amount_tiyin = int(o.total_amount * 100)

            tx = {
                "id": str(o.payme_transaction_id),          # Payme tx id
                "time": create_time,                        # statement time
                "amount": amount_tiyin,
                "account": {"order_id": int(o.id)},
                "create_time": create_time,
                "perform_time": perform_time if perform_time > 0 else 0,
                "cancel_time": cancel_time if state in (-1, -2) else 0,
                "transaction": str(o.payme_transaction_id),
                "state": state,
            }

            if state in (-1, -2) and o.payme_cancel_reason is not None:
                tx["reason"] = int(o.payme_cancel_reason)

            transactions.append(tx)

        return self._success(rpc_id, {"transactions": transactions})




    def _check_transaction(self, rpc_id: Any, params: Dict[str, Any]) -> JsonResponse:
        transaction_id = params.get("id")
        if not transaction_id:
            return self._error(rpc_id, ERROR_INVALID_PARAMS, "Invalid Params", "id")

        order = Order.objects.filter(payme_transaction_id=str(transaction_id)).first()
        if not order:
            return self._error(rpc_id, ERROR_TRANSACTION_NOT_FOUND, "Transaction not found", "id")

        state = int(order.payme_state or 1)

        create_time = int(order.payme_create_time or 0)
        perform_time_db = int(order.payme_perform_time or 0)
        cancel_time = int(order.payme_cancel_time or 0)

        # обязательный timestamp для create_time
        if create_time <= 0:
            if getattr(order, "created_at", None):
                create_time = int(order.created_at.timestamp() * 1000)
            else:
                create_time = self._now_ms()

        # обязательный timestamp для cancel_time в отменённых состояниях
        if state in (-1, -2) and cancel_time <= 0:
            if getattr(order, "updated_at", None):
                cancel_time = int(order.updated_at.timestamp() * 1000)
            else:
                cancel_time = self._now_ms()

        # ВАЖНО:
        # state -1 => отмена ДО выполнения => perform_time должен быть 0
        if state == -1:
            perform_time = 0
        # state -2 => отмена ПОСЛЕ выполнения => perform_time должен быть timestamp
        elif state == -2:
            perform_time = perform_time_db if perform_time_db > 0 else create_time
        # state 2 => выполнена
        elif state == 2:
            perform_time = perform_time_db if perform_time_db > 0 else create_time
        else:
            perform_time = 0

        return self._success(rpc_id, {
            "create_time": create_time,
            "perform_time": perform_time,
            "cancel_time": cancel_time if state in (-1, -2) else 0,
            "transaction": str(transaction_id),
            "state": state,
            "reason": int(order.payme_cancel_reason) if (state in (-1, -2) and order.payme_cancel_reason is not None) else None,
        })


# ============================================================================
# CLICK PAYMENT INTEGRATION
# ============================================================================

import hashlib

# Click error codes
CLICK_ERROR_SUCCESS = 0
CLICK_ERROR_SIGN_CHECK_FAILED = -1
CLICK_ERROR_INVALID_AMOUNT = -2
CLICK_ERROR_ACTION_NOT_FOUND = -3
CLICK_ERROR_ALREADY_PAID = -4
CLICK_ERROR_USER_NOT_FOUND = -5
CLICK_ERROR_TRANSACTION_NOT_FOUND = -6
CLICK_ERROR_UPDATE_FAILED = -7
CLICK_ERROR_REQUEST_FROM_CLICK = -8
CLICK_ERROR_TRANSACTION_CANCELLED = -9


def generate_click_pay_link(order_id: int, amount: int, return_url: Optional[str] = None) -> str:
    """
    Generate Click checkout URL.
    
    amount: integer in SUM (not tiyin)
    """
    service_id = getattr(settings, "CLICK_SERVICE_ID", None)
    merchant_id = getattr(settings, "CLICK_MERCHANT_ID", None)
    
    if not service_id:
        raise RuntimeError("CLICK_SERVICE_ID is not set")
    
    base_url = "https://my.click.uz/services/pay"
    params = f"?service_id={service_id}&merchant_id={merchant_id}&amount={int(amount)}&transaction_param={order_id}"
    
    if return_url:
        import urllib.parse
        params += f"&return_url={urllib.parse.quote(return_url)}"
    
    full_url = base_url + params
    print(f"[CLICK DEBUG] Generated URL: {full_url}")
    print(f"[CLICK DEBUG] service_id={service_id}, merchant_id={merchant_id}, amount={amount}, order_id={order_id}")
    
    return full_url


@method_decorator(csrf_exempt, name="dispatch")
class ClickCallbackView(View):
    """
    Click Merchant API Callback View.
    
    Handles Prepare (action=0) and Complete (action=1) requests.
    """
    
    def _response(self, click_trans_id, merchant_trans_id, merchant_prepare_id, error, error_note=""):
        return JsonResponse({
            "click_trans_id": click_trans_id,
            "merchant_trans_id": str(merchant_trans_id),
            "merchant_prepare_id": merchant_prepare_id,
            "error": error,
            "error_note": error_note,
        })
    
    def _verify_sign(self, data: Dict[str, Any], action: int) -> bool:
        """Verify Click signature using MD5."""
        secret_key = getattr(settings, "CLICK_SECRET_KEY", "")
        
        click_trans_id = data.get("click_trans_id", "")
        service_id = data.get("service_id", "")
        merchant_trans_id = data.get("merchant_trans_id", "")
        amount = data.get("amount", "")
        sign_time = data.get("sign_time", "")
        sign_string = data.get("sign_string", "")
        
        if action == 0:
            # Prepare: md5(click_trans_id + service_id + SECRET_KEY + merchant_trans_id + amount + action + sign_time)
            check_string = f"{click_trans_id}{service_id}{secret_key}{merchant_trans_id}{amount}{action}{sign_time}"
        else:
            # Complete: md5(click_trans_id + service_id + SECRET_KEY + merchant_trans_id + merchant_prepare_id + amount + action + sign_time)
            merchant_prepare_id = data.get("merchant_prepare_id", "")
            check_string = f"{click_trans_id}{service_id}{secret_key}{merchant_trans_id}{merchant_prepare_id}{amount}{action}{sign_time}"
        
        expected_sign = hashlib.md5(check_string.encode()).hexdigest()
        return expected_sign == sign_string
    
    def post(self, request: HttpRequest):
        # Parse form data (Click sends application/x-www-form-urlencoded)
        data = request.POST.dict()
        
        click_trans_id = int(data.get("click_trans_id", 0))
        service_id = int(data.get("service_id", 0))
        merchant_trans_id = data.get("merchant_trans_id", "")
        amount = data.get("amount", "0")
        action = int(data.get("action", -1))
        sign_time = data.get("sign_time", "")
        sign_string = data.get("sign_string", "")
        error = int(data.get("error", 0))
        error_note = data.get("error_note", "")
        
        # Parse order_id from merchant_trans_id
        try:
            order_id = int(merchant_trans_id)
        except (ValueError, TypeError):
            return self._response(click_trans_id, merchant_trans_id, 0, CLICK_ERROR_USER_NOT_FOUND, "Invalid order ID")
        
        # Verify signature
        if not self._verify_sign(data, action):
            return self._response(click_trans_id, merchant_trans_id, 0, CLICK_ERROR_SIGN_CHECK_FAILED, "Invalid signature")
        
        # Get order
        order = Order.objects.filter(id=order_id).first()
        if not order:
            return self._response(click_trans_id, merchant_trans_id, 0, CLICK_ERROR_USER_NOT_FOUND, "Order not found")
        
        # Verify amount
        try:
            expected_amount = float(order.total_amount)
            received_amount = float(amount)
            if abs(expected_amount - received_amount) > 0.01:
                return self._response(click_trans_id, merchant_trans_id, 0, CLICK_ERROR_INVALID_AMOUNT, "Invalid amount")
        except (ValueError, TypeError):
            return self._response(click_trans_id, merchant_trans_id, 0, CLICK_ERROR_INVALID_AMOUNT, "Invalid amount format")
        
        if action == 0:
            # PREPARE
            return self._handle_prepare(order, click_trans_id, merchant_trans_id, error)
        elif action == 1:
            # COMPLETE
            merchant_prepare_id = int(data.get("merchant_prepare_id", 0))
            return self._handle_complete(order, click_trans_id, merchant_trans_id, merchant_prepare_id, error)
        else:
            return self._response(click_trans_id, merchant_trans_id, 0, CLICK_ERROR_ACTION_NOT_FOUND, "Unknown action")
    
    def _handle_prepare(self, order: Order, click_trans_id: int, merchant_trans_id: str, error: int):
        """Handle Prepare request (action=0)."""
        
        # Check if already paid
        if order.status == "paid":
            return self._response(click_trans_id, merchant_trans_id, order.id, CLICK_ERROR_ALREADY_PAID, "Already paid")
        
        # Check if cancelled
        if order.status == "cancelled":
            return self._response(click_trans_id, merchant_trans_id, order.id, CLICK_ERROR_TRANSACTION_CANCELLED, "Order cancelled")
        
        # Check if order already has a different Click transaction
        if order.click_trans_id and order.click_trans_id != click_trans_id:
            # Reset for new transaction
            pass
        
        # Save Click transaction ID
        order.click_trans_id = click_trans_id
        order.click_prepare_id = order.id  # We use order.id as prepare_id
        order.payment_method = "click"
        order.save(update_fields=["click_trans_id", "click_prepare_id", "payment_method"])
        
        return self._response(click_trans_id, merchant_trans_id, order.id, CLICK_ERROR_SUCCESS, "Success")
    
    def _handle_complete(self, order: Order, click_trans_id: int, merchant_trans_id: str, merchant_prepare_id: int, error: int):
        """Handle Complete request (action=1)."""
        
        # Check if this is a cancellation from Click
        if error < 0:
            # Click is canceling this payment
            if order.status != "paid":
                order.status = "cancelled"
                order.save(update_fields=["status", "updated_at"])
            return self._response(click_trans_id, merchant_trans_id, merchant_prepare_id, CLICK_ERROR_TRANSACTION_CANCELLED, "Cancelled")
        
        # Check if already paid
        if order.status == "paid":
            return self._response(click_trans_id, merchant_trans_id, merchant_prepare_id, CLICK_ERROR_ALREADY_PAID, "Already paid")
        
        # Check if cancelled
        if order.status == "cancelled":
            return self._response(click_trans_id, merchant_trans_id, merchant_prepare_id, CLICK_ERROR_TRANSACTION_CANCELLED, "Order cancelled")
        
        # Verify prepare_id matches
        if order.click_prepare_id != merchant_prepare_id:
            return self._response(click_trans_id, merchant_trans_id, merchant_prepare_id, CLICK_ERROR_TRANSACTION_NOT_FOUND, "Prepare ID mismatch")
        
        # Mark as paid
        with transaction.atomic():
            order.status = "paid"
            order.save(update_fields=["status", "updated_at"])
            
            # Update participant
            if order.participant_id:
                p = order.participant
                p.is_paid = True
                p.paid_at = timezone.now()
                p.save(update_fields=["is_paid", "paid_at"])
        
        return self._response(click_trans_id, merchant_trans_id, merchant_prepare_id, CLICK_ERROR_SUCCESS, "Success")


class InitiateClickPaymentView(View):
    """
    Create order and return Click payment URL.
    
    POST /api/payment/initiate-click/
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
        
        # Get subject_ids from request body
        try:
            body = json.loads(request.body) if request.body else {}
        except Exception:
            body = {}
        subject_ids = body.get("subject_ids", [])

        if not subject_ids:
            return JsonResponse({"success": False, "error": "No subjects selected"}, status=400)

        subjects = Subject.objects.select_related('olympiad').filter(
            id__in=subject_ids, olympiad__is_active=True, ticket_price__gt=0
        )

        if not subjects.exists():
            return JsonResponse({"success": False, "error": "Subjects not found"}, status=404)

        total_amount = sum(s.ticket_price for s in subjects)
        olympiad = subjects.first().olympiad
        
        # Cancel any existing pending orders for this participant
        Order.objects.filter(participant=participant, status="pending").update(status="cancelled")
        
        # Create one order per subject
        first_order = None
        for subj in subjects:
            order = Order.objects.create(
                participant=participant,
                olympiad=subj.olympiad,
                subject=subj,
                total_amount=subj.ticket_price,
                status="pending",
                payment_method="click",
            )
            if first_order is None:
                first_order = order
        
        amount_sum = int(total_amount)
        
        pay_url = generate_click_pay_link(
            order_id=first_order.id,
            amount=amount_sum,
            return_url=request.build_absolute_uri("/ticket/"),
        )
        
        return JsonResponse({
            "success": True,
            "order_id": first_order.id,
            "amount": float(total_amount),
            "pay_url": pay_url,
        })