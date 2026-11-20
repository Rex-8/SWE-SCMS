import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.module_loading import import_string

from apps.complaints.models import ComplaintStatus

from .models import DeliveryStatus, EventType, Notification

logger = logging.getLogger(__name__)


def _contact(user):
    return ("email", user.email) if user.email else ("mobile", user.mobile)


def notify_status_change(*, complaint, old_status, new_status):
    """Record a notification for the complaint's citizen and schedule delivery after commit.

    The row is written inside the caller's transaction (it cannot be lost if the status
    change commits); delivery happens only after commit and can never undo the change.
    """
    closed = new_status == ComplaintStatus.CLOSED.value
    old_label = ComplaintStatus(old_status).label
    new_label = ComplaintStatus(new_status).label
    notification = Notification.objects.create(
        recipient_id=complaint.citizen_id,
        complaint=complaint,
        event_type=EventType.COMPLAINT_CLOSED if closed else EventType.STATUS_CHANGED,
        from_status=old_status,
        to_status=new_status,
        message=f"Your complaint {complaint.tracking_id} status changed from {old_label} to {new_label}.",
    )
    transaction.on_commit(lambda: _dispatch_after_commit(notification.pk))
    return notification


def _dispatch_after_commit(notification_id):
    try:
        dispatch(notification_id)
    except Exception:
        # Nothing here may affect the already-committed status change. The row stays
        # PENDING and the retry command will pick it up.
        logger.error("Notification dispatch crashed: id=%s", notification_id)


def dispatch(notification_id):
    """Attempt one delivery of a PENDING notification. Returns it, or None if not pending."""
    with transaction.atomic():
        notification = (
            Notification.objects.select_for_update()
            .select_related("recipient")
            .filter(pk=notification_id, delivery_status=DeliveryStatus.PENDING)
            .first()
        )
        if notification is None:
            return None
        channel, address = _contact(notification.recipient)
        notification.attempt_count += 1
        try:
            import_string(settings.NOTIFICATION_ADAPTER)().send(
                channel=channel, address=address, message=notification.message
            )
        except Exception as exc:
            # Only the exception class is kept; messages can carry provider secrets.
            notification.last_error = type(exc).__name__[:100]
            if notification.attempt_count >= settings.NOTIFICATION_MAX_ATTEMPTS:
                notification.delivery_status = DeliveryStatus.FAILED
            logger.warning(
                "Notification delivery failed: id=%s attempt=%s error=%s",
                notification.pk,
                notification.attempt_count,
                notification.last_error,
            )
        else:
            notification.delivery_status = DeliveryStatus.SENT
            notification.sent_at = timezone.now()
            notification.last_error = ""
        notification.save(update_fields=["attempt_count", "last_error", "delivery_status", "sent_at"])
    return notification


def dispatch_pending(limit=100):
    """One retry pass over PENDING notifications (oldest first). Returns the processed rows."""
    ids = list(
        Notification.objects.filter(
            delivery_status=DeliveryStatus.PENDING,
            attempt_count__lt=settings.NOTIFICATION_MAX_ATTEMPTS,
        )
        .order_by("created_at", "id")
        .values_list("pk", flat=True)[:limit]
    )
    results = (dispatch(pk) for pk in ids)
    return [n for n in results if n is not None]
