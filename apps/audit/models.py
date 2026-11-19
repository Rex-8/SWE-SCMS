from django.conf import settings
from django.db import models


class AppendOnlyError(Exception):
    """Raised on any attempt to modify or delete an audit record."""


class AuditQuerySet(models.QuerySet):
    def update(self, *args, **kwargs):
        raise AppendOnlyError("Audit records are append-only.")

    def bulk_update(self, *args, **kwargs):
        raise AppendOnlyError("Audit records are append-only.")

    def delete(self):
        raise AppendOnlyError("Audit records are append-only.")


class AuditLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="audit_entries"
    )
    action = models.CharField(max_length=64)
    object_type = models.CharField(max_length=100)
    object_id = models.CharField(max_length=64)
    details = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    objects = AuditQuerySet.as_manager()

    class Meta:
        ordering = ["-timestamp", "-id"]
        indexes = [
            models.Index(fields=["object_type", "object_id"], name="audit_object_idx"),
            models.Index(fields=["-timestamp"], name="audit_timestamp_idx"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AppendOnlyError("Audit records are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyError("Audit records are append-only.")

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M:%S} {self.action} {self.object_type}#{self.object_id}"
