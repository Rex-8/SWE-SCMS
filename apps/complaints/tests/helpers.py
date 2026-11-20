from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Role
from apps.accounts.tests.helpers import make_verified_user
from apps.complaints.models import Category, Complaint, ComplaintStatus, Department

COMPLAINTS_URL = "/api/v1/complaints"
TRACK_URL = "/api/v1/complaints/track"


class ComplaintAPITestCase(TestCase):
    def setUp(self):
        cache.clear()  # throttle counters live in the cache
        self.client = APIClient()
        self.citizen = make_verified_user(email="citizen@example.com", name="Citizen")
        self.other_citizen = make_verified_user(email="other@example.com", name="Other")
        self.staff = make_verified_user(email="staff@example.com", role=Role.STAFF, name="Staff")
        self.admin = make_verified_user(email="admin@example.com", role=Role.ADMIN, name="Admin")
        self.elec = Department.objects.create(name="Electricity")
        self.roads = Department.objects.create(name="Roads")
        self.elec.staff.add(self.staff)
        self.lights = Category.objects.create(name="Streetlight not working", department=self.elec)
        self.potholes = Category.objects.create(name="Road damage", department=self.roads)

    def payload(self, **overrides):
        """Pass a key as None to omit it."""
        data = {
            "categoryId": self.lights.pk,
            "description": "Light is out",
            "location": "Sector 12, Main Road",
        }
        for key, value in overrides.items():
            if value is None:
                data.pop(key, None)
            else:
                data[key] = value
        return data

    def submit(self, client=None, **overrides):
        return (client or self.client).post(COMPLAINTS_URL, self.payload(**overrides), format="json")

    def make_complaint(self, **kw):
        category = kw.pop("category", self.lights)
        data = dict(
            tracking_id="SCMS-20261030-AAAAAA",
            citizen=self.citizen,
            category=category,
            department=category.department,
            status=ComplaintStatus.ASSIGNED,
            description="Light is out",
            location="Sector 12",
        )
        data.update(kw)
        return Complaint.objects.create(**data)
