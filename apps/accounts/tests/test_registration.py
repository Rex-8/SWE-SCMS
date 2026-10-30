from datetime import timedelta
from unittest import mock

from django.test import override_settings
from django.utils import timezone
from rest_framework.throttling import SimpleRateThrottle

from apps.accounts.gateways import LocMemOTPGateway, OTPGateway
from apps.accounts.models import Role, User, VerificationOTP

from .helpers import NUMERIC_ONLY, PASSWORD, AuthAPITestCase, make_verified_user


class FailingGateway(OTPGateway):
    last_code = None

    def send(self, *, channel, recipient, code):
        FailingGateway.last_code = code
        raise RuntimeError("gateway down")


class RegistrationTests(AuthAPITestCase):
    def test_register_with_email(self):
        r = self.register()
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["channel"], "email")
        user = User.objects.get(email="asha@example.com")
        self.assertEqual(user.role, Role.CITIZEN)
        self.assertFalse(user.is_verified)
        self.assertEqual(len(LocMemOTPGateway.outbox), 1)
        self.assertEqual(LocMemOTPGateway.outbox[0]["recipient"], "asha@example.com")
        self.assertNotIn(self.last_code(), r.content.decode())

    def test_register_with_mobile(self):
        r = self.register(email=None, mobile="9876543210")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["channel"], "mobile")
        self.assertTrue(User.objects.filter(mobile="9876543210").exists())

    def test_requires_exactly_one_contact(self):
        self.assertEqual(self.register(email=None).status_code, 400)
        self.assertEqual(self.register(mobile="9876543210").status_code, 400)
        self.assertEqual(User.objects.count(), 0)

    def test_weak_password_rejected(self):
        r = self.register(password=NUMERIC_ONLY)
        self.assertEqual(r.status_code, 400)
        self.assertIn("password", r.json())
        self.assertEqual(User.objects.count(), 0)

    def test_password_is_hashed(self):
        self.register()
        user = User.objects.get(email="asha@example.com")
        self.assertNotIn(PASSWORD, user.password)
        self.assertTrue(user.password.startswith("argon2$"))

    def test_cannot_register_privileged_account(self):
        r = self.register(role="ADMIN", is_staff=True, is_superuser=True, is_verified=True)
        self.assertEqual(r.status_code, 201)
        user = User.objects.get(email="asha@example.com")
        self.assertEqual(user.role, Role.CITIZEN)
        self.assertFalse(user.is_staff or user.is_superuser or user.is_verified)

    def test_duplicate_verified_account_rejected(self):
        make_verified_user(email="asha@example.com")
        self.assertEqual(self.register().status_code, 409)

    def test_duplicate_pending_registration_rejected(self):
        self.assertEqual(self.register().status_code, 201)
        self.assertEqual(self.register().status_code, 409)
        self.assertEqual(len(LocMemOTPGateway.outbox), 1)

    def test_stale_pending_registration_is_replaced(self):
        self.register()
        VerificationOTP.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.register().status_code, 201)
        self.assertEqual(User.objects.filter(email="asha@example.com").count(), 1)
        self.assertEqual(len(LocMemOTPGateway.outbox), 2)

    def test_registration_throttled_per_identifier(self):
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {"register_identifier": "1/hour"}):
            self.assertEqual(self.register().status_code, 201)
            self.assertEqual(self.register().status_code, 429)

    @override_settings(OTP_GATEWAY="apps.accounts.tests.test_registration.FailingGateway")
    def test_delivery_failure_returns_503_and_leaves_no_user(self):
        with self.assertLogs("apps.accounts.services", level="ERROR") as logs:
            r = self.register()
        self.assertEqual(r.status_code, 503)
        self.assertFalse(User.objects.filter(email="asha@example.com").exists())
        self.assertNotIn(FailingGateway.last_code, "\n".join(logs.output))
        self.assertNotIn(PASSWORD, "\n".join(logs.output))


class OTPVerificationTests(AuthAPITestCase):
    def setUp(self):
        super().setUp()
        self.register()
        self.code = self.last_code()
        self.user = User.objects.get(email="asha@example.com")

    def test_otp_format_and_storage(self):
        self.assertRegex(self.code, r"^\d{6}$")
        otp = VerificationOTP.objects.get(user=self.user)
        self.assertEqual(len(otp.otp_hash), 64)
        self.assertNotEqual(otp.otp_hash, self.code)

    def test_successful_verification_enables_login(self):
        self.assertEqual(self.login("asha@example.com").status_code, 401)
        r = self.verify("asha@example.com", self.code)
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_verified)
        self.assertIsNotNone(VerificationOTP.objects.get(user=self.user).verified_at)
        self.assertEqual(self.login("asha@example.com").status_code, 200)

    def test_identifier_is_case_insensitive(self):
        self.assertEqual(self.verify("ASHA@Example.com", self.code).status_code, 200)

    def test_verify_by_mobile(self):
        LocMemOTPGateway.outbox.clear()
        self.register(name="Ravi", email=None, mobile="9123456780")
        self.assertEqual(self.verify("9123456780", self.last_code()).status_code, 200)

    def test_wrong_code_rejected_and_counted(self):
        r = self.verify("asha@example.com", self.wrong_code(self.code))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(VerificationOTP.objects.get(user=self.user).attempt_count, 1)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_verified)

    def test_expired_code_rejected(self):
        VerificationOTP.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.verify("asha@example.com", self.code).status_code, 400)

    def test_attempt_limit_locks_the_code(self):
        for _ in range(5):
            self.assertEqual(self.verify("asha@example.com", self.wrong_code(self.code)).status_code, 400)
        self.assertEqual(self.verify("asha@example.com", self.code).status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_verified)

    def test_code_cannot_be_reused(self):
        self.assertEqual(self.verify("asha@example.com", self.code).status_code, 200)
        self.assertEqual(self.verify("asha@example.com", self.code).status_code, 400)

    def test_unknown_identifier_gives_same_response_as_wrong_code(self):
        unknown = self.verify("nobody@example.com", self.code)
        wrong = self.verify("asha@example.com", self.wrong_code(self.code))
        self.assertEqual(unknown.status_code, wrong.status_code)
        self.assertEqual(unknown.json(), wrong.json())

    def test_verify_is_throttled_per_identifier(self):
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {"otp_identifier": "2/hour"}):
            self.verify("asha@example.com", self.wrong_code(self.code))
            self.verify("asha@example.com", self.wrong_code(self.code))
            self.assertEqual(self.verify("asha@example.com", self.code).status_code, 429)

    def test_happy_path_logs_nothing(self):
        LocMemOTPGateway.outbox.clear()
        with self.assertNoLogs(level="INFO"):
            self.register(name="Ravi", email="ravi@example.com")
            self.verify("ravi@example.com", self.last_code())
