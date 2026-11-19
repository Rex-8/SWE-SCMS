from django.conf import settings
from django.db import models
from django.db.models import Q


class EventType(models.TextChoices):
    STATUS_CHANGED = "STATUS_CHANGED", "Status changed"
    COMPLAINT_CLOSED = "COMPLAINT_CLOSED", "Complaint closed"


class DeliveryStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    SENT = "SENT", "Sent"
    FAILED = "FAILED", "Failed"


class Notification(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="notifications"
    )
    complaint = models.ForeignKey(
        "complaints.Complaint", on_delete=models.PROTECT, related_name="notifications"
    )
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    # The status change that triggered this notification.
    from_status = models.CharField(max_length=12)
    to_status = models.CharField(max_length=12)
    message = models.TextField()
    delivery_status = models.CharField(
        max_length=10, choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING
    )
    attempt_count = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=100, blank=True, default="")  # exception class name only
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["delivery_status", "created_at"], name="notification_pending_idx")]
        constraints = [
            models.CheckConstraint(
                condition=Q(delivery_status__in=DeliveryStatus.values),
                name="notification_delivery_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(delivery_status=DeliveryStatus.SENT, sent_at__isnull=False)
                | (~Q(delivery_status=DeliveryStatus.SENT) & Q(sent_at__isnull=True)),
                name="notification_sent_at_matches_status",
            ),
        ]

    def __str__(self):
        return f"{self.event_type} -> {self.recipient_id} ({self.delivery_status})"
