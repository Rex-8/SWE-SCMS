import contextlib
import io

from django.db import IntegrityError, transaction
from django.test import override_settings

from apps.accounts.models import Role, User
from apps.complaints.models import ComplaintStatus as S
from apps.notifications.adapters import LocMemNotificationAdapter
from apps.notifications.models import DeliveryStatus, EventType, Notification
from apps.notifications.services import dispatch, dispatch_pending, notify_status_change

from .helpers import NotificationTestCase

FAILING = "apps.notifications.tests.helpers.FailingAdapter"
FLAKY = "apps.notifications.tests.helpers.FlakyAdapter"
CONSOLE = "apps.notifications.adapters.ConsoleNotificationAdapter"


class DispatchTests(NotificationTestCase):
    def setUp(self):
        super().setUp()
        self.complaint = self.make_complaint()

    def notify(self, old=S.ASSIGNED, new=S.IN_PROGRESS, execute=True, complaint=None):
        with self.captureOnCommitCallbacks(execute=execute):
            n = notify_status_change(
                complaint=complaint or self.complaint, old_status=old.value, new_status=new.value
            )
        n.refresh_from_db()
        return n

    def test_row_records_the_triggering_change_and_waits_for_commit(self):
        n = self.notify(execute=False)
        self.assertEqual(n.recipient, self.citizen)
        self.assertEqual(n.complaint, self.complaint)
        self.assertEqual(n.event_type, EventType.STATUS_CHANGED)
        self.assertEqual((n.from_status, n.to_status), ("ASSIGNED", "IN_PROGRESS"))
        self.assertEqual(n.delivery_status, DeliveryStatus.PENDING)
        self.assertEqual(n.attempt_count, 0)
        self.assertIn(self.complaint.tracking_id, n.message)
        self.assertIn("Assigned", n.message)
        self.assertIn("In Progress", n.message)
        self.assertEqual(LocMemNotificationAdapter.outbox, [])

    def test_delivered_after_commit(self):
        n = self.notify()
        self.assertEqual(n.delivery_status, DeliveryStatus.SENT)
        self.assertEqual(n.attempt_count, 1)
        self.assertIsNotNone(n.sent_at)
        self.assertEqual(
            LocMemNotificationAdapter.outbox,
            [{"channel": "email", "address": "citizen@example.com", "message": n.message}],
        )

    def test_closing_uses_the_closed_event_type(self):
        n = self.notify(old=S.RESOLVED, new=S.CLOSED)
        self.assertEqual(n.event_type, EventType.COMPLAINT_CLOSED)

    def test_mobile_only_citizen_is_notified_by_mobile(self):
        citizen = User.objects.create_user(mobile="9876543210", name="M", is_verified=True)
        complaint = self.make_complaint(tracking_id="SCMS-20261030-MMMMMM", citizen=citizen)
        self.notify(complaint=complaint)
        sent = LocMemNotificationAdapter.outbox[0]
        self.assertEqual((sent["channel"], sent["address"]), ("mobile", "9876543210"))

    @override_settings(NOTIFICATION_ADAPTER=FAILING)
    def test_failure_is_retried_then_marked_failed(self):
        n = self.notify()
        self.assertEqual((n.delivery_status, n.attempt_count, n.last_error), ("PENDING", 1, "RuntimeError"))
        self.assertEqual(dispatch(n.pk).attempt_count, 2)
        third = dispatch(n.pk)
        self.assertEqual((third.delivery_status, third.attempt_count), ("FAILED", 3))
        self.assertIsNone(dispatch(n.pk))  # no longer pending: not attempted again
        n.refresh_from_db()
        self.assertEqual(n.attempt_count, 3)

    @override_settings(NOTIFICATION_ADAPTER=FLAKY)
    def test_retry_recovers_after_a_transient_failure(self):
        from .helpers import FlakyAdapter

        FlakyAdapter.failures_left = 1
        n = self.notify()
        self.assertEqual(n.delivery_status, DeliveryStatus.PENDING)
        done = dispatch(n.pk)
        self.assertEqual((done.delivery_status, done.attempt_count), ("SENT", 2))
        self.assertIsNotNone(done.sent_at)
        self.assertEqual(FlakyAdapter.sent, [n.message])

    @override_settings(NOTIFICATION_ADAPTER=FAILING)
    def test_only_the_exception_class_is_stored_or_logged(self):
        with self.assertLogs("apps.notifications.services", level="WARNING") as logs:
            n = self.notify()
        self.assertEqual(n.last_error, "RuntimeError")
        self.assertNotIn("provider down", "\n".join(logs.output))
        self.assertNotIn(n.message, "\n".join(logs.output))

    def test_dispatch_pending_only_touches_pending_rows(self):
        self.notify()  # SENT
        failed = self.notify(execute=False)
        Notification.objects.filter(pk=failed.pk).update(delivery_status="FAILED", attempt_count=3)
        pending = self.notify(execute=False)
        LocMemNotificationAdapter.outbox.clear()
        results = dispatch_pending()
        self.assertEqual([n.pk for n in results], [pending.pk])
        self.assertEqual(len(LocMemNotificationAdapter.outbox), 1)

    def test_dispatch_pending_respects_the_limit(self):
        for _ in range(3):
            self.notify(execute=False)
        self.assertEqual(len(dispatch_pending(limit=2)), 2)

    def test_unknown_id_is_ignored(self):
        self.assertIsNone(dispatch(999999))

    @override_settings(NOTIFICATION_ADAPTER=CONSOLE)
    def test_console_adapter_refuses_to_run_in_production(self):
        n = self.notify()  # tests run with DEBUG=False
        self.assertEqual((n.delivery_status, n.last_error), ("PENDING", "ImproperlyConfigured"))

    @override_settings(NOTIFICATION_ADAPTER=CONSOLE, DEBUG=True)
    def test_console_adapter_prints_a_safe_summary_in_development(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            n = self.notify()
        self.assertEqual(n.delivery_status, DeliveryStatus.SENT)
        self.assertIn(self.complaint.tracking_id, out.getvalue())
        self.assertNotIn("citizen@example.com", out.getvalue())

    def test_sent_requires_a_sent_timestamp_in_the_database(self):
        n = self.notify(execute=False)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Notification.objects.filter(pk=n.pk).update(delivery_status=DeliveryStatus.SENT)
