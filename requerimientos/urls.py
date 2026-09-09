from django.urls import path

from . import views

app_name = "requerimientos"

urlpatterns = [
    path("nuevo/", views.RequerimientoCreateView.as_view(), name="crear"),
    # HU-18: guardado temporal del borrador, antes de la ruta con consecutivo.
    path(
        "borrador/guardar/",
        views.GuardarBorradorView.as_view(),
        name="guardar_borrador",
    ),
    path(
        "borrador/descartar/",
        views.DescartarBorradorView.as_view(),
        name="descartar_borrador",
    ),
    path(
        "<str:consecutivo>/confirmacion/",
        views.RequerimientoConfirmacionView.as_view(),
        name="confirmacion",
    ),
    path(
        "prototipo/",
        views.prototipo_interactivo_view,
        name="prototipo_interactivo",
    ),
]
