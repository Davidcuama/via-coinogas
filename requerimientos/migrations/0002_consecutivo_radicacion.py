# HU-16: consecutivo único de radicación.
#
# La migración se hace en tres pasos para no fallar si ya existen requerimientos:
#   1. Se agrega el campo permitiendo nulos.
#   2. Se asigna consecutivo a los requerimientos existentes, en orden de creación.
#   3. Se vuelve el campo obligatorio y único.

from django.db import migrations, models


def asignar_consecutivos_existentes(apps, schema_editor):
    Requerimiento = apps.get_model("requerimientos", "Requerimiento")
    SecuenciaRadicacion = apps.get_model("requerimientos", "SecuenciaRadicacion")

    for req in Requerimiento.objects.order_by("fecha_solicitud", "pk"):
        anio = req.fecha_solicitud.year
        secuencia, _ = SecuenciaRadicacion.objects.get_or_create(anio=anio)
        secuencia.ultimo_numero += 1
        secuencia.save(update_fields=["ultimo_numero"])
        req.consecutivo = f"REQ-{anio}-{secuencia.ultimo_numero:04d}"
        req.save(update_fields=["consecutivo"])


class Migration(migrations.Migration):
    dependencies = [
        ("requerimientos", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="SecuenciaRadicacion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("anio", models.PositiveIntegerField(unique=True, verbose_name="Año")),
                (
                    "ultimo_numero",
                    models.PositiveIntegerField(default=0, verbose_name="Último número asignado"),
                ),
            ],
            options={
                "verbose_name": "Secuencia de radicación",
                "verbose_name_plural": "Secuencias de radicación",
                "ordering": ["-anio"],
            },
        ),
        migrations.AddField(
            model_name="requerimiento",
            name="consecutivo",
            field=models.CharField(
                editable=False,
                max_length=13,
                null=True,
                verbose_name="Consecutivo de radicación",
            ),
        ),
        migrations.RunPython(asignar_consecutivos_existentes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="requerimiento",
            name="consecutivo",
            field=models.CharField(
                editable=False,
                max_length=13,
                unique=True,
                verbose_name="Consecutivo de radicación",
            ),
        ),
    ]
