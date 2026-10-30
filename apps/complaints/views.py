from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import IsCitizen

from . import services
from .models import Category
from .serializers import ComplaintSubmitSerializer


class CategoryListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        categories = Category.objects.filter(is_active=True, department__is_active=True).order_by("name")
        return Response(
            [{"id": c.pk, "name": c.name, "description": c.description} for c in categories]
        )


class ComplaintCreateView(APIView):
    permission_classes = [IsCitizen]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "complaint_submit"

    def post(self, request):
        serializer = ComplaintSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            complaint = services.submit_complaint(
                citizen=request.user,
                category_id=data["categoryId"],
                description=data["description"],
                location=data["location"],
            )
        except services.CategoryUnavailable:
            return Response(
                {"categoryId": ["Select a valid, active category."]}, status=status.HTTP_400_BAD_REQUEST
            )
        except services.TrackingIDGenerationError:
            return Response(
                {"detail": "Could not create the complaint. Try again."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(
            {
                "trackingId": complaint.tracking_id,
                "status": complaint.get_status_display(),
                "department": complaint.department.name,
            },
            status=status.HTTP_201_CREATED,
        )
