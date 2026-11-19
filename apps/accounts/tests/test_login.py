from datetime import timedelta
from unittest import mock

from django.contrib.sessions.models import Session
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from apps.accounts.models import User

from .helpers import AUTH, PASSWORD, AuthAPITestCase, make_verified_user


class LoginTests(AuthAPITestCase):
    def setUp(self):
        super().setUp()
        self.user = make_verified_user(email="asha@example.com", mobile="9876543210")

    def test_login_by_email_and_mobile(self):
        for identifier in ("asha@example.com", "ASHA@example.com", "9876543210"):
            client = APIClient()
            r = self.login(identifier, client=client)
            self.assertEqual(r.status_code, 200, identifier)
            self.assertEqual(r.json()["role"], "CITIZEN")
            self.assertEqual(client.get(f"{AUTH}/me").status_code, 200)

    def test_invalid_credentials_are_indistinguishable(self):
        wrong = self.login("asha@example.com", PASSWORD + "x")
        unknown = self.login("nobody@example.com")
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(unknown.status_code, 401)
        self.assertEqual(wrong.json(), unknown.json())

    def test_unverified_account_cannot_log_in(self):
        User.objects.create_user(email="u@example.com", password=PASSWORD, name="U")
        self.assertEqual(self.login("u@example.com").status_code, 401)

    def test_inactive_account_cannot_log_in(self):
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.login("asha@example.com").status_code, 401)

    def test_me_requires_authentication(self):
        self.assertEqual(self.client.get(f"{AUTH}/me").status_code, 403)

    def test_logout_invalidates_session(self):
        self.login("asha@example.com")
        self.assertEqual(self.client.post(f"{AUTH}/logout").status_code, 200)
        self.assertEqual(self.client.get(f"{AUTH}/me").status_code, 403)
        self.assertEqual(Session.objects.count(), 0)

    def test_expired_session_is_rejected(self):
        self.login("asha@example.com")
        Session.objects.update(expire_date=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get(f"{AUTH}/me").status_code, 403)

    def test_activity_extends_the_idle_timeout(self):
        self.login("asha@example.com")
        Session.objects.update(expire_date=timezone.now() + timedelta(seconds=60))
        self.client.get(f"{AUTH}/me")
        remaining = (Session.objects.get().expire_date - timezone.now()).total_seconds()
        self.assertTrue(880 < remaining <= 900, remaining)

    def test_session_cookie_flags(self):
        cookie = self.login("asha@example.com").cookies["sessionid"]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")

    def test_csrf_enforced_on_public_and_authenticated_posts(self):
        client = APIClient(enforce_csrf_checks=True)
        self.assertEqual(self.login("asha@example.com", client=client).status_code, 403)

        client.get(f"{AUTH}/csrf")
        token = client.cookies["csrftoken"].value
        r = self.login("asha@example.com", client=client, HTTP_X_CSRFTOKEN=token)
        self.assertEqual(r.status_code, 200)

        self.assertEqual(client.post(f"{AUTH}/logout").status_code, 403)
        token = client.cookies["csrftoken"].value  # rotated on login
        self.assertEqual(client.post(f"{AUTH}/logout", HTTP_X_CSRFTOKEN=token).status_code, 200)

    def test_login_throttled_per_ip(self):
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {"login": "2/min"}):
            self.assertEqual(self.login("asha@example.com", PASSWORD + "x").status_code, 401)
            self.assertEqual(self.login("asha@example.com", PASSWORD + "x").status_code, 401)
            self.assertEqual(self.login("asha@example.com", PASSWORD + "x").status_code, 429)

    def test_login_throttled_per_identifier(self):
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {"login_identifier": "2/min"}):
            self.login("asha@example.com", PASSWORD + "x")
            self.login("asha@example.com", PASSWORD + "x")
            self.assertEqual(self.login("asha@example.com", PASSWORD + "x").status_code, 429)
            self.assertEqual(self.login("other@example.com", PASSWORD + "x").status_code, 401)
