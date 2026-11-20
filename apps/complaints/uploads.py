from pathlib import Path

MAX_UPLOAD_SIZE = 5 * 1024 * 1024
_ALLOWED = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".pdf": "application/pdf"}


def validate_evidence(upload):
    """Validate extension, declared MIME type, size and file signature before storage."""
    ext = Path(upload.name).suffix.lower()
    if ext not in _ALLOWED or upload.size > MAX_UPLOAD_SIZE:
        return False
    if upload.content_type not in {_ALLOWED[ext], "application/octet-stream"}:
        return False
    head = upload.read(8)
    upload.seek(0)
    if ext == ".pdf":
        return head.startswith(b"%PDF-")
    if ext in {".jpg", ".jpeg"}:
        return head.startswith(b"\xff\xd8\xff")
    return head.startswith(b"\x89PNG\r\n\x1a\n")
