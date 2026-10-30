from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import services
from .serializers import ComplaintTrackingSerializer


class TrackComplaintView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "track"

    def get(self, request, tracking_id):
        complaint = services.get_trackable_complaint(user=request.user, tracking_id=tracking_id)
        if complaint is None:
            raise NotFound("Complaint not found.")  # same response for unknown and forbidden
        return Response(ComplaintTrackingSerializer(complaint).data)
