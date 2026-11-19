import json
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.accounts.tests.helpers import PASSWORD, make_verified_user
from apps.audit.models import AuditLog
from apps.complaints.models import ComplaintStatus as S
from apps.complaints.models import Department
from apps.complaints.tests.helpers import ComplaintAPITestCase
from apps.complaints.tests.test_status_workflow import client_for


class StaffActionAuditTests(ComplaintAPITestCase):
    def setUp(self):
        super().setUp()
        self.complaint = self.make_complaint()
        self.status_url = f"/api/v1/complaints/{self.complaint.pk}/status"
        self.close_url = f"/api/v1/complaints/{self.complaint.pk}/close"

    def test_every_successful_action_writes_one_complete_entry(self):
        client = client_for(self.staff)
        started = timezone.now()
        steps = [
            (
                "patch",
                self.status_url,
                {"status": "In Progress", "remark": "Dispatched"},
                "complaint.status_changed",
            ),
            ("patch", self.status_url, {"status": "Resolved"}, "complaint.status_changed"),
            ("post", self.close_url, {"resolutionDetails": "Fixed."}, "complaint.closed"),
        ]
        for number, (method, url, payload, action) in enumerate(steps, start=1):
            self.assertEqual(getattr(client, method)(url, payload, format="json").status_code, 200)
            self.assertEqual(AuditLog.objects.count(), number)
            entry = AuditLog.objects.first()  # newest first
            self.assertEqual(entry.actor, self.staff)
            self.assertEqual(entry.action, action)
            self.assertEqual(entry.object_type, "complaints.complaint")
            self.assertEqual(entry.object_id, str(self.complaint.pk))
            self.assertTrue(started <= entry.timestamp <= timezone.now())
            self.assertIn("from", entry.details)
            self.assertIn("to", entry.details)

    def test_admin_actions_are_attributed_to_the_admin(self):
        client_for(self.admin).patch(self.status_url, {"status": "In Progress"}, format="json")
        self.assertEqual(AuditLog.objects.get().actor, self.admin)

    def test_failed_and_unauthorized_actions_leave_no_entries(self):
        roads_staff = make_verified_user(email="roads@example.com", role=Role.STAFF)
        self.roads.staff.add(roads_staff)
        attempts = [
            (client_for(self.staff), self.status_url, {"status": "Resolved"}, 409),  # invalid transition
            (client_for(self.staff), self.status_url, {"status": "Bogus"}, 400),
            (client_for(self.citizen), self.status_url, {"status": "In Progress"}, 403),
            (APIClient(), self.status_url, {"status": "In Progress"}, 403),
            (client_for(roads_staff), self.status_url, {"status": "In Progress"}, 404),
            (client_for(self.staff), "/api/v1/complaints/999999/status", {"status": "In Progress"}, 404),
            (
                client_for(self.staff, enforce_csrf_checks=True),
                self.status_url,
                {"status": "In Progress"},
                403,
            ),
        ]
        for client, url, payload, expected in attempts:
            with self.subTest(url=url, expected=expected):
                self.assertEqual(client.patch(url, payload, format="json").status_code, expected)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_the_audit_log_is_not_exposed_through_the_api(self):
        client = client_for(self.admin)
        for path in ("/api/v1/audit", "/api/v1/audit/", "/api/v1/auditlog", "/api/v1/audit-logs"):
            with self.subTest(path=path):
                self.assertEqual(client.get(path).status_code, 404)

    def test_details_never_contain_credentials(self):
        client = client_for(self.staff)
        client.patch(self.status_url, {"status": "In Progress", "remark": "Dispatched"}, format="json")
        client.patch(self.status_url, {"status": "Resolved"}, format="json")
        client.post(self.close_url, {"resolutionDetails": "Fixed."}, format="json")
        dumped = json.dumps([e.details for e in AuditLog.objects.all()]).lower()
        for forbidden in ("password", "otp", "session", "token", "secret"):
            self.assertNotIn(forbidden, dumped)

    def test_audit_failure_aborts_the_action(self):
        client = client_for(self.staff)
        with mock.patch("apps.complaints.services.record_audit", side_effect=RuntimeError("audit down")):
            with self.assertRaises(RuntimeError):
                client.patch(self.status_url, {"status": "In Progress"}, format="json")
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, S.ASSIGNED)
        self.assertEqual(AuditLog.objects.count(), 0)


class AdminSiteAuditTests(TestCase):
    """Provisioning staff/admin accounts and editing departments happens in the Django admin."""

    def setUp(self):
        self.root = User.objects.create_superuser(email="root@example.com", name="Root")
        self.client.force_login(self.root)

    def post(self, url, data):
        response = self.client.post(url, data)
        detail = ""
        if response.status_code == 200 and getattr(response, "context", None):
            detail = response.context["adminform"].form.errors
        self.assertEqual(response.status_code, 302, detail)
        return response

    def test_department_add_change_delete_are_audited(self):
        self.post(
            reverse("admin:complaints_department_add"),
            {"name": "Parks", "description": "", "is_active": "on"},
        )
        department = Department.objects.get(name="Parks")
        created = AuditLog.objects.get()
        self.assertEqual(created.actor, self.root)
        self.assertEqual(created.action, "admin.created")
        self.assertEqual(created.object_type, "complaints.department")
        self.assertEqual(created.object_id, str(department.pk))
        self.assertIn("added", created.details["message"][0])

        self.post(
            reverse("admin:complaints_department_change", args=[department.pk]),
            {"name": "Parks & Gardens", "description": "", "is_active": "on"},
        )
        updated = AuditLog.objects.first()
        self.assertEqual(updated.action, "admin.updated")
        self.assertIn("changed", updated.details["message"][0])
        self.assertIn("Name", str(updated.details))

        self.post(reverse("admin:complaints_department_delete", args=[department.pk]), {"post": "yes"})
        deleted = AuditLog.objects.first()
        self.assertEqual(deleted.action, "admin.deleted")
        self.assertEqual(deleted.object_id, str(department.pk))
        self.assertFalse(Department.objects.filter(pk=department.pk).exists())
        self.assertEqual(AuditLog.objects.count(), 3)

    def test_provisioning_a_staff_account_is_audited_without_the_password(self):
        self.post(
            reverse("admin:accounts_user_add"),
            {
                "name": "New Staff",
                "email": "new.staff@example.com",
                "mobile": "",
                "role": Role.STAFF,
                "is_verified": "on",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )
        created = User.objects.get(email="new.staff@example.com")
        self.assertEqual(created.role, Role.STAFF)
        self.assertTrue(created.password.startswith("argon2$"))
        entry = AuditLog.objects.get()
        self.assertEqual(entry.action, "admin.created")
        self.assertEqual(entry.object_type, "accounts.user")
        self.assertEqual(entry.object_id, str(created.pk))
        self.assertEqual(entry.actor, self.root)
        self.assertNotIn(PASSWORD, json.dumps(entry.details))

    def test_a_rejected_admin_form_leaves_no_entry(self):
        response = self.client.post(
            reverse("admin:complaints_department_add"), {"name": "", "description": ""}
        )
        self.assertEqual(response.status_code, 200)  # form re-rendered with errors
        self.assertEqual(AuditLog.objects.count(), 0)
