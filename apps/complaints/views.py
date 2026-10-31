from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.accounts.permissions import IsCitizen, IsStaffOrAdmin

from . import services
from .models import Category, Complaint
from .serializers import (
    AssignedComplaintSerializer,
    CloseSerializer,
    ComplaintSubmitSerializer,
    StatusUpdateSerializer,
)


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


class AssignedPagination(PageNumberPagination):
    page_size = 20
    max_page_size = 100
    page_size_query_param = "pageSize"


class AssignedComplaintListView(ListAPIView):
    """Complaints staff may act on: their departments' (staff) or all (admin). Not a search."""

    permission_classes = [IsStaffOrAdmin]
    pagination_class = AssignedPagination
    serializer_class = AssignedComplaintSerializer

    def get_queryset(self):
        queryset = Complaint.objects.select_related("category", "department")
        if self.request.user.role == Role.STAFF:
            queryset = queryset.filter(department__staff=self.request.user)
        return queryset.order_by("-created_at", "-id")


class ComplaintStatusView(APIView):
    permission_classes = [IsStaffOrAdmin]

    def patch(self, request, pk):
        serializer = StatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            complaint = services.change_status(
                complaint_id=pk,
                actor=request.user,
                new_status=serializer.validated_data["status"],
                remark=serializer.validated_data["remark"],
            )
        except services.ComplaintNotFound:
            raise NotFound("Complaint not found.") from None
        except services.InvalidTransition as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response({"status": complaint.get_status_display(), "updatedAt": complaint.updated_at})


class ComplaintCloseView(APIView):
    permission_classes = [IsStaffOrAdmin]

    def post(self, request, pk):
        serializer = CloseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            complaint = services.close_complaint(
                complaint_id=pk,
                actor=request.user,
                resolution_details=serializer.validated_data["resolutionDetails"],
            )
        except services.ComplaintNotFound:
            raise NotFound("Complaint not found.") from None
        except services.ResolutionRequired:
            return Response(
                {"resolutionDetails": ["Resolution details are required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except services.InvalidTransition as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response({"status": complaint.get_status_display(), "closedAt": complaint.closed_at})
