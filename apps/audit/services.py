from .models import AuditLog


def record(*, actor, action, obj, details=None):
    """Append an audit entry. Runs inside the caller's transaction, so the audited change
    and its audit row commit or roll back together. Never put secrets in `details`."""
    return AuditLog.objects.create(
        actor=actor,
        action=action,
        object_type=obj._meta.label_lower,
        object_id=str(obj.pk),
        details=details or {},
    )
