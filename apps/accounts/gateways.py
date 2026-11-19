import sys

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class OTPGateway:
    def send(self, *, channel, recipient, code):
        raise NotImplementedError


class ConsoleOTPGateway(OTPGateway):
    """Development mock. Writes to stdout (never to logging); refuses to run in production."""

    def send(self, *, channel, recipient, code):
        if not settings.DEBUG:
            raise ImproperlyConfigured("ConsoleOTPGateway is for development only.")
        sys.stdout.write(f"[DEV OTP] {channel}:{recipient} code={code}\n")


class LocMemOTPGateway(OTPGateway):
    """Test gateway: collects messages in memory."""

    outbox = []

    def send(self, *, channel, recipient, code):
        self.outbox.append({"channel": channel, "recipient": recipient, "code": code})
