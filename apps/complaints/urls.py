from django.urls import path

from . import views

app_name = "complaints"

urlpatterns = [
    path("complaints", views.ComplaintCreateView.as_view(), name="create"),
    path("complaints/categories", views.CategoryListView.as_view(), name="categories"),
]
