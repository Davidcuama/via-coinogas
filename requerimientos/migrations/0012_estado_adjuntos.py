"""HU-11 y HU-23: adjuntos del requerimiento, su estado y la bitácora de cambios.

Se sube a `main` antes que las historias que la usan, para que las migraciones
de los demás se encadenen después de esta y no choquen.

Agregar la columna `estado` a ``requerimientos_requerimiento`` obliga, en SQLite,
a reconstruir la tabla, y eso rompe las vistas analíticas de HU-29 que la
consultan. Por eso las vistas se retiran antes de ese cambio y se recrean justo
después, con el mismo SQL de la migración 0009, igual que en la 0011. Las tablas
nuevas (Adjunto, CambioEstado) no tocan la de requerimientos, así que van fuera
de ese paréntesis.
"""

from importlib import import_module

import django.db.models.deletion
import requerimientos.models
from django.conf import settings
from django.db import migrations, models

vistas = import_module("requerimientos.migrations.0009_vistas_analiticas")


class Migration(migrations.Migration):
    dependencies = [
        ("requerimientos", "0011_requerimiento_sustitutos"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(vistas.borrar_vistas, vistas.crear_vistas),
        migrations.AddField(
            model_name="requerimiento",
            name="estado",
            field=models.CharField(
                choices=[
                    ("radicado", "Radicado"),
                    ("revision", "En revisión"),
                    ("devuelto", "Devuelto"),
                    ("cotizacion", "En cotización"),
                    ("cerrado", "Cerrado"),
                ],
                db_index=True,
                default="radicado",
                editable=False,
                max_length=20,
                verbose_name="Estado",
            ),
        ),
        migrations.RunPython(vistas.crear_vistas, vistas.borrar_vistas),
        migrations.CreateModel(
            name="Adjunto",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "archivo",
                    models.FileField(
                        max_length=255,
                        upload_to=requerimientos.models.ruta_adjunto,
                        verbose_name="Archivo",
                    ),
                ),
                (
                    "nombre_original",
                    models.CharField(max_length=255, verbose_name="Nombre del archivo"),
                ),
                (
                    "tipo",
                    models.CharField(
                        choices=[("foto", "Fotografía"), ("documento", "Documento")],
                        max_length=12,
                        verbose_name="Tipo",
                    ),
                ),
                ("tamano", models.PositiveIntegerField(verbose_name="Tamaño (bytes)")),
                ("subido_en", models.DateTimeField(auto_now_add=True, verbose_name="Subido el")),
                (
                    "requerimiento",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="adjuntos",
                        to="requerimientos.requerimiento",
                        verbose_name="Requerimiento",
                    ),
                ),
                (
                    "subido_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="adjuntos_subidos",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Subido por",
                    ),
                ),
            ],
            options={
                "verbose_name": "Adjunto",
                "verbose_name_plural": "Adjuntos",
                "ordering": ["subido_en", "pk"],
            },
        ),
        migrations.CreateModel(
            name="CambioEstado",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "estado_anterior",
                    models.CharField(
                        choices=[
                            ("radicado", "Radicado"),
                            ("revision", "En revisión"),
                            ("devuelto", "Devuelto"),
                            ("cotizacion", "En cotización"),
                            ("cerrado", "Cerrado"),
                        ],
                        max_length=20,
                        verbose_name="Estado anterior",
                    ),
                ),
                (
                    "estado_nuevo",
                    models.CharField(
                        choices=[
                            ("radicado", "Radicado"),
                            ("revision", "En revisión"),
                            ("devuelto", "Devuelto"),
                            ("cotizacion", "En cotización"),
                            ("cerrado", "Cerrado"),
                        ],
                        max_length=20,
                        verbose_name="Estado nuevo",
                    ),
                ),
                ("observacion", models.TextField(blank=True, verbose_name="Observación")),
                ("fecha", models.DateTimeField(auto_now_add=True, verbose_name="Fecha")),
                (
                    "requerimiento",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cambios_estado",
                        to="requerimientos.requerimiento",
                        verbose_name="Requerimiento",
                    ),
                ),
                (
                    "usuario",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="cambios_estado",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Realizado por",
                    ),
                ),
            ],
            options={
                "verbose_name": "Cambio de estado",
                "verbose_name_plural": "Cambios de estado",
                "ordering": ["fecha", "pk"],
                "indexes": [
                    models.Index(
                        fields=["requerimiento", "fecha"], name="requerimien_requeri_3ceb06_idx"
                    )
                ],
            },
        ),
    ]
