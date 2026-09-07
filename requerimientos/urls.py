from django.urls import path

from . import views

app_name = "requerimientos"

urlpatterns = [
    path("nuevo/", views.RequerimientoCreateView.as_view(), name="crear"),
]
