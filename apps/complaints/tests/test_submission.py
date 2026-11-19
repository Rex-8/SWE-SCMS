from unittest import mock

from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from apps.complaints.models import Complaint, ComplaintStatus

from .helpers import ComplaintAPITestCase


class SubmissionTests(ComplaintAPITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.citizen)

    def test_successful_submission(self):
        r = self.submit(description="  Light is out  ")
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertEqual(set(body), {"trackingId", "status", "department"})
        self.assertEqual(body["status"], "Assigned")
        self.assertEqual(body["department"], "Electricity")
        c = Complaint.objects.get(tracking_id=body["trackingId"])
        self.assertEqual(c.citizen, self.citizen)
        self.assertEqual(c.category, self.lights)
        self.assertEqual(c.department, self.elec)
        self.assertEqual(c.status, ComplaintStatus.ASSIGNED)
        self.assertEqual(c.description, "Light is out")
        self.assertEqual(c.location, "Sector 12, Main Road")
        self.assertIsNone(c.assigned_staff)

    def test_department_comes_from_category(self):
        r = self.submit(categoryId=self.potholes.pk)
        self.assertEqual(r.json()["department"], "Roads")
        self.assertEqual(Complaint.objects.get().department, self.roads)

    def test_client_cannot_override_server_controlled_fields(self):
        r = self.submit(
            citizen=self.other_citizen.pk,
            citizen_id=self.other_citizen.pk,
            department=self.roads.pk,
            departmentId=self.roads.pk,
            status="CLOSED",
            trackingId="SCMS-20990101-ZZZZZZ",
            assigned_staff=self.staff.pk,
        )
        self.assertEqual(r.status_code, 201)
        c = Complaint.objects.get()
        self.assertEqual(c.citizen, self.citizen)
        self.assertEqual(c.department, self.elec)
        self.assertEqual(c.status, ComplaintStatus.ASSIGNED)
        self.assertNotEqual(c.tracking_id, "SCMS-20990101-ZZZZZZ")
        self.assertIsNone(c.assigned_staff)

    def test_required_fields(self):
        for field in ("categoryId", "description", "location"):
            with self.subTest(field=field):
                r = self.submit(**{field: None})
                self.assertEqual(r.status_code, 400)
                self.assertIn(field, r.json())
        self.assertEqual(Complaint.objects.count(), 0)

    def test_blank_and_oversized_text_rejected(self):
        for overrides in (
            {"description": "   "},
            {"location": ""},
            {"description": "x" * 5001},
            {"location": "x" * 256},
        ):
            with self.subTest(overrides=list(overrides)):
                self.assertEqual(self.submit(**overrides).status_code, 400)
        self.assertEqual(Complaint.objects.count(), 0)

    def test_invalid_category_values(self):
        for value in ("abc", 0, -1, 999999, 10**30):
            with self.subTest(value=value):
                r = self.submit(categoryId=value)
                self.assertEqual(r.status_code, 400)
                self.assertIn("categoryId", r.json())
        self.assertEqual(Complaint.objects.count(), 0)

    def test_inactive_category_rejected(self):
        self.lights.is_active = False
        self.lights.save()
        self.assertEqual(self.submit().status_code, 400)
        self.assertEqual(Complaint.objects.count(), 0)

    def test_inactive_department_rejected(self):
        self.elec.is_active = False
        self.elec.save()
        self.assertEqual(self.submit().status_code, 400)
        self.assertEqual(Complaint.objects.count(), 0)

    def test_only_citizens_can_submit(self):
        for label, client in (
            ("anonymous", APIClient()),
            ("staff", self._client_for(self.staff)),
            ("admin", self._client_for(self.admin)),
        ):
            with self.subTest(label=label):
                self.assertEqual(self.submit(client=client).status_code, 403)
        self.assertEqual(Complaint.objects.count(), 0)

    def test_csrf_enforced(self):
        client = self._client_for(self.citizen, enforce_csrf_checks=True)
        self.assertEqual(self.submit(client=client).status_code, 403)
        self.assertEqual(Complaint.objects.count(), 0)

    def test_submission_is_throttled(self):
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {"complaint_submit": "1/hour"}):
            self.assertEqual(self.submit().status_code, 201)
            self.assertEqual(self.submit().status_code, 429)

    @staticmethod
    def _client_for(user, **kwargs):
        client = APIClient(**kwargs)
        client.force_login(user)
        return client
