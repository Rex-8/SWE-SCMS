import secrets
import string

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
