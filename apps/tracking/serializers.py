from rest_framework import serializers


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
