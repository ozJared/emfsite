import json
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from django.conf import settings

PAYSTACK_CHANNELS = ["card", "bank_transfer"]


class PaystackError(Exception):
    pass


def is_configured():
    mode = settings.PAYSTACK_MODE
    expected_prefix = {"test": "sk_test_", "live": "sk_live_"}.get(mode)
    return bool(expected_prefix and settings.PAYSTACK_SECRET_KEY.startswith(expected_prefix))


def currency_is_supported(site_currency):
    return settings.PAYSTACK_CURRENCY == "NGN" and site_currency in {"₦", "NGN"}


def amount_in_minor_units(amount):
    value = Decimal(amount) * 100
    if value != value.to_integral_value():
        raise PaystackError("The order total cannot be represented in the selected payment currency.")
    return int(value)


def _provider_error_message(error_response, payload):
    messages = []
    sensitive_values = [settings.PAYSTACK_SECRET_KEY]
    if isinstance(payload, dict):
        sensitive_values.extend(
            value for value in (payload.get("email"), payload.get("reference")) if isinstance(value, str)
        )

    def collect(value, depth=0):
        if depth > 3:
            return
        if isinstance(value, dict):
            for key, nested in value.items():
                if key in {"message", "error", "detail", "errors"}:
                    collect(nested, depth + 1)
        elif isinstance(value, list):
            for nested in value[:5]:
                collect(nested, depth + 1)
        elif isinstance(value, str):
            text = " ".join(value.split())
            for sensitive_value in sensitive_values:
                if sensitive_value:
                    text = text.replace(sensitive_value, "[redacted]")
            if text and text not in messages:
                messages.append(text)

    collect(error_response)
    return "; ".join(messages)[:240]


def _request_json(method, path, payload=None):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        settings.PAYSTACK_API_BASE + path,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "EMFStore-Django/1.0",
        },
    )
    try:
        with urlopen(request, timeout=settings.PAYSTACK_TIMEOUT) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = ""
        error_body = b""
        try:
            error_body = exc.read()
            error_response = json.loads(error_body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            error_response = {}
        detail = _provider_error_message(error_response, payload)
        if detail:
            suffix = f": {detail}"
        else:
            content_type = exc.headers.get_content_type() if exc.headers else "unknown"
            diagnostics = [f"content type {content_type}", f"body {len(error_body)} bytes"]
            if isinstance(error_response, dict):
                diagnostics.append(f"JSON keys {','.join(sorted(error_response.keys())[:12]) or 'none'}")
            elif isinstance(error_response, list):
                diagnostics.append(f"JSON array with {len(error_response)} items")
            else:
                diagnostics.append(f"JSON type {type(error_response).__name__}")
            if exc.headers:
                request_id = exc.headers.get("x-request-id") or exc.headers.get("x-paystack-request-id")
                if request_id and len(request_id) <= 128 and all(
                    character.isalnum() or character in "-_.:" for character in request_id
                ):
                    diagnostics.append(f"request ID {request_id}")
            suffix = f" ({'; '.join(diagnostics)})"
        raise PaystackError(f"Paystack returned HTTP {exc.code}{suffix}.") from exc
    except (URLError, TimeoutError) as exc:
        raise PaystackError("Could not reach Paystack. Please try again.") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PaystackError("Paystack returned an unreadable response.") from exc
    if not isinstance(result, dict) or not result.get("status"):
        raise PaystackError("Paystack could not process the payment request.")
    data = result.get("data")
    if not isinstance(data, dict):
        raise PaystackError("Paystack returned an invalid payment response.")
    return data


def initialize_transaction(reference, email, amount, callback_url):
    if not is_configured():
        raise PaystackError("Online payments are not configured. Please contact the store.")
    data = _request_json("POST", "/transaction/initialize", {
        "reference": reference,
        "email": email,
        "amount": amount_in_minor_units(amount),
        "currency": settings.PAYSTACK_CURRENCY,
        "channels": PAYSTACK_CHANNELS,
        "callback_url": callback_url,
    })
    authorization_url = data.get("authorization_url", "")
    parsed = urlparse(authorization_url)
    if parsed.scheme != "https" or parsed.hostname != "checkout.paystack.com":
        raise PaystackError("Paystack returned an invalid checkout address.")
    if data.get("reference") != reference:
        raise PaystackError("Paystack returned an unexpected payment reference.")
    return authorization_url


def verify_transaction(reference):
    if not is_configured():
        raise PaystackError("Online payments are not configured.")
    return _request_json("GET", f"/transaction/verify/{quote(reference, safe='')}")


def verify_webhook_signature(payload, signature):
    import hashlib
    import hmac

    if not is_configured():
        return False
    expected = hmac.new(
        settings.PAYSTACK_SECRET_KEY.encode("utf-8"),
        payload,
        hashlib.sha512,
    ).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def successful_payment_matches(order, reference, data):
    if not isinstance(data, dict):
        return False
    try:
        amount = int(data.get("amount"))
    except (TypeError, ValueError):
        return False
    return (
        data.get("status") == "success"
        and data.get("reference") == reference
        and data.get("currency") == settings.PAYSTACK_CURRENCY
        and amount == amount_in_minor_units(order.total)
    )
