from rest_framework import serializers
from apps.complaints.models import ComplaintStatus


class ComplaintTrackingSerializer(serializers.Serializer):
    trackingId = serializers.CharField(source="tracking_id", read_only=True)
    category = serializers.CharField(source="category.name", read_only=True)
    description = serializers.CharField(read_only=True)
    location = serializers.CharField(read_only=True)
    status = serializers.CharField(source="get_status_display", read_only=True)
    department = serializers.CharField(source="department.name", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)
    closedAt = serializers.DateTimeField(source="closed_at", read_only=True, allow_null=True)
    resolutionDetails = serializers.CharField(source="resolution_details", read_only=True)
    history = serializers.SerializerMethodField()
    attachments = serializers.SerializerMethodField()

    def get_history(self, obj):
        return [{"from": h.from_status, "to": ComplaintStatus(h.to_status).label,
                 "remark": h.remark, "actor": h.actor.name, "at": h.created_at}
                for h in obj.history.select_related("actor").all()]

    def get_attachments(self, obj):
        request = self.context.get("request")
        return [{"name": a.original_name, "url": request.build_absolute_uri(f"/api/v1/attachments/{a.pk}") if request else f"/api/v1/attachments/{a.pk}"}
                for a in obj.evidence_files.all()]
