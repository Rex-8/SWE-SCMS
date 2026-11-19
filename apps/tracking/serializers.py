from django.urls import reverse
from rest_framework import serializers


class EvidenceSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    fileName = serializers.CharField(
        source="original_name",
        read_only=True,
    )
    downloadUrl = serializers.SerializerMethodField()

    def get_downloadUrl(self, obj):
        return reverse(
            "complaints:evidence-download",
            kwargs={"pk": obj.pk},
        )


class ComplaintStatusHistorySerializer(serializers.Serializer):
    fromStatus = serializers.SerializerMethodField()
    toStatus = serializers.CharField(source="get_to_status_display", read_only=True)
    remark = serializers.CharField(read_only=True)
    actorName = serializers.CharField(source="actor.name", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    def get_fromStatus(self, obj):
        if obj.from_status is None:
            return None
        return obj.get_from_status_display()


class ComplaintTrackingSerializer(serializers.Serializer):
    trackingId = serializers.CharField(source="tracking_id", read_only=True)
    category = serializers.CharField(source="category.name", read_only=True)
    description = serializers.CharField(read_only=True)
    evidence = EvidenceSerializer(many=True, read_only=True)
    history = ComplaintStatusHistorySerializer(source="status_history", many=True, read_only=True)
    location = serializers.CharField(read_only=True)
    status = serializers.CharField(source="get_status_display", read_only=True)
    department = serializers.CharField(source="department.name", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)
    closedAt = serializers.DateTimeField(source="closed_at", read_only=True, allow_null=True)
