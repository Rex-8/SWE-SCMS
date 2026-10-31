from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("created_at", "event_type", "recipient", "complaint", "delivery_status", "attempt_count")
    list_filter = ("delivery_status", "event_type")
    search_fields = ("complaint__tracking_id",)
    readonly_fields = [f.name for f in Notification._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
