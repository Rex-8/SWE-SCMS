from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import override_settings

from apps.accounts.models import User
from apps.accounts.tests.helpers import PASSWORD
from apps.audit.models import AuditLog
from apps.complaints.models import Complaint
from apps.complaints.models import ComplaintStatus as S
from apps.complaints.tests.state import force_state
from apps.notifications.adapters import LocMemNotificationAdapter
from apps.notifications.models import DeliveryStatus, Notification

from .helpers import ApiSession, IntegrationTestCase

FAILING = "apps.notifications.tests.helpers.FailingAdapter"
EXISTING_ID = "SCMS-20261030-AAAAAA"
FRESH_ID = "SCMS-20261030-BBBBBB"


class ConsistencyTests(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.citizen_user = User.objects.create_user(
            email="c@example.com", password=PASSWORD, name="Citizen", is_verified=True
        )
        self.complaint = Complaint.objects.create(
            tracking_id=EXISTING_ID,
            citizen=self.citizen_user,
            category=self.lights,
            department=self.electricity,
            status=S.ASSIGNED,
            description="Light is out",
            location="Sector 12",
        )
        self.citizen = self.login(self.citizen_user)
        self.staff = self.login(self.elec_staff)
        self.status_path = f"/complaints/{self.complaint.pk}/status"
        self.close_path = f"/complaints/{self.complaint.pk}/close"

    def side_effects(self):
        return AuditLog.objects.count(), Notification.objects.count()

    def assert_untouched(self, status=S.ASSIGNED):
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, status)
        self.assertEqual(self.side_effects(), (0, 0))
        self.assertEqual(LocMemNotificationAdapter.outbox, [])

    # -- transactions ---------------------------------------------------------------------

    def test_status_audit_and_notification_commit_together(self):
        self.assertEqual(self.staff.patch(self.status_path, {"status": "In Progress"}).status_code, 200)
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, S.IN_PROGRESS)
        self.assertEqual(self.side_effects(), (1, 1))
        self.assertEqual(Notification.objects.get().delivery_status, DeliveryStatus.PENDING)

    def test_audit_failure_rolls_back_the_whole_change(self):
        with mock.patch("apps.complaints.services.record_audit", side_effect=RuntimeError("audit down")):
            with self.assertRaises(RuntimeError):
                self.staff.patch(self.status_path, {"status": "In Progress"})
        self.assert_untouched()

    def test_failure_writing_the_notification_rolls_back_the_whole_change(self):
        with mock.patch("apps.complaints.services.notify_status_change", side_effect=RuntimeError("db down")):
            with self.assertRaises(RuntimeError):
                self.staff.patch(self.status_path, {"status": "In Progress"})
        self.assert_untouched()

    # -- notification delivery failures ------------------------------------------------

    def test_delivery_failure_keeps_the_change_and_a_retry_delivers(self):
        with override_settings(NOTIFICATION_ADAPTER=FAILING):
            response = self.commit(lambda: self.staff.patch(self.status_path, {"status": "In Progress"}))
        self.assertEqual(response.status_code, 200)
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, S.IN_PROGRESS)
        notification = Notification.objects.get()
        self.assertEqual(
            (notification.delivery_status, notification.attempt_count), (DeliveryStatus.PENDING, 1)
        )
        self.assertEqual(LocMemNotificationAdapter.outbox, [])

        out = StringIO()
        call_command("send_pending_notifications", stdout=out)  # provider is back
        self.assertEqual(out.getvalue().strip(), "sent=1 failed=0 pending=0")
        notification.refresh_from_db()
        self.assertEqual((notification.delivery_status, notification.attempt_count), (DeliveryStatus.SENT, 2))
        self.assertEqual(LocMemNotificationAdapter.outbox[0]["address"], "c@example.com")

    # -- tracking IDs ---------------------------------------------------------------------

    def test_tracking_id_collision_is_recovered_end_to_end(self):
        with mock.patch("apps.complaints.services.generate_tracking_id", side_effect=[EXISTING_ID, FRESH_ID]):
            response = self.citizen.post(
                "/complaints",
                {"categoryId": self.lights.pk, "description": "Another light", "location": "Sector 9"},
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["trackingId"], FRESH_ID)
        self.assertEqual(Complaint.objects.count(), 2)

    # -- department mapping --------------------------------------------------------------

    def test_inactive_mappings_are_rejected_and_remapping_applies_to_new_complaints_only(self):
        def attempt():
            return self.citizen.post(
                "/complaints",
                {"categoryId": self.lights.pk, "description": "Light is out", "location": "Sector 12"},
            )

        self.lights.is_active = False
        self.lights.save()
        self.assertEqual(attempt().status_code, 400)
        self.lights.is_active = True
        self.lights.save()

        self.electricity.is_active = False
        self.electricity.save()
        self.assertEqual(attempt().status_code, 400)
        self.electricity.is_active = True
        self.electricity.save()
        self.assertEqual(Complaint.objects.count(), 1)

        self.lights.department = self.roads
        self.lights.save()
        response = attempt()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["department"], "Roads")
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.department, self.electricity)

    # -- rejected operations have no side effects ----------------------------------------

    def test_invalid_transitions_have_no_side_effects(self):
        cases = [
            (S.ASSIGNED, "Resolved"), (S.ASSIGNED, "Closed"), (S.ASSIGNED, "Assigned"),
            (S.IN_PROGRESS, "Assigned"), (S.IN_PROGRESS, "Closed"), (S.RESOLVED, "Closed"),
            (S.RESOLVED, "Assigned"), (S.CLOSED, "In Progress"), (S.CLOSED, "Resolved"),
        ]  # fmt: skip
        for current, target in cases:
            with self.subTest(current=current.value, target=target):
                force_state(self.complaint, current)
                response = self.commit(lambda: self.staff.patch(self.status_path, {"status": target}))
                self.assertEqual(response.status_code, 409)
                self.assert_untouched(current)

    def test_closure_requires_resolution_details(self):
        force_state(self.complaint, S.RESOLVED)
        for details in ("", "   "):
            response = self.commit(lambda: self.staff.post(self.close_path, {"resolutionDetails": details}))
            self.assertEqual(response.status_code, 400)
            self.assert_untouched(S.RESOLVED)

        response = self.commit(lambda: self.staff.post(self.close_path, {"resolutionDetails": "Fixed it."}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.side_effects(), (1, 1))
        self.assertEqual(len(LocMemNotificationAdapter.outbox), 1)

    def test_unauthorized_updates_have_no_side_effects(self):
        force_state(self.complaint, S.RESOLVED)
        roads = self.login(self.roads_staff)
        anonymous = ApiSession()
        attempts = [
            (self.citizen, "patch", self.status_path, {"status": "In Progress"}, 403),
            (self.citizen, "post", self.close_path, {"resolutionDetails": "x"}, 403),
            (roads, "patch", self.status_path, {"status": "In Progress"}, 404),
            (roads, "post", self.close_path, {"resolutionDetails": "x"}, 404),
            (anonymous, "patch", self.status_path, {"status": "In Progress"}, 403),
            (anonymous, "post", self.close_path, {"resolutionDetails": "x"}, 403),
        ]
        for session, method, path, payload, expected in attempts:
            with self.subTest(method=method, path=path, expected=expected):
                response = self.commit(lambda: getattr(session, method)(path, payload))
                self.assertEqual(response.status_code, expected)
                self.assert_untouched(S.RESOLVED)
