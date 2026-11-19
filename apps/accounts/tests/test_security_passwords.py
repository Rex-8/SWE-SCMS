import logging
from unittest import mock

from django.apps import apps
from django.conf import settings
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import User

from .helpers import AUTH, PASSWORD, AuthAPITestCase


def database_text():
    """Every row of every table as text, to prove a secret is stored nowhere."""
    chunks = []
    for model in apps.get_models():
        chunks.extend(repr(row) for row in model._base_manager.values())
    return "\n".join(chunks)


class CapturingHandler(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines = []

    def emit(self, record):
        self.lines.append(self.format(record))


class PasswordStorageTests(AuthAPITestCase):
    def test_argon2_is_the_primary_hasher(self):
        self.assertEqual(settings.PASSWORD_HASHERS[0], "django.contrib.auth.hashers.Argon2PasswordHasher")

    def test_hashes_are_argon2_and_salted(self):
        self.register()
        self.register(name="Ravi", email="ravi@example.com")  # same password, different user
        first = User.objects.get(email="asha@example.com")
        second = User.objects.get(email="ravi@example.com")
        for user in (first, second):
            self.assertTrue(user.password.startswith("argon2$"))
            self.assertNotIn(PASSWORD, user.password)
            self.assertTrue(user.check_password(PASSWORD))
        self.assertNotEqual(first.password, second.password)

    def test_no_plaintext_password_anywhere_in_the_database(self):
        self.register()
        self.verify("asha@example.com", self.last_code())
        self.assertEqual(self.login("asha@example.com").status_code, 200)
        self.assertNotIn(PASSWORD, database_text())

    def test_weak_passwords_are_rejected(self):
        for weak in ("short1!", "password123", "asha@example.com", "12345678"):
            with self.subTest(password=weak):
                cache.clear()  # throttle counters live in the cache
                response = self.register(password=weak)
                self.assertEqual(response.status_code, 400)
                self.assertIn("password", response.json())
        self.assertEqual(User.objects.count(), 0)

    def test_passwords_are_never_returned_by_the_api(self):
        responses = [self.register()]
        self.verify("asha@example.com", self.last_code())
        responses.append(self.login("asha@example.com"))
        responses.append(self.client.get(f"{AUTH}/me"))
        for response in responses:
            self.assertNotIn(PASSWORD, response.content.decode())
            self.assertNotIn("password", response.content.decode().lower())

    def test_passwords_otps_and_session_ids_never_reach_the_logs(self):
        handler = CapturingHandler()
        root = logging.getLogger()
        previous_level = root.level
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)
        try:
            self.register()
            code = self.last_code()
            self.verify("asha@example.com", self.wrong_code(code))
            self.verify("asha@example.com", code)
            self.login("asha@example.com", PASSWORD + "x")
            login = self.login("asha@example.com")
            session_id = login.cookies["sessionid"].value
        finally:
            root.removeHandler(handler)
            root.setLevel(previous_level)
        logged = "\n".join(handler.lines)
        self.assertIn("Unauthorized", logged)  # the capture really works
        self.assertNotIn(PASSWORD, logged)
        self.assertNotIn(code, logged)
        self.assertNotIn(session_id, logged)


class ErrorHandlingTests(AuthAPITestCase):
    def test_malformed_and_unsupported_bodies_get_clean_errors(self):
        malformed = self.client.post(f"{AUTH}/login", "{not json", content_type="application/json")
        self.assertEqual(malformed.status_code, 400)
        wrong_type = self.client.post(f"{AUTH}/login", "x", content_type="text/plain")
        self.assertEqual(wrong_type.status_code, 415)
        for response in (malformed, wrong_type):
            self.assertNotIn("Traceback", response.content.decode())

    def test_unexpected_errors_do_not_leak_internals(self):
        client = APIClient()
        client.raise_request_exception = False
        with mock.patch("apps.accounts.views.authenticate", side_effect=RuntimeError("internal detail")):
            with self.assertLogs("django.request", level="ERROR"):
                response = client.post(
                    f"{AUTH}/login", {"identifier": "asha@example.com", "password": PASSWORD}, format="json"
                )
        self.assertEqual(response.status_code, 500)
        self.assertNotIn(b"internal detail", response.content)
        self.assertNotIn(b"Traceback", response.content)
