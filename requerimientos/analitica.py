"""Capa analítica de solo lectura (HU-29).

El área de compras conecta Power BI (o un tablero propio, HU-30) contra estas
**vistas SQL desnormalizadas**, no contra las tablas transaccionales. Así el
reporte no depende del equipo de desarrollo cada vez que cambia, y la conexión
analítica no puede modificar los datos de operación.

Estos modelos son ``managed = False``: Django **no** crea ni altera sus tablas.
Las vistas las define la migración ``0009_vistas_analiticas`` con SQL; aquí solo
se mapean para poder consultarlas y documentar su diccionario de campos. Por eso
``save()``/``delete()`` quedan deshabilitados: una vista es de solo lectura.

Nombres de vista:
  - ``analitica_requerimientos``: un renglón por requerimiento, con área,
    centro de costo, prioridad, fechas, total estimado y conteo de ítems.
  - ``analitica_items``: un renglón por ítem, con su requerimiento y la unidad.
"""

from django.db import models


class _VistaSoloLectura(models.Model):
    """Base de las vistas: prohíbe escrituras desde el ORM."""

    class Meta:
        abstract = True
        managed = False

    def save(self, *args, **kwargs):
        raise NotImplementedError("Las vistas analíticas son de solo lectura (HU-29).")

    def delete(self, *args, **kwargs):
        raise NotImplementedError("Las vistas analíticas son de solo lectura (HU-29).")


class RequerimientoAnalitico(_VistaSoloLectura):
    """Vista desnormalizada de requerimientos para el tablero (HU-29)."""

    # La vista reusa el id del requerimiento como clave; Django exige una pk.
    id = models.IntegerField(primary_key=True)
    consecutivo = models.CharField(max_length=20)
    solicitante = models.CharField(max_length=150)
    area = models.CharField("Área o proyecto", max_length=100)
    centro_costo_codigo = models.CharField("Código del centro de costo", max_length=20)
    centro_costo_nombre = models.CharField("Centro de costo", max_length=100)
    prioridad = models.CharField(max_length=20)
    fecha_solicitud = models.DateField()
    fecha_requerida = models.DateField()
    anio_solicitud = models.IntegerField("Año de solicitud")
    mes_solicitud = models.IntegerField("Mes de solicitud")
    numero_items = models.IntegerField("Número de ítems")
    total_estimado = models.DecimalField(max_digits=18, decimal_places=2)

    class Meta(_VistaSoloLectura.Meta):
        db_table = "analitica_requerimientos"
        verbose_name = "Requerimiento (analítico)"
        verbose_name_plural = "Requerimientos (analíticos)"

    def __str__(self):
        return f"{self.consecutivo} · {self.area}"


class ItemAnalitico(_VistaSoloLectura):
    """Vista desnormalizada de ítems para el tablero (HU-29)."""

    id = models.IntegerField(primary_key=True)
    requerimiento_id = models.IntegerField("ID del requerimiento")
    consecutivo = models.CharField(max_length=20)
    numero = models.IntegerField("N.º de ítem")
    descripcion = models.TextField()
    cantidad = models.IntegerField()
    unidad_medida = models.CharField("Unidad de medida", max_length=50)
    precio_referencia = models.DecimalField(max_digits=14, decimal_places=2, null=True)
    total = models.DecimalField(max_digits=16, decimal_places=2)
    requiere_calibracion = models.BooleanField()
    es_reembolsable = models.BooleanField()

    class Meta(_VistaSoloLectura.Meta):
        db_table = "analitica_items"
        verbose_name = "Ítem (analítico)"
        verbose_name_plural = "Ítems (analíticos)"

    def __str__(self):
        return f"{self.consecutivo} · ítem {self.numero}"
