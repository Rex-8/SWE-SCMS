from io import StringIO

from django.core.management import call_command
from django.test import override_settings

from apps.complaints.models import ComplaintStatus as S
from apps.notifications.adapters import LocMemNotificationAdapter
from apps.notifications.models import DeliveryStatus, Notification
from apps.notifications.services import notify_status_change

from .helpers import NotificationTestCase

FAILING = "apps.notifications.tests.helpers.FailingAdapter"


class SendPendingCommandTests(NotificationTestCase):
    def setUp(self):
        super().setUp()
        self.complaint = self.make_complaint()
        with self.captureOnCommitCallbacks(execute=False):
            notify_status_change(
                complaint=self.complaint, old_status=S.ASSIGNED.value, new_status=S.IN_PROGRESS.value
            )

    def run_command(self):
        out = StringIO()
        call_command("send_pending_notifications", stdout=out)
        return out.getvalue().strip()

    def test_delivers_pending_notifications(self):
        self.assertEqual(self.run_command(), "sent=1 failed=0 pending=0")
        self.assertEqual(Notification.objects.get().delivery_status, DeliveryStatus.SENT)
        self.assertEqual(len(LocMemNotificationAdapter.outbox), 1)

    def test_nothing_to_do_the_second_time(self):
        self.run_command()
        self.assertEqual(self.run_command(), "sent=0 failed=0 pending=0")
        self.assertEqual(len(LocMemNotificationAdapter.outbox), 1)

    @override_settings(NOTIFICATION_ADAPTER=FAILING)
    def test_failures_are_retried_until_marked_failed(self):
        self.assertEqual(self.run_command(), "sent=0 failed=0 pending=1")
        self.assertEqual(self.run_command(), "sent=0 failed=0 pending=1")
        self.assertEqual(self.run_command(), "sent=0 failed=1 pending=0")
        self.assertEqual(self.run_command(), "sent=0 failed=0 pending=0")
