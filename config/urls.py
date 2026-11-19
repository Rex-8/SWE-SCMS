from django.contrib import admin
from django.urls import include, path
from apps.complaints import extended

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.complaints.urls")),
    path("api/v1/", include("apps.tracking.urls")),
    path("api/v1/complaints/search", extended.ComplaintSearchView.as_view()),
    path("api/v1/complaints/<int:pk>", extended.ComplaintDetailView.as_view()),
    path("api/v1/complaints/<int:pk>/attachments", extended.ComplaintUploadView.as_view()),
    path("api/v1/attachments/<int:pk>", extended.AttachmentDownloadView.as_view()),
    path("api/v1/complaints/<int:pk>/reassign", extended.ReassignView.as_view()),
    path("api/v1/complaints/<int:pk>/feedback", extended.FeedbackView.as_view()),
    path("api/v1/reports/complaints", extended.ReportsView.as_view()),
    path("api/v1/admin/data", extended.AdminDataView.as_view()),
    path("api/v1/audit-logs", extended.AuditListView.as_view()),
    path("api/v1/notifications", extended.NotificationsView.as_view()),
]

from apps.web import home
urlpatterns += [path("", home, name="home"), path("dashboard/", home, name="dashboard")]
