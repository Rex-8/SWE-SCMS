
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.complaints.models import Complaint, ComplaintEvidence
from apps.complaints.tests.helpers import (
    COMPLAINTS_URL,
    TRACK_URL,
    ComplaintAPITestCase,
)

PNG_CONTENT = b"\x89PNG\r\n\x1a\n" + b"image-data"


class EvidenceUploadTests(ComplaintAPITestCase):
    def setUp(self):
        super().setUp()

        self.media_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.media_dir.cleanup)

        media_override = override_settings(MEDIA_ROOT=self.media_dir.name)
        media_override.enable()
        self.addCleanup(media_override.disable)

        self.client.force_login(self.citizen)

    def upload(self, uploaded_file):
        data = {
            **self.payload(),
            "files": uploaded_file,
        }
        return self.client.post(COMPLAINTS_URL, data, format="multipart")

    def create_evidence(self):
        response = self.upload(
            SimpleUploadedFile(
                "streetlight.png",
                PNG_CONTENT,
                content_type="image/png",
            )
        )
        self.assertEqual(response.status_code, 201)
        return ComplaintEvidence.objects.get()

    def test_valid_evidence_is_saved(self):
        response = self.upload(
            SimpleUploadedFile(
                "streetlight.png",
                PNG_CONTENT,
                content_type="image/png",
            )
        )

        self.assertEqual(response.status_code, 201)

        complaint = Complaint.objects.get()
        evidence = ComplaintEvidence.objects.get()

        self.assertEqual(evidence.complaint, complaint)
        self.assertEqual(evidence.uploaded_by, self.citizen)
        self.assertEqual(evidence.original_name, "streetlight.png")
        self.assertEqual(evidence.content_type, "image/png")
        self.assertEqual(evidence.size, len(PNG_CONTENT))
        self.assertTrue(evidence.file.storage.exists(evidence.file.name))

    def test_invalid_extension_is_rejected(self):
        response = self.upload(
            SimpleUploadedFile("malware.exe", b"invalid")
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Complaint.objects.count(), 0)
        self.assertEqual(ComplaintEvidence.objects.count(), 0)

    def test_mismatched_file_signature_is_rejected(self):
        response = self.upload(
            SimpleUploadedFile(
                "fake.png",
                b"%PDF-not-a-png",
            )
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Complaint.objects.count(), 0)

    def test_file_size_limit_is_enforced(self):
        with override_settings(SCMS_MAX_EVIDENCE_SIZE_BYTES=10):
            response = self.upload(
                SimpleUploadedFile("large.png", PNG_CONTENT)
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Complaint.objects.count(), 0)

    def test_owner_can_download_evidence(self):
        evidence = self.create_evidence()

        tracking = self.client.get(
            f"{TRACK_URL}/{evidence.complaint.tracking_id}"
        ).json()

        self.assertEqual(len(tracking["evidence"]), 1)

        metadata = tracking["evidence"][0]
        self.assertEqual(metadata["fileName"], "streetlight.png")

        response = self.client.get(metadata["downloadUrl"])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(
            b"".join(response.streaming_content),
            PNG_CONTENT,
        )
        response.close()

    def test_other_citizen_cannot_download_evidence(self):
        evidence = self.create_evidence()

        from django.urls import reverse

        url = reverse(
            "complaints:evidence-download",
            kwargs={"pk": evidence.pk},
        )

        self.client.force_login(self.other_citizen)

        self.assertEqual(self.client.get(url).status_code, 404)

    def test_department_staff_can_download_evidence(self):
        evidence = self.create_evidence()

        from django.urls import reverse

        url = reverse(
            "complaints:evidence-download",
            kwargs={"pk": evidence.pk},
        )

        self.client.force_login(self.staff)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        response.close()
