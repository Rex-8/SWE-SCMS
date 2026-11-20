import re

from apps.complaints.models import Complaint
from apps.complaints.permissions import can_view_complaint

TRACKING_ID_RE = re.compile(r"^SCMS-\d{8}-[A-Z0-9]{6}$")


def get_trackable_complaint(*, user, tracking_id):
    """Complaint if it exists AND `user` may see it; otherwise None (callers can't tell which)."""
    tracking_id = (tracking_id or "").strip().upper()
    if not TRACKING_ID_RE.match(tracking_id):
        return None
    complaint = (
        Complaint.objects.select_related("category", "department").filter(tracking_id=tracking_id).first()
    )
    if complaint is None or not can_view_complaint(user, complaint):
        return None
    return complaint
