from django.utils import timezone

from apps.complaints.models import Complaint, ComplaintStatus


def force_state(complaint, status):
    """Put a complaint in `status` directly in the DB, satisfying the closure constraints."""
    if status == ComplaintStatus.CLOSED:
        extra = {"closed_at": timezone.now(), "resolution_details": "Fixed"}
    else:
        extra = {"closed_at": None, "resolution_details": ""}
    Complaint.objects.filter(pk=complaint.pk).update(status=status, **extra)
    complaint.refresh_from_db()
