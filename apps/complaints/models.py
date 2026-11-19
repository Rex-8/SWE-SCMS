from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Role


class ComplaintStatus(models.TextChoices):
    SUBMITTED = "SUBMITTED", "Submitted"
    ASSIGNED = "ASSIGNED", "Assigned"
    IN_PROGRESS = "IN_PROGRESS", "In Progress"
    RESOLVED = "RESOLVED", "Resolved"
    CLOSED = "CLOSED", "Closed"


tracking_id_validator = RegexValidator(
    r"^SCMS-\d{8}-[A-Z0-9]{6}$",
    "Tracking ID must look like SCMS-YYYYMMDD-XXXXXX.",
)


class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    # Membership is needed so PR 5 can check "staff belongs to the complaint's department".
    staff = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="departments",
        limit_choices_to={"role": Role.STAFF.value},
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="categories")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Complaint(models.Model):
    tracking_id = models.CharField(max_length=20, unique=True, validators=[tracking_id_validator])
    citizen = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="complaints",
        limit_choices_to={"role": Role.CITIZEN.value},
    )
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="complaints")
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="complaints")
    assigned_staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_complaints",
        limit_choices_to={"role": Role.STAFF.value},
    )
    description = models.TextField()
    location = models.CharField(max_length=255)
    status = models.CharField(
        max_length=12, choices=ComplaintStatus.choices, default=ComplaintStatus.SUBMITTED
    )
    resolution_details = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"], name="complaint_status_idx"),
            models.Index(fields=["department", "status"], name="complaint_dept_status_idx"),
            models.Index(fields=["-created_at"], name="complaint_created_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=ComplaintStatus.values),
                name="complaint_status_valid",
            ),
            models.CheckConstraint(
                condition=(Q(status=ComplaintStatus.CLOSED) & Q(closed_at__isnull=False))
                | (~Q(status=ComplaintStatus.CLOSED) & Q(closed_at__isnull=True)),
                name="complaint_closed_at_matches_status",
            ),
            models.CheckConstraint(
                condition=~Q(status=ComplaintStatus.CLOSED) | ~Q(resolution_details=""),
                name="complaint_closed_requires_resolution",
            ),
        ]

    def __str__(self):
        return self.tracking_id

    def clean(self):
        errors = {}
        if self.citizen_id and self.citizen.role != Role.CITIZEN:
            errors["citizen"] = "Complaints can only be submitted by citizens."
        if self.category_id and self.department_id and self.department_id != self.category.department_id:
            errors["department"] = "Department must be the one mapped to the category."
        if self.assigned_staff_id:
            if self.assigned_staff.role != Role.STAFF:
                errors["assigned_staff"] = "Assigned user must have the Staff role."
            elif self.department_id and not self.department.staff.filter(pk=self.assigned_staff_id).exists():
                errors["assigned_staff"] = "Assigned staff must belong to the complaint's department."
        if self.status == ComplaintStatus.CLOSED and not self.resolution_details.strip():
            errors["resolution_details"] = "Resolution details are required to close a complaint."
        if errors:
            raise ValidationError(errors)


def evidence_upload_path(instance, filename):
    extension = Path(filename).suffix.lower()
    return f"evidence/{instance.complaint_id}/{uuid4().hex}{extension}"


class ComplaintEvidence(models.Model):
    complaint = models.ForeignKey(
        Complaint,
        on_delete=models.CASCADE,
        related_name="evidence",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
    )
    file = models.FileField(upload_to=evidence_upload_path)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size = models.PositiveBigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.original_name



class ComplaintStatusHistory(models.Model):
    complaint = models.ForeignKey(
        Complaint,
        on_delete=models.CASCADE,
        related_name="status_history",
    )
    from_status = models.CharField(
        max_length=12,
        choices=ComplaintStatus.choices,
        null=True,
        blank=True,
    )
    to_status = models.CharField(max_length=12, choices=ComplaintStatus.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="complaint_status_changes",
    )
    remark = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["complaint", "created_at"], name="complaint_history_idx"),
        ]

    def __str__(self):
        return f"{self.complaint.tracking_id}: {self.from_status or 'NEW'} -> {self.to_status}"
