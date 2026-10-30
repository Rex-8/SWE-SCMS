import secrets

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.gateways import LocMemOTPGateway
from apps.accounts.models import User

# Random per test run; never a hardcoded credential.
PASSWORD = secrets.token_urlsafe(16)
NUMERIC_ONLY = "1" * 8  # fails NumericPasswordValidator

AUTH = "/api/v1/auth"


def make_verified_user(*, email=None, mobile=None, role="CITIZEN", name="Test User"):
    return User.objects.create_user(
        email=email, mobile=mobile, password=PASSWORD, name=name, role=role, is_verified=True
    )


@override_settings(OTP_GATEWAY="apps.accounts.gateways.LocMemOTPGateway")
class AuthAPITestCase(TestCase):
    def setUp(self):
        cache.clear()  # throttle counters live in the cache
        LocMemOTPGateway.outbox.clear()
        self.client = APIClient()

    def register(self, **overrides):
        """Pass a key as None to omit it from the payload."""
        data = {"name": "Asha", "email": "asha@example.com", "password": PASSWORD}
        for key, value in overrides.items():
            if value is None:
                data.pop(key, None)
            else:
                data[key] = value
        return self.client.post(f"{AUTH}/register", data, format="json")

    def verify(self, identifier, code):
        return self.client.post(
            f"{AUTH}/verify-otp", {"identifier": identifier, "otp": code}, format="json"
        )

    def login(self, identifier, password=PASSWORD, client=None, **extra):
        return (client or self.client).post(
            f"{AUTH}/login", {"identifier": identifier, "password": password}, format="json", **extra
        )

    def last_code(self):
        return LocMemOTPGateway.outbox[-1]["code"]

    @staticmethod
    def wrong_code(code):
        return "000000" if code != "000000" else "111111"
