import secrets
import string
from apps.audit.services import record as record_audit

from . import workflow
from .permissions import can_modify_complaint
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.routing.services import RoutingError, resolve_department

from .models import Category, Complaint, ComplaintStatus

TRACKING_ALPHABET = string.ascii_uppercase + string.digits
TRACKING_SUFFIX_LENGTH = 6
MAX_TRACKING_ATTEMPTS = 5


class CategoryUnavailable(Exception):
    """Unknown, inactive, or unroutable category (deliberately not distinguished)."""


class TrackingIDGenerationError(Exception):
    pass


def generate_tracking_id():
    """SCMS-YYYYMMDD-XXXXXX, random uppercase alphanumeric suffix."""
    suffix = "".join(secrets.choice(TRACKING_ALPHABET) for _ in range(TRACKING_SUFFIX_LENGTH))
    return f"SCMS-{timezone.localdate():%Y%m%d}-{suffix}"


def submit_complaint(*, citizen, category_id, description, location):
    """Create a complaint for `citizen`; the department always comes from the category."""
    category = Category.objects.select_related("department").filter(pk=category_id).first()
    if category is None:
        raise CategoryUnavailable
    try:
        department = resolve_department(category)
    except RoutingError:
        raise CategoryUnavailable from None

    for _ in range(MAX_TRACKING_ATTEMPTS):
        complaint = Complaint(
            tracking_id=generate_tracking_id(),
            citizen=citizen,
            category=category,
            department=department,
            status=ComplaintStatus.ASSIGNED,  # routing is synchronous, so it is assigned on creation
            description=description,
            location=location,
        )
        # FKs come from objects we just loaded; the DB enforces unique + check constraints.
        complaint.full_clean(
            exclude=("citizen", "category", "department", "assigned_staff"),
            validate_unique=False,
            validate_constraints=False,
        )
        try:
            with transaction.atomic():
                complaint.save(force_insert=True)
        except IntegrityError:
            # Only a tracking-ID collision is retried; anything else is a real error.
            if Complaint.objects.filter(tracking_id=complaint.tracking_id).exists():
                continue
            raise
        return complaint
    raise TrackingIDGenerationError

class ComplaintNotFound(Exception):
    """Unknown complaint OR the actor may not modify it (deliberately not distinguished)."""


class ResolutionRequired(Exception):
    pass


class InvalidTransition(Exception):
    pass


def _lock_for_update(*, complaint_id, actor):
    # Must be called inside transaction.atomic().
    complaint = (
        Complaint.objects.select_for_update(of=("self",))
        .select_related("department")
        .filter(pk=complaint_id)
        .first()
    )
    if complaint is None or not can_modify_complaint(actor, complaint):
        raise ComplaintNotFound
    return complaint


def change_status(*, complaint_id, actor, new_status, remark=""):
    with transaction.atomic():
        complaint = _lock_for_update(complaint_id=complaint_id, actor=actor)
        old = complaint.status
        if not workflow.can_transition(old, new_status):
            if new_status == ComplaintStatus.CLOSED:
                raise InvalidTransition("Complaints are closed through the close endpoint.")
            raise InvalidTransition(
                f"Cannot change status from {ComplaintStatus(old).label} "
                f"to {ComplaintStatus(new_status).label}."
            )
        complaint.status = new_status
        complaint.save(update_fields=["status", "updated_at"])
        record_audit(
            actor=actor,
            action="complaint.status_changed",
            obj=complaint,
            details={"from": old, "to": new_status, "remark": remark},
        )
    return complaint


def close_complaint(*, complaint_id, actor, resolution_details):
    details = (resolution_details or "").strip()
    with transaction.atomic():
        complaint = _lock_for_update(complaint_id=complaint_id, actor=actor)
        if not details:
            raise ResolutionRequired
        old = complaint.status
        if old != workflow.CLOSE_FROM:
            raise InvalidTransition(
                f"Only resolved complaints can be closed (current status: {ComplaintStatus(old).label})."
            )
        complaint.status = ComplaintStatus.CLOSED
        complaint.resolution_details = details
        complaint.closed_at = timezone.now()
        complaint.save(update_fields=["status", "resolution_details", "closed_at", "updated_at"])
        record_audit(
            actor=actor,
            action="complaint.closed",
            obj=complaint,
            details={"from": old, "to": ComplaintStatus.CLOSED.value, "resolution_details": details},
        )
    return complaint
