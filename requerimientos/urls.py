from django.urls import path

from . import views

app_name = "requerimientos"

urlpatterns = [
    path("nuevo/", views.RequerimientoCreateView.as_view(), name="crear"),
    # Bandeja del área de compras y consulta propia del solicitante.
    path("bandeja/", views.BandejaView.as_view(), name="bandeja"),
    path("mios/", views.MisRequerimientosView.as_view(), name="mios"),
    # HU-18: guardado temporal del borrador, antes de la ruta con consecutivo.
    path("borrador/guardar/", views.GuardarBorradorView.as_view(), name="guardar_borrador"),
    path("borrador/descartar/", views.DescartarBorradorView.as_view(), name="descartar_borrador"),
    path(
        "<str:consecutivo>/confirmacion/",
        views.RequerimientoConfirmacionView.as_view(),
        name="confirmacion",
    ),
]
