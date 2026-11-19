import django.db.models.deletion
import django.utils.timezone

from django.conf import settings
from django.db import migrations, models


def backfill_status_history(apps, schema_editor):
    Complaint = apps.get_model("complaints", "Complaint")
    ComplaintStatusHistory = apps.get_model("complaints", "ComplaintStatusHistory")
    db_alias = schema_editor.connection.alias

    entries = (
        ComplaintStatusHistory(
            complaint_id=complaint.pk,
            from_status=None,
            to_status=complaint.status,
            actor_id=complaint.citizen_id,
            remark="",
            created_at=complaint.created_at,
        )
        for complaint in Complaint.objects.using(db_alias).only(
            "pk", "status", "citizen_id", "created_at"
        ).iterator()
    )
    ComplaintStatusHistory.objects.using(db_alias).bulk_create(entries, batch_size=500)


class Migration(migrations.Migration):

    dependencies = [
        ("complaints", "0002_complaintevidence"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ComplaintStatusHistory",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "from_status",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("SUBMITTED", "Submitted"),
                            ("ASSIGNED", "Assigned"),
                            ("IN_PROGRESS", "In Progress"),
                            ("RESOLVED", "Resolved"),
                            ("CLOSED", "Closed"),
                        ],
                        max_length=12,
                        null=True,
                    ),
                ),
                (
                    "to_status",
                    models.CharField(
                        choices=[
                            ("SUBMITTED", "Submitted"),
                            ("ASSIGNED", "Assigned"),
                            ("IN_PROGRESS", "In Progress"),
                            ("RESOLVED", "Resolved"),
                            ("CLOSED", "Closed"),
                        ],
                        max_length=12,
                    ),
                ),
                ("remark", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                (
                    "actor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="complaint_status_changes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "complaint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="status_history",
                        to="complaints.complaint",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at", "id"],
                "indexes": [
                    models.Index(
                        fields=["complaint", "created_at"],
                        name="complaint_history_idx",
                    ),
                ],
            },
        ),
        migrations.RunPython(backfill_status_history, migrations.RunPython.noop),
    ]
