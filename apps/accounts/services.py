import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.module_loading import import_string

from .models import Role, User, VerificationOTP, _clean_email, _clean_mobile

logger = logging.getLogger(__name__)


class DuplicateAccount(Exception):
    pass


class InvalidOTP(Exception):
    pass


class OTPDeliveryError(Exception):
    pass


def normalize_identifier(value):
    value = (value or "").strip()
    if "@" in value:
        return "email", _clean_email(value)
    return "mobile", _clean_mobile(value)


def find_user(identifier):
    channel, value = normalize_identifier(identifier)
    if not value:
        return None
    return User.objects.filter(**{channel: value}).first()


def _hash_otp(user_id, code):
    return salted_hmac("accounts.otp", f"{user_id}:{code}", algorithm="sha256").hexdigest()


def _has_pending_otp(user):
    otp = user.otps.filter(verified_at__isnull=True).order_by("-created_at").first()
    return bool(
        otp and otp.expires_at > timezone.now() and otp.attempt_count < settings.OTP_MAX_ATTEMPTS
    )


def issue_otp(user):
    """Create a fresh OTP, replacing any unverified one, and deliver it. Returns the channel."""
    n = settings.OTP_LENGTH
    code = f"{secrets.randbelow(10**n):0{n}d}"
    with transaction.atomic():
        VerificationOTP.objects.filter(user=user, verified_at__isnull=True).delete()
        VerificationOTP.objects.create(
            user=user,
            otp_hash=_hash_otp(user.pk, code),
            expires_at=timezone.now() + timedelta(seconds=settings.OTP_TTL_SECONDS),
        )
    channel, recipient = ("email", user.email) if user.email else ("mobile", user.mobile)
    try:
        import_string(settings.OTP_GATEWAY)().send(channel=channel, recipient=recipient, code=code)
    except Exception:
        # Deliberately no exc_info and no code: nothing sensitive reaches the logs.
        logger.error("OTP delivery failed for user_id=%s", user.pk)
        raise OTPDeliveryError from None
    return channel


def register_citizen(*, name, email, mobile, password):
    """Always creates a CITIZEN. Exactly one of email/mobile is set (validated upstream)."""
    channel, value = ("email", email) if email else ("mobile", mobile)
    try:
        with transaction.atomic():
            existing = User.objects.select_for_update().filter(**{channel: value}).first()
            if existing is not None:
                # A live pending registration is never overwritten (prevents pre-registration
                # hijacking). A stale/exhausted one is replaced.
                if existing.is_verified or existing.role != Role.CITIZEN or _has_pending_otp(existing):
                    raise DuplicateAccount
                existing.delete()
            user = User.objects.create_user(email=email, mobile=mobile, password=password, name=name)
    except IntegrityError:
        raise DuplicateAccount from None
    try:
        return issue_otp(user)
    except OTPDeliveryError:
        user.delete()
        raise


def verify_otp(*, identifier, code):
    user = find_user(identifier)
    if user is None or user.is_verified or user.role != Role.CITIZEN:
        raise InvalidOTP
    ok = False
    with transaction.atomic():
        otp = (
            VerificationOTP.objects.select_for_update()
            .filter(user=user, verified_at__isnull=True)
            .order_by("-created_at")
            .first()
        )
        if (
            otp is not None
            and otp.expires_at > timezone.now()
            and otp.attempt_count < settings.OTP_MAX_ATTEMPTS
        ):
            otp.attempt_count += 1  # counted (and committed) even on a wrong guess
            ok = constant_time_compare(otp.otp_hash, _hash_otp(user.pk, code))
            if ok:
                otp.verified_at = timezone.now()
                user.is_verified = True
                user.save(update_fields=["is_verified"])
            otp.save(update_fields=["attempt_count", "verified_at"])
    if not ok:
        raise InvalidOTP
    return user
