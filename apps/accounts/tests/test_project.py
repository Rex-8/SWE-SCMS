from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import SimpleTestCase, TestCase


class ProjectHealthTests(TestCase):
    def test_system_check_passes(self):
        call_command("check")

    def test_no_missing_migrations(self):
        call_command("makemigrations", "--check", "--dry-run")

    def test_database_connection(self):
        with connection.cursor() as c:
            c.execute("SELECT 1")
            self.assertEqual(c.fetchone()[0], 1)


class SettingsTests(SimpleTestCase):
    def test_custom_user_model_active(self):
        self.assertEqual(settings.AUTH_USER_MODEL, "accounts.User")
        self.assertEqual(get_user_model().__name__, "User")

    def test_session_security_settings(self):
        self.assertEqual(settings.SESSION_COOKIE_AGE, 900)
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, "Lax")
