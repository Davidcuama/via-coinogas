"""HU-14: alternativas o productos sustitutos del requerimiento.

Agregar columnas a ``requerimientos_requerimiento`` obliga, en SQLite, a
reconstruir la tabla (crearla de nuevo, copiar y renombrar), y eso rompe las
vistas analíticas de HU-29 que la consultan. Por eso las vistas se retiran
antes del cambio y se vuelven a crear después, con el mismo SQL de la
migración 0009. En PostgreSQL no haría falta, pero así la migración se
comporta igual en los dos motores.
"""

from importlib import import_module

from django.db import migrations, models

vistas = import_module("requerimientos.migrations.0009_vistas_analiticas")


class Migration(migrations.Migration):
    dependencies = [
        ("requerimientos", "0010_proveedorsugerido"),
    ]

    operations = [
        migrations.RunPython(vistas.borrar_vistas, vistas.crear_vistas),
        migrations.AddField(
            model_name="requerimiento",
            name="hay_sustitutos",
            field=models.BooleanField(
                default=False, verbose_name="¿Existen productos o servicios sustitutos?"
            ),
        ),
        migrations.AddField(
            model_name="requerimiento",
            name="sustitutos",
            field=models.TextField(
                blank=True,
                help_text="Qué alternativa sirve y en qué condiciones (marca, referencia, etc.).",
                verbose_name="Productos o servicios sustitutos",
            ),
        ),
        migrations.RunPython(vistas.crear_vistas, vistas.borrar_vistas),
    ]
