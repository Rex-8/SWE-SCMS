from apps.accounts.models import Role
from apps.accounts.tests.helpers import make_verified_user
from apps.audit.models import AuditLog
from apps.complaints.models import ComplaintStatus as S
from apps.complaints.tests.state import force_state
from apps.complaints.tests.test_status_workflow import client_for
from apps.notifications.adapters import LocMemNotificationAdapter
from apps.notifications.models import DeliveryStatus, EventType, Notification

from django.test import override_settings

from .helpers import NotificationTestCase

FAILING = "apps.notifications.tests.helpers.FailingAdapter"
RESOLUTION = "Streetlight repaired."


class StatusNotificationTests(NotificationTestCase):
    def setUp(self):
        super().setUp()
        self.complaint = self.make_complaint()
        self.client = client_for(self.staff)
        self.status_url = f"/api/v1/complaints/{self.complaint.pk}/status"
        self.close_url = f"/api/v1/complaints/{self.complaint.pk}/close"

    def patch_status(self, status, client=None, execute=True):
        with self.captureOnCommitCallbacks(execute=execute):
            return (client or self.client).patch(self.status_url, {"status": status}, format="json")

    def close(self, client=None, execute=True):
        with self.captureOnCommitCallbacks(execute=execute):
            return (client or self.client).post(
                self.close_url, {"resolutionDetails": RESOLUTION}, format="json"
            )

    def test_status_change_notifies_the_citizen(self):
        self.assertEqual(self.patch_status("In Progress").status_code, 200)
        n = Notification.objects.get()
        self.assertEqual(n.recipient, self.citizen)
        self.assertEqual(n.complaint, self.complaint)
        self.assertEqual((n.from_status, n.to_status), ("ASSIGNED", "IN_PROGRESS"))
        self.assertEqual(n.delivery_status, DeliveryStatus.SENT)
        self.assertEqual(len(LocMemNotificationAdapter.outbox), 1)
        self.assertEqual(LocMemNotificationAdapter.outbox[0]["address"], "citizen@example.com")
        self.assertFalse(Notification.objects.filter(recipient=self.other_citizen).exists())

    def test_every_valid_change_and_the_closure_notify(self):
        self.patch_status("In Progress")
        self.patch_status("Resolved")
        self.close()
        events = list(Notification.objects.values_list("event_type", "to_status"))
        self.assertEqual(
            events,
            [
                (EventType.STATUS_CHANGED, "IN_PROGRESS"),
                (EventType.STATUS_CHANGED, "RESOLVED"),
                (EventType.COMPLAINT_CLOSED, "CLOSED"),
            ],
        )
        self.assertEqual(len(LocMemNotificationAdapter.outbox), 3)
        self.assertEqual(Notification.objects.filter(delivery_status=DeliveryStatus.SENT).count(), 3)

    def test_rejected_transition_creates_no_notification(self):
        self.assertEqual(self.patch_status("Resolved").status_code, 409)
        self.assertEqual(self.patch_status("Closed").status_code, 409)
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(LocMemNotificationAdapter.outbox, [])

    def test_closure_without_resolution_creates_no_notification(self):
        force_state(self.complaint, S.RESOLVED)
        with self.captureOnCommitCallbacks(execute=True):
            r = self.client.post(self.close_url, {"resolutionDetails": "  "}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Notification.objects.count(), 0)

    def test_unauthorized_attempts_create_no_notification(self):
        roads_staff = make_verified_user(email="roads@example.com", role=Role.STAFF)
        self.roads.staff.add(roads_staff)
        self.assertEqual(self.patch_status("In Progress", client=client_for(roads_staff)).status_code, 404)
        self.assertEqual(self.patch_status("In Progress", client=client_for(self.citizen)).status_code, 403)
        self.assertEqual(Notification.objects.count(), 0)

    def test_message_does_not_leak_complaint_content(self):
        force_state(self.complaint, S.RESOLVED)
        self.close()
        message = Notification.objects.get().message
        self.assertIn(self.complaint.tracking_id, message)
        self.assertNotIn(RESOLUTION, message)
        self.assertNotIn(self.complaint.description, message)

    def test_notification_is_stored_even_if_not_yet_dispatched(self):
        self.patch_status("In Progress", execute=False)
        n = Notification.objects.get()
        self.assertEqual(n.delivery_status, DeliveryStatus.PENDING)
        self.assertEqual(LocMemNotificationAdapter.outbox, [])

    @override_settings(NOTIFICATION_ADAPTER=FAILING)
    def test_delivery_failure_does_not_undo_the_status_change(self):
        r = self.patch_status("In Progress")
        self.assertEqual(r.status_code, 200)
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, S.IN_PROGRESS)
        self.assertEqual(AuditLog.objects.count(), 1)
        n = Notification.objects.get()
        self.assertEqual((n.delivery_status, n.attempt_count), (DeliveryStatus.PENDING, 1))

    @override_settings(NOTIFICATION_ADAPTER=FAILING)
    def test_delivery_failure_does_not_undo_closure(self):
        force_state(self.complaint, S.RESOLVED)
        self.assertEqual(self.close().status_code, 200)
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, S.CLOSED)
        self.assertEqual(Notification.objects.get().delivery_status, DeliveryStatus.PENDING)
