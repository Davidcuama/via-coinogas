"""Configuración de la aplicación requerimientos."""

from django.apps import AppConfig


class RequerimientosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "requerimientos"
    verbose_name = "VIA Compras — Requerimientos"

    def ready(self):
        # HU-36: conectar las señales al arrancar (alerta de inicio de sesión).
        from . import signals  # noqa: F401
