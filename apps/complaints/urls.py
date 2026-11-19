from django.urls import path

from . import views

app_name = "complaints"

urlpatterns = [
    path("complaints", views.ComplaintCreateView.as_view(), name="create"),
    path("complaints/categories", views.CategoryListView.as_view(), name="categories"),
    path("complaints/assigned", views.AssignedComplaintListView.as_view(), name="assigned"),
    path("complaints/<int:pk>/status", views.ComplaintStatusView.as_view(), name="status"),
    path("complaints/<int:pk>/close", views.ComplaintCloseView.as_view(), name="close"),
]
