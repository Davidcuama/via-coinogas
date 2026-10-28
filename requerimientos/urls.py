from django.urls import path

from . import views

app_name = "requerimientos"

urlpatterns = [
    path("nuevo/", views.RequerimientoCreateView.as_view(), name="crear"),
    # Bandeja del área de compras y consulta propia del solicitante.
    path("bandeja/", views.BandejaView.as_view(), name="bandeja"),
    path("mios/", views.MisRequerimientosView.as_view(), name="mios"),
    # Épica 7 - Analítica: indicadores del área de compras (HU-31).
    path("indicadores/", views.IndicadoresView.as_view(), name="indicadores"),
    # HU-22: ficha completa del requerimiento para el area de compras.
    path("ficha/<str:consecutivo>/", views.FichaRequerimientoView.as_view(), name="ficha"),
    # HU-23: el área de compras cambia el estado desde la ficha.
    path(
        "ficha/<str:consecutivo>/estado/",
        views.CambiarEstadoView.as_view(),
        name="cambiar_estado",
    ),
    # HU-24: compras devuelve; el solicitante corrige y reenvía.
    path(
        "ficha/<str:consecutivo>/devolver/",
        views.DevolverRequerimientoView.as_view(),
        name="devolver",
    ),
    path(
        "<str:consecutivo>/corregir/",
        views.CorregirRequerimientoView.as_view(),
        name="corregir",
    ),
    # HU-11: los adjuntos se entregan por una vista que revisa permisos.
    path("adjunto/<int:pk>/", views.DescargarAdjuntoView.as_view(), name="adjunto"),
    # HU-18: guardado temporal del borrador, antes de la ruta con consecutivo.
    path("borrador/guardar/", views.GuardarBorradorView.as_view(), name="guardar_borrador"),
    path("borrador/descartar/", views.DescartarBorradorView.as_view(), name="descartar_borrador"),
    path(
        "<str:consecutivo>/confirmacion/",
        views.RequerimientoConfirmacionView.as_view(),
        name="confirmacion",
    ),
]
