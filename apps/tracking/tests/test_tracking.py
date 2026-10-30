from unittest import mock

from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from apps.accounts.models import Role
from apps.accounts.tests.helpers import make_verified_user
from apps.complaints.models import ComplaintStatus
from apps.complaints.tests.helpers import TRACK_URL, ComplaintAPITestCase

FIELDS = {
    "trackingId", "category", "description", "location", "status",
    "department", "createdAt", "updatedAt", "closedAt",
}  # fmt: skip


class TrackingTests(ComplaintAPITestCase):
    def setUp(self):
        super().setUp()
        self.complaint = self.make_complaint()
        self.url = f"{TRACK_URL}/{self.complaint.tracking_id}"

    def test_owner_can_track(self):
        self.client.force_login(self.citizen)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(set(body), FIELDS)
        self.assertEqual(body["trackingId"], self.complaint.tracking_id)
        self.assertEqual(body["category"], "Streetlight not working")
        self.assertEqual(body["description"], "Light is out")
        self.assertEqual(body["location"], "Sector 12")
        self.assertEqual(body["status"], "Assigned")
        self.assertEqual(body["department"], "Electricity")
        self.assertIsNotNone(body["createdAt"])
        self.assertIsNotNone(body["updatedAt"])
        self.assertIsNone(body["closedAt"])

    def test_closed_complaint_shows_closed_timestamp(self):
        closed = self.make_complaint(
            tracking_id="SCMS-20261030-CCCCCC",
            status=ComplaintStatus.CLOSED,
            resolution_details="Fixed",
            closed_at=timezone.now(),
        )
        self.client.force_login(self.citizen)
        body = self.client.get(f"{TRACK_URL}/{closed.tracking_id}").json()
        self.assertEqual(body["status"], "Closed")
        self.assertIsNotNone(body["closedAt"])

    def test_tracking_id_is_case_insensitive(self):
        self.client.force_login(self.citizen)
        r = self.client.get(f"{TRACK_URL}/{self.complaint.tracking_id.lower()}")
        self.assertEqual(r.status_code, 200)

    def test_other_citizen_gets_same_404_as_unknown_id(self):
        self.client.force_login(self.other_citizen)
        forbidden = self.client.get(self.url)
        unknown = self.client.get(f"{TRACK_URL}/SCMS-20261030-ZZZZZZ")
        self.assertEqual(forbidden.status_code, 404)
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(forbidden.json(), unknown.json())

    def test_malformed_ids_are_404(self):
        self.client.force_login(self.citizen)
        for bad in ("invalid", "SCMS-1-2", "SCMS-20261030-AAAAAAA", "SCMS-20261030-AAAAA!"):
            with self.subTest(bad=bad):
                self.assertEqual(self.client.get(f"{TRACK_URL}/{bad}").status_code, 404)

    def test_anonymous_is_denied(self):
        self.assertEqual(APIClient().get(self.url).status_code, 403)

    def test_admin_can_track_any_complaint(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_staff_only_see_their_departments_complaints(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url).status_code, 200)

        roads_staff = make_verified_user(email="roads@example.com", role=Role.STAFF)
        self.roads.staff.add(roads_staff)
        self.client.force_login(roads_staff)
        self.assertEqual(self.client.get(self.url).status_code, 404)

        no_dept_staff = make_verified_user(email="nodept@example.com", role=Role.STAFF)
        self.client.force_login(no_dept_staff)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_tracking_is_throttled(self):
        self.client.force_login(self.citizen)
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {"track": "1/min"}):
            self.assertEqual(self.client.get(self.url).status_code, 200)
            self.assertEqual(self.client.get(self.url).status_code, 429)
