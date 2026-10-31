from rest_framework import serializers

from . import workflow

MAX_DESCRIPTION_LENGTH = 5000
MAX_LOCATION_LENGTH = 255
MAX_REMARK_LENGTH = 1000


class ComplaintSubmitSerializer(serializers.Serializer):
    # No citizen/department/status/trackingId fields: such input is ignored.
    categoryId = serializers.IntegerField(min_value=1, max_value=2**63 - 1)
    description = serializers.CharField(max_length=MAX_DESCRIPTION_LENGTH)
    location = serializers.CharField(max_length=MAX_LOCATION_LENGTH)


class StatusUpdateSerializer(serializers.Serializer):
    status = serializers.CharField(max_length=32)
    remark = serializers.CharField(
        required=False, allow_blank=True, max_length=MAX_REMARK_LENGTH, default=""
    )

    def validate_status(self, value):
        parsed = workflow.parse_status(value)
        if parsed is None:
            raise serializers.ValidationError("Unknown status.")
        return parsed


class CloseSerializer(serializers.Serializer):
    resolutionDetails = serializers.CharField(max_length=MAX_DESCRIPTION_LENGTH)  # blank rejected


class AssignedComplaintSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    trackingId = serializers.CharField(source="tracking_id", read_only=True)
    category = serializers.CharField(source="category.name", read_only=True)
    department = serializers.CharField(source="department.name", read_only=True)
    location = serializers.CharField(read_only=True)
    status = serializers.CharField(source="get_status_display", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)
