from unittest import mock

from django.core import mail
from django.core.cache.backends.db import DatabaseCache
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

from apps.accounts.gateways import DeliveryOTPGateway
from apps.notifications import delivery
from apps.notifications.adapters import DeliveryNotificationAdapter
from apps.notifications.delivery import DeliveryError, SMSProvider

SECRET = "sms-secret-key-value"


class FakeSMS(SMSProvider):
    sent = []

    def send(self, *, to, message):
        FakeSMS.sent.append((to, message))


class BrokenSMS(SMSProvider):
    def send(self, *, to, message):
        raise RuntimeError(f"provider said key={SECRET}")


FAKE = "apps.notifications.tests.test_delivery.FakeSMS"
BROKEN = "apps.notifications.tests.test_delivery.BrokenSMS"
HTTP = "apps.notifications.delivery.HTTPSMSProvider"


class EmailDeliveryTests(SimpleTestCase):
    def test_email_is_sent_through_configured_backend(self):
        delivery.send_email(to="a@example.com", subject="s", body="hello")
        self.assertEqual(mail.outbox[-1].to, ["a@example.com"])

    def test_backend_failure_becomes_generic_error(self):
        with mock.patch.object(delivery, "send_mail", side_effect=OSError(f"auth {SECRET}")):
            with self.assertRaises(DeliveryError) as ctx:
                delivery.send_email(to="a@example.com", subject="s", body="b")
        self.assertNotIn(SECRET, repr(ctx.exception))
        self.assertIsNone(ctx.exception.__cause__)

    @override_settings(EMAIL_BACKEND=delivery.SMTP_BACKEND, EMAIL_HOST="")
    def test_smtp_without_host_is_a_configuration_error(self):
        with self.assertRaises(ImproperlyConfigured):
            delivery.send_email(to="a@example.com", subject="s", body="b")


class SMSDeliveryTests(SimpleTestCase):
    def setUp(self):
        FakeSMS.sent.clear()

    @override_settings(SMS_PROVIDER="")
    def test_no_provider_is_a_configuration_error(self):
        with self.assertRaises(ImproperlyConfigured):
            delivery.send_sms(to="+910000000000", message="m")

    @override_settings(SMS_PROVIDER="no.such.Provider")
    def test_invalid_provider_path(self):
        with self.assertRaises(ImproperlyConfigured):
            delivery.send_sms(to="+910000000000", message="m")

    @override_settings(SMS_PROVIDER=FAKE)
    def test_success(self):
        delivery.send_sms(to="+910000000000", message="m")
        self.assertEqual(FakeSMS.sent, [("+910000000000", "m")])

    @override_settings(SMS_PROVIDER=BROKEN)
    def test_provider_failure_is_generic(self):
        with self.assertRaises(DeliveryError) as ctx:
            delivery.send_sms(to="+910000000000", message="m")
        self.assertNotIn(SECRET, repr(ctx.exception))

    @override_settings(SMS_PROVIDER=HTTP, SMS_API_URL="http://insecure.example.com", SMS_API_KEY="k")
    def test_http_provider_requires_https(self):
        with self.assertRaises(ImproperlyConfigured):
            delivery.send_sms(to="+910000000000", message="m")

    @override_settings(SMS_PROVIDER=HTTP, SMS_API_URL="https://sms.example.com/send", SMS_API_KEY="k")
    def test_http_provider_posts_with_bearer_key(self):
        with mock.patch.object(delivery.urllib.request, "urlopen") as urlopen:
            delivery.send_sms(to="+910000000000", message="m")
        req = urlopen.call_args.args[0]
        self.assertEqual(req.get_header("Authorization"), "Bearer k")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 10)

    @override_settings(SMS_PROVIDER=HTTP, SMS_API_URL="https://sms.example.com/send", SMS_API_KEY=SECRET)
    def test_http_provider_failure_hides_secret(self):
        with mock.patch.object(delivery.urllib.request, "urlopen", side_effect=OSError(SECRET)):
            with self.assertRaises(DeliveryError) as ctx:
                delivery.send_sms(to="+910000000000", message="m")
        self.assertNotIn(SECRET, repr(ctx.exception))


class AdapterRoutingTests(SimpleTestCase):
    def setUp(self):
        FakeSMS.sent.clear()

    def test_otp_gateway_routes_email_and_mobile(self):
        with override_settings(SMS_PROVIDER=FAKE):
            DeliveryOTPGateway().send(channel="email", recipient="a@example.com", code="123456")
            DeliveryOTPGateway().send(channel="mobile", recipient="+910000000000", code="654321")
        self.assertIn("123456", mail.outbox[-1].body)
        self.assertIn("654321", FakeSMS.sent[-1][1])

    def test_notification_adapter_routes_email_and_mobile(self):
        with override_settings(SMS_PROVIDER=FAKE):
            DeliveryNotificationAdapter().send(channel="email", address="a@example.com", message="one")
            DeliveryNotificationAdapter().send(channel="mobile", address="+910000000000", message="two")
        self.assertEqual(mail.outbox[-1].body, "one")
        self.assertEqual(FakeSMS.sent[-1][1], "two")

    def test_unknown_channel_rejected(self):
        with self.assertRaises(DeliveryError):
            DeliveryNotificationAdapter().send(channel="pigeon", address="x", message="m")

    @override_settings(SMS_PROVIDER="")
    def test_mobile_without_provider_fails_cleanly(self):
        with self.assertRaises(ImproperlyConfigured):
            DeliveryNotificationAdapter().send(channel="mobile", address="+910000000000", message="m")


class SharedCacheTests(TestCase):
    def test_database_cache_is_shared_between_instances(self):
        call_command("createcachetable", "scms_cache_test", verbosity=0)
        a = DatabaseCache("scms_cache_test", {})
        b = DatabaseCache("scms_cache_test", {})
        a.set("throttle:key", [1, 2, 3], 60)
        self.assertEqual(b.get("throttle:key"), [1, 2, 3])
