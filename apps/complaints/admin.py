from django.contrib import admin

from .models import Category, Complaint, Department


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    search_fields = ("name",)
    filter_horizontal = ("staff",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "department", "is_active")
    list_filter = ("department", "is_active")
    search_fields = ("name",)


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    """Read-only: changes must go through the service layer so they are audited."""

    list_display = ("tracking_id", "category", "department", "status", "created_at")
    list_filter = ("status", "department")
    search_fields = ("tracking_id",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
