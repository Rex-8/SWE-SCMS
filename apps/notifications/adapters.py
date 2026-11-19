import sys

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .delivery import deliver


class NotificationAdapter:
    """Delivery backend. Implementations must raise on failure and must not log secrets."""

    def send(self, *, channel, address, message):
        raise NotImplementedError


class ConsoleNotificationAdapter(NotificationAdapter):
    """Development mock: prints a safe summary (no address). Refuses to run in production."""

    def send(self, *, channel, address, message):
        if not settings.DEBUG:
            raise ImproperlyConfigured(
                "ConsoleNotificationAdapter is for development only; configure a real adapter."
            )
        sys.stdout.write(f"[DEV NOTIFICATION] via {channel}: {message}\n")


class LocMemNotificationAdapter(NotificationAdapter):
    """Test adapter: collects messages in memory."""

    outbox = []

    def send(self, *, channel, address, message):
        self.outbox.append({"channel": channel, "address": address, "message": message})


class DeliveryNotificationAdapter(NotificationAdapter):
    """Real adapter: email via Django's configured email backend, mobile via SMS_PROVIDER."""

    def send(self, *, channel, address, message):
        deliver(channel=channel, address=address, subject="SCMS complaint update", body=message)
