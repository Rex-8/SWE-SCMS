from django.apps import apps
from django.conf import settings
from rest_framework.test import APIClient

from apps.complaints.models import Complaint

from .helpers import IntegrationTestCase


class SprintOneScopeTests(IntegrationTestCase):
    """Guards against Sprint 2 features (F-005, F-008, F-009, F-011, F-015) sneaking in."""

    EXCLUDED_PATHS = [
        "/complaints/search",
        "/complaints/1/history",
        "/complaints/1/evidence",
        "/complaints/1/attachments",
        "/complaints/1/reassign",
        "/complaints/1/feedback",
        "/reports",
        "/reports/summary",
    ]
    FORBIDDEN_APP_LABELS = {"reports", "feedback", "evidence", "uploads", "search"}
    FORBIDDEN_FIELDS = {
        "attachment",
        "attachments",
        "feedback",
        "rating",
        "reassigned_by",
    }
    def test_excluded_endpoints_do_not_exist(self):
        admin = self.login(self.admin)
        for path in self.EXCLUDED_PATHS:
            for method in ("get", "post"):
                with self.subTest(method=method, path=path):
                    self.assertEqual(getattr(admin, method)(path).status_code, 404)

    def test_no_excluded_apps_or_model_fields(self):
        labels = {config.label for config in apps.get_app_configs()}
        self.assertEqual(labels & self.FORBIDDEN_APP_LABELS, set())
        fields = {field.name for field in Complaint._meta.get_fields()}
        self.assertEqual(fields & self.FORBIDDEN_FIELDS, set())

    def test_authentication_is_session_based_only(self):
        self.assertEqual(
            settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"],
            ["rest_framework.authentication.SessionAuthentication"],
        )
        self.assertNotIn("rest_framework_simplejwt", settings.INSTALLED_APPS)
        response = APIClient().get("/api/v1/auth/me", HTTP_AUTHORIZATION="Bearer anything")
        self.assertEqual(response.status_code, 403)
