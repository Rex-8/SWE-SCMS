import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("complaints", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AddField(model_name="category", name="sla_hours", field=models.PositiveIntegerField(default=72, help_text="Target resolution time in hours.")),
        migrations.CreateModel(name="ComplaintAttachment", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("file", models.FileField(upload_to="complaints/%Y/%m/")), ("original_name", models.CharField(max_length=255)),
            ("content_type", models.CharField(max_length=100)), ("size", models.PositiveIntegerField()),
            ("uploaded_at", models.DateTimeField(auto_now_add=True)),
            ("complaint", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="evidence_files", to="complaints.complaint")),
        ], options={"ordering": ["uploaded_at"]}),
        migrations.CreateModel(name="StatusHistory", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("from_status", models.CharField(blank=True, max_length=12)), ("to_status", models.CharField(max_length=12)),
            ("remark", models.TextField(blank=True)), ("created_at", models.DateTimeField(auto_now_add=True)),
            ("actor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="status_changes", to=settings.AUTH_USER_MODEL)),
            ("complaint", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="history", to="complaints.complaint")),
        ], options={"ordering": ["created_at", "id"]}),
        migrations.CreateModel(name="CitizenFeedback", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("rating", models.PositiveSmallIntegerField()), ("comment", models.TextField(blank=True, max_length=2000)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("citizen", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="citizen_review", to=settings.AUTH_USER_MODEL)),
            ("complaint", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="citizen_review", to="complaints.complaint")),
        ], options={"constraints": [models.CheckConstraint(condition=models.Q(("rating__gte", 1), ("rating__lte", 5)), name="feedback_rating_1_to_5")]}),
    ]
