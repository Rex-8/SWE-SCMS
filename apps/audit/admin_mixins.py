from .services import record


class AuditedAdminMixin:
    """Mirror Django-admin add/change/delete actions into the append-only AuditLog.

    The admin calls these hooks inside the request's transaction, so the audit row and the
    change commit or roll back together. Only Django's own change message is stored (field
    labels, never values), so credentials cannot reach the log.
    """

    def log_addition(self, request, obj, message):
        entry = super().log_addition(request, obj, message)
        record(actor=request.user, action="admin.created", obj=obj, details={"message": message})
        return entry

    def log_change(self, request, obj, message):
        entry = super().log_change(request, obj, message)
        record(actor=request.user, action="admin.updated", obj=obj, details={"message": message})
        return entry

    def log_deletions(self, request, queryset):
        # Must run before the deletion, while the objects still exist.
        for obj in list(queryset):
            record(actor=request.user, action="admin.deleted", obj=obj, details={"repr": str(obj)})
        return super().log_deletions(request, queryset)
