import re

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.gateways import LocMemOTPGateway
from apps.accounts.models import Role, User
from apps.accounts.tests.helpers import PASSWORD
from apps.complaints.models import Category, Department
from apps.notifications.adapters import LocMemNotificationAdapter

API = "/api/v1"
TRACKING_ID_RE = re.compile(r"^SCMS-\d{8}-[A-Z0-9]{6}$")


class ApiSession:
    """Browser-like client: session cookies plus CSRF tokens, exactly as a real front end behaves."""

    def __init__(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.get(f"{API}/auth/csrf")

    def _csrf(self):
        return {"HTTP_X_CSRFTOKEN": self.client.cookies["csrftoken"].value}

    def get(self, path):
        return self.client.get(f"{API}{path}")

    def post(self, path, data=None):
        return self.client.post(f"{API}{path}", data or {}, format="json", **self._csrf())

    def patch(self, path, data=None):
        return self.client.patch(f"{API}{path}", data or {}, format="json", **self._csrf())


@override_settings(
    OTP_GATEWAY="apps.accounts.gateways.LocMemOTPGateway",
    NOTIFICATION_ADAPTER="apps.notifications.adapters.LocMemNotificationAdapter",
)
class IntegrationTestCase(TestCase):
    fixtures = ["sample_departments"]

    def setUp(self):
        cache.clear()  # throttle counters live in the cache
        LocMemOTPGateway.outbox.clear()
        LocMemNotificationAdapter.outbox.clear()
        self.electricity = Department.objects.get(name="Electricity")
        self.roads = Department.objects.get(name="Roads")
        self.lights = Category.objects.get(name="Streetlight not working")
        self.potholes = Category.objects.get(name="Road damage")
        self.elec_staff = self.make_staff("elec.staff@example.com", self.electricity)
        self.roads_staff = self.make_staff("roads.staff@example.com", self.roads)
        self.admin = User.objects.create_user(
            email="admin@example.com", password=PASSWORD, name="Admin", role=Role.ADMIN
        )

    def make_staff(self, email, department):
        user = User.objects.create_user(email=email, password=PASSWORD, name="Staff", role=Role.STAFF)
        department.staff.add(user)
        return user

    def login(self, user):
        session = ApiSession()
        response = session.post("/auth/login", {"identifier": user.email, "password": PASSWORD})
        self.assertEqual(response.status_code, 200, response.content)
        return session

    def sign_up(self, email, name="Asha"):
        """Register, verify the OTP and log in through the API. Returns a logged-in session."""
        session = ApiSession()
        response = session.post("/auth/register", {"name": name, "email": email, "password": PASSWORD})
        self.assertEqual(response.status_code, 201, response.content)
        code = LocMemOTPGateway.outbox[-1]["code"]
        response = session.post("/auth/verify-otp", {"identifier": email, "otp": code})
        self.assertEqual(response.status_code, 200, response.content)
        response = session.post("/auth/login", {"identifier": email, "password": PASSWORD})
        self.assertEqual(response.status_code, 200, response.content)
        return session

    def submit(self, session, category=None, description="Light is out"):
        response = session.post(
            "/complaints",
            {"categoryId": (category or self.lights).pk, "description": description, "location": "Sector 12"},
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["trackingId"]

    def commit(self, call):
        """Run an API call, then execute its after-commit hooks (notification delivery)."""
        with self.captureOnCommitCallbacks(execute=True):
            return call()
