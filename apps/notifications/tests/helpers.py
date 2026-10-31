from django.test import override_settings

from apps.complaints.tests.helpers import ComplaintAPITestCase
from apps.notifications.adapters import LocMemNotificationAdapter, NotificationAdapter


class FailingAdapter(NotificationAdapter):
    def send(self, *, channel, address, message):
        raise RuntimeError("provider down")


class FlakyAdapter(NotificationAdapter):
    failures_left = 0
    sent = []

    def send(self, *, channel, address, message):
        if FlakyAdapter.failures_left > 0:
            FlakyAdapter.failures_left -= 1
            raise RuntimeError("provider down")
        FlakyAdapter.sent.append(message)


@override_settings(NOTIFICATION_ADAPTER="apps.notifications.adapters.LocMemNotificationAdapter")
class NotificationTestCase(ComplaintAPITestCase):
    def setUp(self):
        super().setUp()
        LocMemNotificationAdapter.outbox.clear()
        FlakyAdapter.failures_left = 0
        FlakyAdapter.sent.clear()
