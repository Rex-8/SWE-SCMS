from rest_framework.test import APIClient

from apps.accounts.models import Role
from apps.accounts.tests.helpers import make_verified_user
from apps.audit.models import AuditLog
from apps.complaints.models import ComplaintStatus as S
from apps.complaints.tests.helpers import TRACK_URL

from .helpers import ComplaintAPITestCase
from .state import force_state
from .test_status_workflow import client_for

DETAILS = "Streetlight repaired."


def close_url(complaint_or_pk):
    pk = getattr(complaint_or_pk, "pk", complaint_or_pk)
    return f"/api/v1/complaints/{pk}/close"


class ClosureTests(ComplaintAPITestCase):
    def setUp(self):
        super().setUp()
        self.complaint = self.make_complaint()
        force_state(self.complaint, S.RESOLVED)
        self.url = close_url(self.complaint)
        self.client = client_for(self.staff)

    def close(self, details=DETAILS, client=None, url=None, **extra):
        data = {} if details is None else {"resolutionDetails": details}
        data.update(extra)
        return (client or self.client).post(url or self.url, data, format="json")

    def assert_still_resolved(self):
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, S.RESOLVED)
        self.assertIsNone(self.complaint.closed_at)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_staff_can_close_a_resolved_complaint(self):
        r = self.close("  Streetlight repaired.  ")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "Closed")
        self.assertIsNotNone(r.json()["closedAt"])
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, S.CLOSED)
        self.assertEqual(self.complaint.resolution_details, DETAILS)
        self.assertIsNotNone(self.complaint.closed_at)
        entry = AuditLog.objects.get()
        self.assertEqual(entry.actor, self.staff)
        self.assertEqual(entry.action, "complaint.closed")
        self.assertEqual(entry.details, {"from": "RESOLVED", "to": "CLOSED", "resolution_details": DETAILS})

    def test_admin_can_close(self):
        self.assertEqual(self.close(client=client_for(self.admin)).status_code, 200)

    def test_resolution_details_are_mandatory(self):
        for details in (None, "", "   ", "\n\t"):
            with self.subTest(details=details):
                r = self.close(details)
                self.assertEqual(r.status_code, 400)
                self.assertIn("resolutionDetails", r.json())
        self.assert_still_resolved()

    def test_only_resolved_complaints_can_be_closed(self):
        for state in (S.ASSIGNED, S.IN_PROGRESS):
            with self.subTest(state=state.value):
                force_state(self.complaint, state)
                self.assertEqual(self.close().status_code, 409)
                self.complaint.refresh_from_db()
                self.assertEqual(self.complaint.status, state)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_closed_complaint_cannot_be_closed_again_or_overwritten(self):
        force_state(self.complaint, S.CLOSED)
        self.assertEqual(self.close("Something else").status_code, 409)
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.resolution_details, "Fixed")
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_citizen_cannot_close(self):
        self.assertEqual(self.close(client=client_for(self.citizen)).status_code, 403)
        self.assert_still_resolved()

    def test_anonymous_cannot_close(self):
        self.assertEqual(self.close(client=APIClient()).status_code, 403)
        self.assert_still_resolved()

    def test_other_department_staff_gets_404(self):
        roads_staff = make_verified_user(email="roads@example.com", role=Role.STAFF)
        self.roads.staff.add(roads_staff)
        self.assertEqual(self.close(client=client_for(roads_staff)).status_code, 404)
        self.assert_still_resolved()

    def test_unknown_complaint_gets_404(self):
        self.assertEqual(self.close(url=close_url(999999)).status_code, 404)

    def test_csrf_is_enforced(self):
        client = client_for(self.staff, enforce_csrf_checks=True)
        self.assertEqual(self.close(client=client).status_code, 403)
        self.assert_still_resolved()

    def test_citizen_sees_the_closed_state_when_tracking(self):
        self.close()
        body = client_for(self.citizen).get(f"{TRACK_URL}/{self.complaint.tracking_id}").json()
        self.assertEqual(body["status"], "Closed")
        self.assertIsNotNone(body["closedAt"])
