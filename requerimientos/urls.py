from django.urls import path

from . import views

app_name = "requerimientos"

urlpatterns = [
    path("nuevo/", views.RequerimientoCreateView.as_view(), name="crear"),
    path(
        "<str:consecutivo>/confirmacion/",
        views.RequerimientoConfirmacionView.as_view(),
        name="confirmacion",
    ),
]
