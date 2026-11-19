import json
import os
import secrets
import subprocess
import sys

from django.conf import settings
from django.test import Client, SimpleTestCase, override_settings

from .helpers import AUTH, PASSWORD, AuthAPITestCase, make_verified_user

KEYS = [
    "DEBUG",
    "SESSION_COOKIE_SECURE",
    "CSRF_COOKIE_SECURE",
    "SECURE_SSL_REDIRECT",
    "SECURE_HSTS_SECONDS",
    "SECURE_HSTS_INCLUDE_SUBDOMAINS",
    "SECURE_CONTENT_TYPE_NOSNIFF",
    "SECURE_PROXY_SSL_HEADER",
]
DUMP = (
    "import json; from django.conf import settings as s; print(json.dumps({k: getattr(s, k) for k in %r}))"
    % (KEYS,)
)
DEPLOY_WARNINGS_THAT_MUST_BE_ABSENT = [
    "security.W004",  # HSTS seconds
    "security.W005",  # HSTS include subdomains
    "security.W006",  # nosniff
    "security.W008",  # SSL redirect
    "security.W009",  # weak secret key
    "security.W012",  # session cookie secure
    "security.W016",  # CSRF cookie secure
    "security.W018",  # DEBUG on
    "security.W020",  # empty ALLOWED_HOSTS
]


def run_python(debug, *args):
    """Run a fresh interpreter with the given DJANGO_DEBUG (settings are read at import time)."""
    env = dict(os.environ)
    env.update(
        DJANGO_DEBUG=debug,
        DJANGO_SECRET_KEY=secrets.token_urlsafe(50),
        DJANGO_ALLOWED_HOSTS="example.com",
        DJANGO_SETTINGS_MODULE="config.settings",
    )
    env.pop("DJANGO_SECURE_SSL_REDIRECT", None)
    return subprocess.run(
        [sys.executable, *args], cwd=settings.BASE_DIR, env=env, capture_output=True, text=True, timeout=120
    )


class DeploymentSettingsTests(SimpleTestCase):
    def dump(self, debug):
        result = run_python(debug, "-c", DUMP)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout.strip().splitlines()[-1])

    def test_production_settings_enable_transport_security(self):
        cfg = self.dump("False")
        self.assertFalse(cfg["DEBUG"])
        self.assertTrue(cfg["SESSION_COOKIE_SECURE"])
        self.assertTrue(cfg["CSRF_COOKIE_SECURE"])
        self.assertTrue(cfg["SECURE_SSL_REDIRECT"])
        self.assertGreaterEqual(cfg["SECURE_HSTS_SECONDS"], 31536000)
        self.assertTrue(cfg["SECURE_HSTS_INCLUDE_SUBDOMAINS"])
        self.assertTrue(cfg["SECURE_CONTENT_TYPE_NOSNIFF"])
        self.assertEqual(cfg["SECURE_PROXY_SSL_HEADER"], ["HTTP_X_FORWARDED_PROTO", "https"])

    def test_development_settings_allow_plain_http(self):
        cfg = self.dump("True")
        self.assertTrue(cfg["DEBUG"])
        self.assertFalse(cfg["SECURE_SSL_REDIRECT"])
        self.assertFalse(cfg["SESSION_COOKIE_SECURE"])

    def test_django_deploy_check_has_no_transport_security_warnings(self):
        result = run_python("False", "manage.py", "check", "--deploy")
        self.assertEqual(result.returncode, 0, result.stderr)
        output = result.stdout + result.stderr
        for code in DEPLOY_WARNINGS_THAT_MUST_BE_ABSENT:
            self.assertNotIn(code, output)


class SecureDeploymentBehaviourTests(AuthAPITestCase):
    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_plain_http_is_redirected_to_https(self):
        response = Client().get(f"{AUTH}/csrf")
        self.assertEqual(response.status_code, 301)
        self.assertTrue(response["Location"].startswith("https://"))

    @override_settings(
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
        SECURE_HSTS_SECONDS=31536000,
        SECURE_HSTS_INCLUDE_SUBDOMAINS=True,
    )
    def test_cookies_are_secure_and_hsts_is_sent_over_https(self):
        make_verified_user(email="asha@example.com")
        client = type(self.client)()
        login = client.post(
            f"{AUTH}/login",
            {"identifier": "asha@example.com", "password": PASSWORD},
            format="json",
            secure=True,
        )
        self.assertEqual(login.status_code, 200)
        self.assertTrue(login.cookies["sessionid"]["secure"])
        self.assertIn("max-age=31536000", login["Strict-Transport-Security"])
        self.assertIn("includeSubDomains", login["Strict-Transport-Security"])
        csrf = client.get(f"{AUTH}/csrf", secure=True)
        self.assertTrue(csrf.cookies["csrftoken"]["secure"])
