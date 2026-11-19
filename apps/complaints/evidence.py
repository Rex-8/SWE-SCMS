import os
from pathlib import Path

from django.conf import settings
from django.db import transaction

from .models import ComplaintEvidence

ALLOWED_FILES = {
    ".jpg": (b"\xff\xd8\xff", "image/jpeg"),
    ".jpeg": (b"\xff\xd8\xff", "image/jpeg"),
    ".png": (b"\x89PNG\r\n\x1a\n", "image/png"),
    ".pdf": (b"%PDF-", "application/pdf"),
}


class InvalidEvidence(Exception):
    pass


def validate_evidence_files(files):
    for uploaded in files:
        extension = Path(uploaded.name).suffix.lower()

        if extension not in ALLOWED_FILES:
            raise InvalidEvidence("Only JPG, PNG and PDF files are allowed.")

        if uploaded.size <= 0:
            raise InvalidEvidence("Empty files are not allowed.")

        if uploaded.size > settings.SCMS_MAX_EVIDENCE_SIZE_BYTES:
            raise InvalidEvidence("File exceeds the maximum allowed size.")

        signature, _ = ALLOWED_FILES[extension]

        header = uploaded.read(len(signature))
        uploaded.seek(0)

        if not header.startswith(signature):
            raise InvalidEvidence("File content does not match its extension.")


def attach_evidence(*, complaint, uploaded_by, files):
    files = list(files)
    validate_evidence_files(files)

    saved = []
    records = []

    try:
        with transaction.atomic():
            for uploaded in files:
                extension = Path(uploaded.name).suffix.lower()
                _, content_type = ALLOWED_FILES[extension]

                evidence = ComplaintEvidence(
                    complaint=complaint,
                    uploaded_by=uploaded_by,
                    original_name=os.path.basename(uploaded.name.replace("\\", "/"))[:255],
                    content_type=content_type,
                    size=uploaded.size,
                )

                evidence.file.save(
                    uploaded.name,
                    uploaded,
                    save=False,
                )

                saved.append((evidence.file.storage, evidence.file.name))
                evidence.save()
                records.append(evidence)

    except Exception:
        for storage, name in saved:
            storage.delete(name)
        raise

    return records
