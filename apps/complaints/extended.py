from datetime import timedelta
from pathlib import Path

from django.db import transaction
from django.db.models import Avg, Count, Q
from django.http import FileResponse
from django.utils import timezone
from rest_framework.exceptions import NotFound
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role, User
from apps.accounts.permissions import IsAdminRole, IsCitizen
from apps.audit.models import AuditLog
from apps.audit.services import record as record_audit
from apps.notifications.models import Notification

from .models import Category, CitizenFeedback, Complaint, ComplaintAttachment, ComplaintStatus, Department
from .permissions import can_view_complaint
from .uploads import validate_evidence


def complaint_queryset(user):
    qs = Complaint.objects.select_related("citizen", "category", "department", "assigned_staff")
    if user.role == Role.CITIZEN:
        return qs.filter(citizen=user)
    if user.role == Role.STAFF:
        return qs.filter(department__staff=user).filter(Q(assigned_staff__isnull=True) | Q(assigned_staff=user))
    return qs


class ComplaintSearchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = complaint_queryset(request.user)
        for key, field in (("id", "tracking_id__icontains"), ("category", "category__name__icontains")):
            value = request.query_params.get(key)
            if value:
                qs = qs.filter(**{field: value})
        status_filter = request.query_params.get("status")
        if status_filter:
            from .workflow import parse_status
            parsed = parse_status(status_filter)
            if parsed is None:
                return Response({"status": ["Unknown complaint status."]}, status=400)
            qs = qs.filter(status=parsed)
        start, end = request.query_params.get("from"), request.query_params.get("to")
        if start:
            qs = qs.filter(created_at__date__gte=start)
        if end:
            qs = qs.filter(created_at__date__lte=end)
        try:
            page = max(1, int(request.query_params.get("page", 1)))
            size = min(100, max(1, int(request.query_params.get("pageSize", 25))))
        except ValueError:
            return Response({"detail": "Page and pageSize must be integers."}, status=400)
        total = qs.count()
        rows = qs.order_by("-created_at")[(page-1)*size:page*size]
        return Response({"count": total, "page": page, "items": [complaint_json(c) for c in rows]})


def complaint_json(c):
    return {"id": c.pk, "trackingId": c.tracking_id, "category": c.category.name, "department": c.department.name,
            "assignedStaff": c.assigned_staff.name if c.assigned_staff else None, "citizen": c.citizen.name,
            "location": c.location, "description": c.description, "status": c.get_status_display(),
            "createdAt": c.created_at, "updatedAt": c.updated_at}


class ComplaintDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        c = complaint_queryset(request.user).filter(pk=pk).first()
        if not c:
            raise NotFound("Complaint not found.")
        return Response({**complaint_json(c), "resolutionDetails": c.resolution_details,
                         "history": [{"from": h.from_status, "to": ComplaintStatus(h.to_status).label,
                                      "remark": h.remark, "actor": h.actor.name, "at": h.created_at}
                                     for h in c.history.select_related("actor")],
                         "attachments": [{"name": a.original_name, "url": request.build_absolute_uri(f"/api/v1/attachments/{a.pk}")} for a in c.evidence_files.all()],
                         "feedback": hasattr(c, "citizen_review")})


class ComplaintUploadView(APIView):
    permission_classes = [IsCitizen]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        c = Complaint.objects.filter(pk=pk, citizen=request.user).first()
        if not c:
            raise NotFound("Complaint not found.")
        files = request.FILES.getlist("files") or request.FILES.getlist("file")
        if not files or len(files) > 5 or any(not validate_evidence(f) for f in files):
            return Response({"detail": "Upload up to 5 valid JPG, PNG or PDF files, each no larger than 5 MB."}, status=400)
        saved = []
        for f in files:
            saved.append(ComplaintAttachment.objects.create(complaint=c, file=f, original_name=f.name.replace("\\", "/").rsplit("/", 1)[-1],
                         content_type=f.content_type or "application/octet-stream", size=f.size))
        return Response({"uploaded": len(saved)}, status=201)


class AttachmentDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        attachment = ComplaintAttachment.objects.select_related("complaint").filter(pk=pk).first()
        if not attachment or not can_view_complaint(request.user, attachment.complaint):
            raise NotFound("Attachment not found.")
        response = FileResponse(
            attachment.file.open("rb"), as_attachment=True, filename=attachment.original_name
        )
        response["X-Content-Type-Options"] = "nosniff"
        return response


class ReassignView(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request, pk):
        department = Department.objects.filter(pk=request.data.get("departmentId"), is_active=True).first()
        if not department:
            return Response({"departmentId": ["Select an active department."]}, status=400)
        staff = None
        staff_id = request.data.get("staffId")
        if staff_id:
            staff = User.objects.filter(pk=staff_id, role=Role.STAFF, is_active=True, departments=department).first()
            if not staff:
                return Response({"staffId": ["Select active staff belonging to the department."]}, status=400)
        with transaction.atomic():
            c = Complaint.objects.select_for_update().filter(pk=pk).first()
            if not c:
                raise NotFound("Complaint not found.")
            old_department, old_staff = c.department_id, c.assigned_staff_id
            c.department, c.assigned_staff = department, staff
            c.save(update_fields=["department", "assigned_staff", "updated_at"])
            record_audit(actor=request.user, action="complaint.reassigned", obj=c,
                         details={"from_department": old_department, "to_department": department.pk,
                                  "from_staff": old_staff, "to_staff": staff.pk if staff else None})
        return Response({"department": department.name, "assignedStaff": staff.name if staff else None})


class FeedbackView(APIView):
    permission_classes = [IsCitizen]

    def post(self, request, pk):
        c = Complaint.objects.filter(pk=pk, citizen=request.user).first()
        if not c:
            raise NotFound("Complaint not found.")
        if c.status != ComplaintStatus.CLOSED:
            return Response({"detail": "Feedback is available after closure."}, status=409)
        if hasattr(c, "citizen_review"):
            return Response({"detail": "Feedback has already been submitted."}, status=409)
        try:
            rating = int(request.data.get("rating"))
        except (TypeError, ValueError):
            rating = 0
        if rating not in range(1, 6):
            return Response({"rating": ["Choose a rating from 1 to 5."]}, status=400)
        feedback = CitizenFeedback.objects.create(complaint=c, citizen=request.user, rating=rating,
                                                   comment=str(request.data.get("comment", ""))[:2000])
        return Response({"id": feedback.pk}, status=201)


class ReportsView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        qs = Complaint.objects.all()
        start, end = request.query_params.get("from"), request.query_params.get("to")
        if start: qs = qs.filter(created_at__date__gte=start)
        if end: qs = qs.filter(created_at__date__lte=end)
        now = timezone.now()
        breached = sum(1 for c in qs.select_related("category") if c.status != ComplaintStatus.CLOSED and c.created_at + timedelta(hours=c.category.sla_hours) < now)
        return Response({"total": qs.count(), "slaBreaches": breached, "byStatus": list(qs.values("status").annotate(count=Count("id")).order_by("status")),
                         "byDepartment": list(qs.values("department__name").annotate(count=Count("id")).order_by("department__name")),
                         "byCategory": list(qs.values("category__name").annotate(count=Count("id")).order_by("category__name")),
                         "averageRating": CitizenFeedback.objects.filter(complaint__in=qs).aggregate(value=Avg("rating"))["value"],
                         "feedbackCount": CitizenFeedback.objects.filter(complaint__in=qs).count()})


class AdminDataView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        return Response({"departments": list(Department.objects.filter(is_active=True).values("id", "name")),
                         "staff": [{"id": u.pk, "name": u.name, "departmentIds": list(u.departments.values_list("id", flat=True))}
                                   for u in User.objects.filter(role=Role.STAFF, is_active=True)],
                         "categories": list(Category.objects.select_related("department").values("id", "name", "department__name", "sla_hours"))})


class AuditListView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        rows = AuditLog.objects.select_related("actor")[:200]
        return Response([{"actor": x.actor.name, "action": x.action, "object": f"{x.object_type}#{x.object_id}",
                          "details": x.details, "at": x.timestamp} for x in rows])


class NotificationsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = Notification.objects.filter(recipient=request.user).select_related("complaint")[:100]
        return Response([{"trackingId": n.complaint.tracking_id, "message": n.message,
                          "status": n.delivery_status, "at": n.created_at} for n in rows])
