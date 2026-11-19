from django.urls import path

from . import views

app_name = "tracking"

urlpatterns = [
    path("complaints/track/<str:tracking_id>", views.TrackComplaintView.as_view(), name="track"),
]
