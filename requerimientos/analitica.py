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
  - ``analitica_tiempo_atencion`` (HU-31, migración ``0013``): un renglón por
    requerimiento con los días entre su radicación y su cierre.
  - ``analitica_tiempo_atencion_mensual`` (HU-31): promedio, mínimo y máximo
    de días de atención por área y mes de cierre.
  - ``analitica_devoluciones`` (HU-32, migración ``0014``): un renglón por
    requerimiento indicando si tuvo devoluciones y cuántas.
  - ``analitica_tasa_devolucion_mensual`` (HU-32): tasa porcentual de
    devolución por área y mes de radicación.
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


class TiempoAtencion(_VistaSoloLectura):
    """Tiempo de atención de cada requerimiento (HU-31).

    Responde «¿cuánto se demoró compras en atender esto?». La radicación es la
    fecha de solicitud y el cierre, el paso a «Cerrado» en la bitácora de
    estados (HU-23), llevado a la zona horaria del proyecto.

    Lo que todavía no se ha cerrado aparece igual, con ``fecha_cierre`` y
    ``dias_atencion`` vacíos y ``cerrado`` en falso: así el tablero puede
    contar lo pendiente, y el promedio —que ignora los vacíos— no se distorsiona.

    Diccionario de campos:

    ==================  =========================================================
    ``id``              ID del requerimiento.
    ``consecutivo``     Consecutivo de radicación (``REQ-2026-0001``).
    ``area``            Nombre del área o proyecto.
    ``prioridad``       ``ALTA``, ``MEDIA`` o ``BAJA``.
    ``estado``          Estado actual (``radicado``, ``revision``, ...).
    ``fecha_solicitud`` Fecha de radicación.
    ``anio_solicitud``  Año de radicación.
    ``mes_solicitud``   Mes de radicación (1-12).
    ``fecha_cierre``    Fecha en que pasó a «Cerrado». Vacía si sigue abierto.
    ``anio_cierre``     Año de cierre. Vacío si sigue abierto.
    ``mes_cierre``      Mes de cierre (1-12). Vacío si sigue abierto.
    ``dias_atencion``   Días calendario entre radicación y cierre. Vacío si sigue
                        abierto; 0 si se cerró el mismo día.
    ``cerrado``         Verdadero si ya se cerró.
    ==================  =========================================================
    """

    id = models.IntegerField(primary_key=True)
    consecutivo = models.CharField(max_length=20)
    area = models.CharField("Área o proyecto", max_length=100)
    prioridad = models.CharField(max_length=20)
    estado = models.CharField(max_length=20)
    fecha_solicitud = models.DateField("Fecha de radicación")
    anio_solicitud = models.IntegerField("Año de radicación")
    mes_solicitud = models.IntegerField("Mes de radicación")
    fecha_cierre = models.DateField("Fecha de cierre", null=True)
    anio_cierre = models.IntegerField("Año de cierre", null=True)
    mes_cierre = models.IntegerField("Mes de cierre", null=True)
    dias_atencion = models.IntegerField("Días de atención", null=True)
    cerrado = models.BooleanField()

    class Meta(_VistaSoloLectura.Meta):
        db_table = "analitica_tiempo_atencion"
        verbose_name = "Tiempo de atención (analítico)"
        verbose_name_plural = "Tiempos de atención (analíticos)"

    def __str__(self):
        return f"{self.consecutivo} · {self.dias_atencion} días"


class TiempoAtencionMensual(_VistaSoloLectura):
    """Tiempo de atención agregado por área y mes de cierre (HU-31).

    Solo cuenta lo cerrado: un requerimiento abierto todavía no tiene tiempo de
    atención. Se agrupa por el mes en que se **cerró**, que es cuando la
    atención terminó y se puede medir. Para un total del año o de todas las
    áreas no se promedian estos promedios —daría un número sesgado—: se
    calcula sobre ``analitica_tiempo_atencion``.

    Diccionario de campos:

    ===========================  ================================================
    ``id``                       Número de renglón (sin significado de negocio).
    ``area``                     Nombre del área o proyecto.
    ``anio``                     Año de cierre.
    ``mes``                      Mes de cierre (1-12).
    ``requerimientos_cerrados``  Cuántos se cerraron en ese mes y área.
    ``promedio_dias``            Promedio de días de atención (2 decimales).
    ``minimo_dias``              El que menos se demoró.
    ``maximo_dias``              El que más se demoró.
    ===========================  ================================================
    """

    id = models.IntegerField(primary_key=True)
    area = models.CharField("Área o proyecto", max_length=100)
    anio = models.IntegerField("Año de cierre")
    mes = models.IntegerField("Mes de cierre")
    requerimientos_cerrados = models.IntegerField("Requerimientos cerrados")
    promedio_dias = models.DecimalField("Promedio de días", max_digits=10, decimal_places=2)
    minimo_dias = models.IntegerField("Mínimo de días")
    maximo_dias = models.IntegerField("Máximo de días")

    class Meta(_VistaSoloLectura.Meta):
        db_table = "analitica_tiempo_atencion_mensual"
        verbose_name = "Tiempo de atención mensual (analítico)"
        verbose_name_plural = "Tiempos de atención mensuales (analíticos)"

    def __str__(self):
        return f"{self.area} · {self.anio}-{self.mes:02d}"


class DevolucionAnalitica(_VistaSoloLectura):
    """Información de devoluciones por requerimiento (HU-32).

    Permite responder «¿cuántas solicitudes fueron devueltas por información
    incompleta o errónea?». Analiza la bitácora de estados (``CambioEstado``)
    buscando transiciones hacia ``devuelto``.

    Diccionario de campos:

    ==========================  ================================================
    ``id``                      ID del requerimiento.
    ``consecutivo``             Consecutivo de radicación (``REQ-2026-0001``).
    ``area``                    Nombre del área o proyecto.
    ``prioridad``               ``ALTA``, ``MEDIA`` o ``BAJA``.
    ``estado``                  Estado actual del requerimiento.
    ``fecha_solicitud``         Fecha de radicación.
    ``anio_solicitud``          Año de radicación.
    ``mes_solicitud``           Mes de radicación (1-12).
    ``conteo_devoluciones``     Número de veces que el requerimiento fue devuelto.
    ``fue_devuelto``            Verdadero si fue devuelto al menos una vez.
    ==========================  ================================================
    """

    id = models.IntegerField(primary_key=True)
    consecutivo = models.CharField(max_length=20)
    area = models.CharField("Área o proyecto", max_length=100)
    prioridad = models.CharField(max_length=20)
    estado = models.CharField(max_length=20)
    fecha_solicitud = models.DateField("Fecha de radicación")
    anio_solicitud = models.IntegerField("Año de radicación")
    mes_solicitud = models.IntegerField("Mes de radicación")
    conteo_devoluciones = models.IntegerField("Conteo de devoluciones")
    fue_devuelto = models.BooleanField("¿Fue devuelto?")

    class Meta(_VistaSoloLectura.Meta):
        db_table = "analitica_devoluciones"
        verbose_name = "Devolución (analítica)"
        verbose_name_plural = "Devoluciones (analíticas)"

    def __str__(self):
        return f"{self.consecutivo} · {'Devuelto' if self.fue_devuelto else 'Sin devoluciones'}"


class TasaDevolucionMensual(_VistaSoloLectura):
    """Tasa de devolución agregada por área y mes de solicitud (HU-32).

    Calcula el porcentaje de requerimientos devueltos respecto al total
    radicado en cada periodo y área:
    ``(requerimientos_devueltos / total_requerimientos) * 100``.

    Diccionario de campos:

    ===========================  ================================================
    ``id``                       Número de renglón (sin significado de negocio).
    ``area``                     Nombre del área o proyecto.
    ``anio``                     Año de radicación.
    ``mes``                      Mes de radicación (1-12).
    ``total_requerimientos``     Total de requerimientos radicados en el periodo.
    ``requerimientos_devueltos`` Cuántos de ellos fueron devueltos al menos una vez.
    ``tasa_devolucion``          Porcentaje de devolución (0.00% a 100.00%).
    ===========================  ================================================
    """

    id = models.IntegerField(primary_key=True)
    area = models.CharField("Área o proyecto", max_length=100)
    anio = models.IntegerField("Año de radicación")
    mes = models.IntegerField("Mes de radicación")
    total_requerimientos = models.IntegerField("Total de requerimientos")
    requerimientos_devueltos = models.IntegerField("Requerimientos devueltos")
    tasa_devolucion = models.DecimalField("Tasa de devolución (%)", max_digits=5, decimal_places=2)

    class Meta(_VistaSoloLectura.Meta):
        db_table = "analitica_tasa_devolucion_mensual"
        verbose_name = "Tasa de devolución mensual (analítica)"
        verbose_name_plural = "Tasas de devolución mensuales (analíticas)"

    def __str__(self):
        return f"{self.area} · {self.anio}-{self.mes:02d}: {self.tasa_devolucion}%"
