import secrets
from datetime import timedelta  # noqa: F401  (kept for readers extending the timeout tests)

from django.conf import settings
from django.contrib.sessions.models import Session
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.complaints.models import Complaint, ComplaintStatus
from apps.complaints.tests.helpers import ComplaintAPITestCase
from apps.complaints.tests.test_status_workflow import client_for

from .helpers import AUTH, PASSWORD, AuthAPITestCase, make_verified_user


class SessionSecurityTests(AuthAPITestCase):
    def setUp(self):
        super().setUp()
        self.user = make_verified_user(email="asha@example.com")

    def test_idle_timeout_configuration(self):
        self.assertEqual(settings.SESSION_COOKIE_AGE, 900)
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)
        self.assertTrue(settings.SESSION_EXPIRE_AT_BROWSER_CLOSE)

    def test_server_side_expiry_is_fifteen_minutes_from_login(self):
        self.login("asha@example.com")
        remaining = (Session.objects.get().expire_date - timezone.now()).total_seconds()
        self.assertTrue(880 < remaining <= 900, remaining)

    def test_session_key_rotates_on_login(self):
        session = self.client.session
        session["probe"] = 1
        session.save()
        before = session.session_key
        self.assertEqual(self.login("asha@example.com").status_code, 200)
        self.assertNotEqual(self.client.session.session_key, before)
        self.assertFalse(Session.objects.filter(session_key=before).exists())

    def test_logged_out_session_cookie_cannot_be_replayed(self):
        self.login("asha@example.com")
        old_cookie = self.client.cookies["sessionid"].value
        self.assertEqual(self.client.post(f"{AUTH}/logout").status_code, 200)
        attacker = APIClient()
        attacker.cookies["sessionid"] = old_cookie
        self.assertEqual(attacker.get(f"{AUTH}/me").status_code, 403)

    def test_password_change_invalidates_existing_sessions(self):
        self.login("asha@example.com")
        self.assertEqual(self.client.get(f"{AUTH}/me").status_code, 200)
        self.user.set_password(secrets.token_urlsafe(16))
        self.user.save()
        self.assertEqual(self.client.get(f"{AUTH}/me").status_code, 403)

    def test_deactivated_user_loses_access_immediately(self):
        self.login("asha@example.com")
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.client.get(f"{AUTH}/me").status_code, 403)

    def test_unverified_user_loses_access_immediately(self):
        self.login("asha@example.com")
        self.user.is_verified = False
        self.user.save()
        self.assertEqual(self.client.get(f"{AUTH}/me").status_code, 403)

    def test_cookie_flags(self):
        login = self.login("asha@example.com")
        self.assertTrue(login.cookies["sessionid"]["httponly"])
        self.assertEqual(login.cookies["sessionid"]["samesite"], "Lax")
        csrf = self.client.get(f"{AUTH}/csrf")
        self.assertEqual(csrf.cookies["csrftoken"]["samesite"], "Lax")

    def test_security_headers(self):
        response = self.client.get(f"{AUTH}/csrf")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertEqual(response["Referrer-Policy"], "same-origin")


class CSRFMatrixTests(ComplaintAPITestCase):
    def setUp(self):
        super().setUp()
        self.complaint = self.make_complaint()

    def test_every_state_changing_endpoint_rejects_requests_without_a_token(self):
        base = "/api/v1/complaints"
        pk = self.complaint.pk
        anonymous = [
            (f"{AUTH}/register", "post", {"name": "A", "email": "a@example.com", "password": PASSWORD}),
            (f"{AUTH}/verify-otp", "post", {"identifier": "a@example.com", "otp": "123456"}),
            (f"{AUTH}/login", "post", {"identifier": "a@example.com", "password": PASSWORD}),
        ]
        for url, method, payload in anonymous:
            with self.subTest(url=url):
                client = APIClient(enforce_csrf_checks=True)
                self.assertEqual(getattr(client, method)(url, payload, format="json").status_code, 403)

        authenticated = [
            (self.citizen, "post", f"{AUTH}/logout", {}),
            (self.citizen, "post", base, self.payload()),
            (self.staff, "patch", f"{base}/{pk}/status", {"status": "In Progress"}),
            (self.staff, "post", f"{base}/{pk}/close", {"resolutionDetails": "Fixed."}),
        ]
        for user, method, url, payload in authenticated:
            with self.subTest(url=url):
                client = client_for(user, enforce_csrf_checks=True)
                self.assertEqual(getattr(client, method)(url, payload, format="json").status_code, 403)

        self.assertEqual(Complaint.objects.count(), 1)
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, ComplaintStatus.ASSIGNED)
        self.assertFalse(User.objects.filter(email="a@example.com").exists())
