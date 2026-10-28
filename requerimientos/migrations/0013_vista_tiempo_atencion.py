"""HU-31: vistas SQL de solo lectura para el indicador de tiempo de atención.

Crea dos vistas, con el mismo patrón de ``0009_vistas_analiticas``:

- ``analitica_tiempo_atencion``: un renglón por requerimiento con su fecha de
  radicación, su fecha de cierre (si ya se cerró) y los días que pasaron entre
  una y otra.
- ``analitica_tiempo_atencion_mensual``: el promedio, mínimo y máximo de días de
  atención por área y por mes de cierre.

La radicación es ``fecha_solicitud`` (el sistema no guarda la hora en que se
radicó). El cierre es el cambio de estado a ``cerrado`` en la bitácora
(``CambioEstado``, HU-23). La bitácora guarda fecha y hora en UTC, así que se
lleva a la zona horaria del proyecto antes de quedarse con la fecha: si no, un
cierre a las 8 p. m. en Colombia contaría como del día siguiente.

El SQL difiere entre motores: PostgreSQL convierte con ``AT TIME ZONE`` y resta
fechas directamente; SQLite no conoce zonas horarias, así que se le aplica el
desfase fijo de la zona del proyecto (Colombia no tiene horario de verano) y
se usa ``julianday`` para la resta.
"""

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import migrations

# --- PostgreSQL (producción) ---
PG_TIEMPO_ATENCION = """
CREATE VIEW analitica_tiempo_atencion AS
SELECT
    r.id,
    r.consecutivo,
    a.nombre AS area,
    p.nombre AS prioridad,
    r.estado,
    r.fecha_solicitud,
    EXTRACT(YEAR  FROM r.fecha_solicitud)::int AS anio_solicitud,
    EXTRACT(MONTH FROM r.fecha_solicitud)::int AS mes_solicitud,
    c.fecha_cierre,
    EXTRACT(YEAR  FROM c.fecha_cierre)::int    AS anio_cierre,
    EXTRACT(MONTH FROM c.fecha_cierre)::int    AS mes_cierre,
    (c.fecha_cierre - r.fecha_solicitud)       AS dias_atencion,
    (c.fecha_cierre IS NOT NULL)               AS cerrado
FROM requerimientos_requerimiento r
JOIN requerimientos_area      a ON a.id = r.area_id
JOIN requerimientos_prioridad p ON p.id = r.prioridad_id
LEFT JOIN (
    SELECT requerimiento_id,
           MAX((fecha AT TIME ZONE '{zona}')::date) AS fecha_cierre
    FROM requerimientos_cambioestado
    WHERE estado_nuevo = 'cerrado'
    GROUP BY requerimiento_id
) c ON c.requerimiento_id = r.id;
"""

PG_TIEMPO_ATENCION_MENSUAL = """
CREATE VIEW analitica_tiempo_atencion_mensual AS
SELECT
    ROW_NUMBER() OVER (ORDER BY anio_cierre, mes_cierre, area) AS id,
    area,
    anio_cierre                        AS anio,
    mes_cierre                         AS mes,
    COUNT(*)                           AS requerimientos_cerrados,
    ROUND(AVG(dias_atencion), 2)       AS promedio_dias,
    MIN(dias_atencion)                 AS minimo_dias,
    MAX(dias_atencion)                 AS maximo_dias
FROM analitica_tiempo_atencion
WHERE fecha_cierre IS NOT NULL
GROUP BY area, anio_cierre, mes_cierre;
"""

# --- SQLite (pruebas y desarrollo) ---
SQLITE_TIEMPO_ATENCION = """
CREATE VIEW analitica_tiempo_atencion AS
SELECT
    r.id,
    r.consecutivo,
    a.nombre AS area,
    p.nombre AS prioridad,
    r.estado,
    r.fecha_solicitud,
    CAST(strftime('%Y', r.fecha_solicitud) AS INTEGER) AS anio_solicitud,
    CAST(strftime('%m', r.fecha_solicitud) AS INTEGER) AS mes_solicitud,
    c.fecha_cierre,
    CAST(strftime('%Y', c.fecha_cierre) AS INTEGER)    AS anio_cierre,
    CAST(strftime('%m', c.fecha_cierre) AS INTEGER)    AS mes_cierre,
    CAST(julianday(c.fecha_cierre) - julianday(r.fecha_solicitud) AS INTEGER)
                                                       AS dias_atencion,
    (c.fecha_cierre IS NOT NULL)                       AS cerrado
FROM requerimientos_requerimiento r
JOIN requerimientos_area      a ON a.id = r.area_id
JOIN requerimientos_prioridad p ON p.id = r.prioridad_id
LEFT JOIN (
    SELECT requerimiento_id,
           MAX(date(fecha, '{desfase} minutes')) AS fecha_cierre
    FROM requerimientos_cambioestado
    WHERE estado_nuevo = 'cerrado'
    GROUP BY requerimiento_id
) c ON c.requerimiento_id = r.id;
"""

SQLITE_TIEMPO_ATENCION_MENSUAL = """
CREATE VIEW analitica_tiempo_atencion_mensual AS
SELECT
    ROW_NUMBER() OVER (ORDER BY anio_cierre, mes_cierre, area) AS id,
    area,
    anio_cierre                  AS anio,
    mes_cierre                   AS mes,
    COUNT(*)                     AS requerimientos_cerrados,
    ROUND(AVG(dias_atencion), 2) AS promedio_dias,
    MIN(dias_atencion)           AS minimo_dias,
    MAX(dias_atencion)           AS maximo_dias
FROM analitica_tiempo_atencion
WHERE fecha_cierre IS NOT NULL
GROUP BY area, anio_cierre, mes_cierre;
"""

DROP_TIEMPO_ATENCION = "DROP VIEW IF EXISTS analitica_tiempo_atencion;"
DROP_TIEMPO_ATENCION_MENSUAL = "DROP VIEW IF EXISTS analitica_tiempo_atencion_mensual;"

# La zona va pegada al SQL (no admite parámetros dentro de un CREATE VIEW), así
# que solo se acepta un nombre de zona IANA bien formado: nada de comillas.
_ZONA_VALIDA = re.compile(r"^[A-Za-z0-9_+\-/]+$")


def _zona_del_proyecto():
    zona = settings.TIME_ZONE or "UTC"
    if not _ZONA_VALIDA.match(zona):
        raise ValueError(f"TIME_ZONE con caracteres no permitidos: {zona!r}")
    return zona


def _desfase_en_minutos(zona):
    """Desfase actual de la zona frente a UTC, en minutos (``-300`` en Colombia)."""
    desfase = datetime.now(ZoneInfo(zona)).utcoffset()
    return int(desfase.total_seconds() // 60)


def crear_vistas(apps, schema_editor):
    zona = _zona_del_proyecto()
    if schema_editor.connection.vendor == "postgresql":
        detalle = PG_TIEMPO_ATENCION.format(zona=zona)
        mensual = PG_TIEMPO_ATENCION_MENSUAL
    else:
        desfase = _desfase_en_minutos(zona)
        detalle = SQLITE_TIEMPO_ATENCION.format(desfase=f"{desfase:+d}")
        mensual = SQLITE_TIEMPO_ATENCION_MENSUAL
    # La mensual se apoya en la de detalle: se borra primero y se crea después.
    schema_editor.execute(DROP_TIEMPO_ATENCION_MENSUAL)
    schema_editor.execute(DROP_TIEMPO_ATENCION)
    schema_editor.execute(detalle)
    schema_editor.execute(mensual)


def borrar_vistas(apps, schema_editor):
    schema_editor.execute(DROP_TIEMPO_ATENCION_MENSUAL)
    schema_editor.execute(DROP_TIEMPO_ATENCION)


class Migration(migrations.Migration):
    dependencies = [
        ("requerimientos", "0012_estado_adjuntos"),
    ]

    operations = [
        migrations.RunPython(crear_vistas, borrar_vistas),
    ]
