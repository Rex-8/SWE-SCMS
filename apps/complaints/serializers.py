from rest_framework import serializers

MAX_DESCRIPTION_LENGTH = 5000
MAX_LOCATION_LENGTH = 255


class ComplaintSubmitSerializer(serializers.Serializer):
    # No citizen/department/status/trackingId fields: such input is ignored.
    categoryId = serializers.IntegerField(min_value=1, max_value=2**63 - 1)
    description = serializers.CharField(max_length=MAX_DESCRIPTION_LENGTH)
    location = serializers.CharField(max_length=MAX_LOCATION_LENGTH)
