import json
import logging
import urllib.request

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import send_mail
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)

SMTP_BACKEND = "django.core.mail.backends.smtp.EmailBackend"


class DeliveryError(Exception):
    """Generic delivery failure. Never carries provider responses, addresses or secrets."""


class SMSProvider:
    """Pluggable SMS backend. Implementations must raise on failure and must not log secrets."""

    def send(self, *, to, message):
        raise NotImplementedError


class HTTPSMSProvider(SMSProvider):
    """Generic JSON-over-HTTPS provider driven entirely by environment settings.

    The request shape is a placeholder until the team selects a real SMS provider;
    subclass SMSProvider (or adjust this class) to match that provider's API.
    """

    def send(self, *, to, message):
        url, key = settings.SMS_API_URL, settings.SMS_API_KEY
        if not url.startswith("https://") or not key:
            raise ImproperlyConfigured("SMS_API_URL (https) and SMS_API_KEY must be set.")
        payload = json.dumps({"to": to, "from": settings.SMS_SENDER_ID, "message": message}).encode()
        request = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10):  # noqa: S310 (https enforced above)
                pass
        except Exception:
            raise DeliveryError("sms") from None


def send_email(*, to, subject, body):
    if settings.EMAIL_BACKEND == SMTP_BACKEND and not settings.EMAIL_HOST:
        raise ImproperlyConfigured("EMAIL_HOST is not configured.")
    try:
        sent = send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to], fail_silently=False)
    except Exception:
        raise DeliveryError("email") from None
    if not sent:
        raise DeliveryError("email")


def send_sms(*, to, message):
    if not settings.SMS_PROVIDER:
        raise ImproperlyConfigured("No SMS provider configured; mobile delivery is unavailable.")
    try:
        provider = import_string(settings.SMS_PROVIDER)()
    except ImportError:
        raise ImproperlyConfigured("SMS_PROVIDER is invalid.") from None
    try:
        provider.send(to=to, message=message)
    except ImproperlyConfigured:
        raise
    except Exception:
        raise DeliveryError("sms") from None


def deliver(*, channel, address, subject, body):
    if channel == "email":
        send_email(to=address, subject=subject, body=body)
    elif channel == "mobile":
        send_sms(to=address, message=body)
    else:
        raise DeliveryError("unknown channel")
