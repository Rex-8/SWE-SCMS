from unittest import mock

from django.db import IntegrityError, transaction
from django.test import SimpleTestCase
from django.utils import timezone

from apps.complaints import services
from apps.complaints.models import Complaint

from .helpers import ComplaintAPITestCase

TARGET = "apps.complaints.services.generate_tracking_id"


class GenerateTrackingIDTests(SimpleTestCase):
    def test_format_and_date(self):
        tid = services.generate_tracking_id()
        self.assertRegex(tid, r"^SCMS-\d{8}-[A-Z0-9]{6}$")
        self.assertEqual(tid[5:13], timezone.localdate().strftime("%Y%m%d"))

    def test_suffix_is_random(self):
        suffixes = {services.generate_tracking_id()[-6:] for _ in range(50)}
        self.assertGreater(len(suffixes), 45)


class CollisionTests(ComplaintAPITestCase):
    EXISTING = "SCMS-20261030-AAAAAA"
    FRESH = "SCMS-20261030-BBBBBB"

    def setUp(self):
        super().setUp()
        self.make_complaint(tracking_id=self.EXISTING)

    def submit_via_service(self):
        return services.submit_complaint(
            citizen=self.citizen, category_id=self.lights.pk, description="d", location="l"
        )

    def test_uniqueness_is_enforced_by_the_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_complaint(tracking_id=self.EXISTING)

    def test_collision_is_retried_with_a_new_id(self):
        with mock.patch(TARGET, side_effect=[self.EXISTING, self.FRESH]) as gen:
            complaint = self.submit_via_service()
        self.assertEqual(complaint.tracking_id, self.FRESH)
        self.assertEqual(gen.call_count, 2)
        self.assertEqual(Complaint.objects.count(), 2)

    def test_gives_up_after_max_attempts(self):
        with mock.patch(TARGET, return_value=self.EXISTING) as gen:
            with self.assertRaises(services.TrackingIDGenerationError):
                self.submit_via_service()
        self.assertEqual(gen.call_count, services.MAX_TRACKING_ATTEMPTS)
        self.assertEqual(Complaint.objects.count(), 1)

    def test_api_recovers_from_collision(self):
        self.client.force_login(self.citizen)
        with mock.patch(TARGET, side_effect=[self.EXISTING, self.FRESH]):
            r = self.submit()
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["trackingId"], self.FRESH)

    def test_api_returns_503_when_ids_are_exhausted(self):
        self.client.force_login(self.citizen)
        with mock.patch(TARGET, return_value=self.EXISTING):
            r = self.submit()
        self.assertEqual(r.status_code, 503)
        self.assertEqual(Complaint.objects.count(), 1)

    def test_returned_id_matches_stored_complaint(self):
        self.client.force_login(self.citizen)
        tid = self.submit().json()["trackingId"]
        self.assertTrue(Complaint.objects.filter(tracking_id=tid, citizen=self.citizen).exists())
