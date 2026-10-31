from rest_framework.test import APIClient

from apps.accounts.models import Role
from apps.accounts.tests.helpers import make_verified_user
from apps.audit.models import AuditLog
from apps.complaints.models import ComplaintStatus as S

from .helpers import ComplaintAPITestCase
from .state import force_state


def status_url(complaint_or_pk):
    pk = getattr(complaint_or_pk, "pk", complaint_or_pk)
    return f"/api/v1/complaints/{pk}/status"


def client_for(user, **kwargs):
    client = APIClient(**kwargs)
    client.force_login(user)
    return client


class StatusUpdateTests(ComplaintAPITestCase):
    def setUp(self):
        super().setUp()
        self.complaint = self.make_complaint()
        self.url = status_url(self.complaint)
        self.client = client_for(self.staff)

    def patch(self, status, remark=None, client=None, url=None):
        data = {"status": status}
        if remark is not None:
            data["remark"] = remark
        return (client or self.client).patch(url or self.url, data, format="json")

    def assert_unchanged(self, expected=S.ASSIGNED):
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, expected)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_staff_can_start_work_and_it_is_audited(self):
        before = self.complaint.updated_at
        r = self.patch("In Progress", "Team dispatched")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "In Progress")
        self.assertIn("updatedAt", r.json())
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, S.IN_PROGRESS)
        self.assertGreaterEqual(self.complaint.updated_at, before)
        entry = AuditLog.objects.get()
        self.assertEqual(entry.actor, self.staff)
        self.assertEqual(entry.action, "complaint.status_changed")
        self.assertEqual(entry.object_type, "complaints.complaint")
        self.assertEqual(entry.object_id, str(self.complaint.pk))
        self.assertEqual(
            entry.details, {"from": "ASSIGNED", "to": "IN_PROGRESS", "remark": "Team dispatched"}
        )

    def test_full_forward_path_and_rework(self):
        for target in ("In Progress", "Resolved", "In Progress", "Resolved"):
            self.assertEqual(self.patch(target).status_code, 200, target)
        self.assertEqual(AuditLog.objects.count(), 4)
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, S.RESOLVED)

    def test_remark_is_optional(self):
        self.assertEqual(self.patch("In Progress").status_code, 200)
        self.assertEqual(AuditLog.objects.get().details["remark"], "")

    def test_status_text_is_case_and_separator_insensitive(self):
        for variant in ("in progress", "IN_PROGRESS", "In Progress"):
            force_state(self.complaint, S.ASSIGNED)
            self.assertEqual(self.patch(variant).status_code, 200, variant)

    def test_admin_can_update_any_complaint(self):
        r = self.patch("In Progress", client=client_for(self.admin))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(AuditLog.objects.get().actor, self.admin)

    def test_invalid_transitions_are_rejected_without_side_effects(self):
        cases = [
            (S.ASSIGNED, "Resolved"), (S.ASSIGNED, "Closed"), (S.ASSIGNED, "Submitted"),
            (S.ASSIGNED, "Assigned"), (S.IN_PROGRESS, "Assigned"), (S.IN_PROGRESS, "Closed"),
            (S.RESOLVED, "Closed"), (S.RESOLVED, "Assigned"), (S.CLOSED, "In Progress"),
            (S.CLOSED, "Resolved"),
        ]  # fmt: skip
        for current, target in cases:
            with self.subTest(current=current.value, target=target):
                force_state(self.complaint, current)
                r = self.patch(target)
                self.assertEqual(r.status_code, 409)
                self.assert_unchanged(current)

    def test_closing_through_the_status_endpoint_points_to_close(self):
        force_state(self.complaint, S.RESOLVED)
        r = self.patch("Closed")
        self.assertEqual(r.status_code, 409)
        self.assertIn("close", r.json()["detail"].lower())

    def test_bad_input(self):
        for payload in ({}, {"status": ""}, {"status": "Bogus"}, {"status": "In Progress", "remark": "x" * 1001}):
            with self.subTest(payload=payload):
                r = self.client.patch(self.url, payload, format="json")
                self.assertEqual(r.status_code, 400)
        self.assert_unchanged()

    def test_citizen_cannot_update_even_their_own_complaint(self):
        self.assertEqual(self.patch("In Progress", client=client_for(self.citizen)).status_code, 403)
        self.assert_unchanged()

    def test_anonymous_cannot_update(self):
        self.assertEqual(self.patch("In Progress", client=APIClient()).status_code, 403)
        self.assert_unchanged()

    def test_staff_of_another_department_gets_404(self):
        roads_staff = make_verified_user(email="roads@example.com", role=Role.STAFF)
        self.roads.staff.add(roads_staff)
        self.assertEqual(self.patch("In Progress", client=client_for(roads_staff)).status_code, 404)
        self.assert_unchanged()

    def test_staff_without_a_department_gets_404(self):
        loner = make_verified_user(email="loner@example.com", role=Role.STAFF)
        self.assertEqual(self.patch("In Progress", client=client_for(loner)).status_code, 404)
        self.assert_unchanged()

    def test_unknown_complaint_gets_404(self):
        self.assertEqual(self.patch("In Progress", url=status_url(999999)).status_code, 404)

    def test_csrf_is_enforced(self):
        client = client_for(self.staff, enforce_csrf_checks=True)
        self.assertEqual(self.patch("In Progress", client=client).status_code, 403)
        self.assert_unchanged()
