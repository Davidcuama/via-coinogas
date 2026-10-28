"""HU-32: vistas SQL de solo lectura para el indicador de tasa de devolución.

Crea dos vistas con el mismo patrón de ``0009_vistas_analiticas`` y ``0013_vista_tiempo_atencion``:

- ``analitica_devoluciones``: un renglón por requerimiento que indica si alguna
  vez pasó a estado ``devuelto`` (conteo y marca booleana).
- ``analitica_tasa_devolucion_mensual``: cálculo agrupado por área y por mes de
  radicación de la tasa porcentual = (devueltos / total) * 100.

El SQL difiere entre motores: PostgreSQL usa casting con ``::numeric`` y booleanos
nativos; SQLite usa enteros ``1/0`` y ``strftime``.
"""

from django.db import migrations

# --- PostgreSQL (producción) ---
PG_DEVOLUCIONES = """
CREATE VIEW analitica_devoluciones AS
SELECT
    r.id,
    r.consecutivo,
    a.nombre AS area,
    p.nombre AS prioridad,
    r.estado,
    r.fecha_solicitud,
    EXTRACT(YEAR  FROM r.fecha_solicitud)::int AS anio_solicitud,
    EXTRACT(MONTH FROM r.fecha_solicitud)::int AS mes_solicitud,
    COALESCE(d.conteo_devoluciones, 0)         AS conteo_devoluciones,
    (COALESCE(d.conteo_devoluciones, 0) > 0)   AS fue_devuelto
FROM requerimientos_requerimiento r
JOIN requerimientos_area      a ON a.id = r.area_id
JOIN requerimientos_prioridad p ON p.id = r.prioridad_id
LEFT JOIN (
    SELECT requerimiento_id,
           COUNT(*) AS conteo_devoluciones
    FROM requerimientos_cambioestado
    WHERE estado_nuevo = 'devuelto'
    GROUP BY requerimiento_id
) d ON d.requerimiento_id = r.id;
"""

PG_TASA_DEVOLUCION_MENSUAL = """
CREATE VIEW analitica_tasa_devolucion_mensual AS
SELECT
    ROW_NUMBER() OVER (ORDER BY anio_solicitud, mes_solicitud, area) AS id,
    area,
    anio_solicitud                                                   AS anio,
    mes_solicitud                                                    AS mes,
    COUNT(*)                                                         AS total_requerimientos,
    COUNT(CASE WHEN fue_devuelto THEN 1 END)                         AS requerimientos_devueltos,
    ROUND(
        (COUNT(CASE WHEN fue_devuelto THEN 1 END)::numeric * 100.0)
        / NULLIF(COUNT(*), 0),
        2
    )                                                                AS tasa_devolucion
FROM analitica_devoluciones
GROUP BY area, anio_solicitud, mes_solicitud;
"""

# --- SQLite (pruebas y desarrollo) ---
SQLITE_DEVOLUCIONES = """
CREATE VIEW analitica_devoluciones AS
SELECT
    r.id,
    r.consecutivo,
    a.nombre AS area,
    p.nombre AS prioridad,
    r.estado,
    r.fecha_solicitud,
    CAST(strftime('%Y', r.fecha_solicitud) AS INTEGER) AS anio_solicitud,
    CAST(strftime('%m', r.fecha_solicitud) AS INTEGER) AS mes_solicitud,
    COALESCE(d.conteo_devoluciones, 0)                 AS conteo_devoluciones,
    CASE WHEN COALESCE(d.conteo_devoluciones, 0) > 0 THEN 1 ELSE 0 END
                                                       AS fue_devuelto
FROM requerimientos_requerimiento r
JOIN requerimientos_area      a ON a.id = r.area_id
JOIN requerimientos_prioridad p ON p.id = r.prioridad_id
LEFT JOIN (
    SELECT requerimiento_id,
           COUNT(*) AS conteo_devoluciones
    FROM requerimientos_cambioestado
    WHERE estado_nuevo = 'devuelto'
    GROUP BY requerimiento_id
) d ON d.requerimiento_id = r.id;
"""

SQLITE_TASA_DEVOLUCION_MENSUAL = """
CREATE VIEW analitica_tasa_devolucion_mensual AS
SELECT
    ROW_NUMBER() OVER (ORDER BY anio_solicitud, mes_solicitud, area) AS id,
    area,
    anio_solicitud AS anio,
    mes_solicitud  AS mes,
    COUNT(*)       AS total_requerimientos,
    SUM(CASE WHEN fue_devuelto = 1 THEN 1 ELSE 0 END) AS requerimientos_devueltos,
    ROUND(
        (SUM(CASE WHEN fue_devuelto = 1 THEN 1.0 ELSE 0.0 END) * 100.0)
        / COUNT(*),
        2
    ) AS tasa_devolucion
FROM analitica_devoluciones
GROUP BY area, anio_solicitud, mes_solicitud;
"""

DROP_DEVOLUCIONES = "DROP VIEW IF EXISTS analitica_devoluciones;"
DROP_TASA_DEVOLUCION_MENSUAL = "DROP VIEW IF EXISTS analitica_tasa_devolucion_mensual;"


def crear_vistas(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        detalle = PG_DEVOLUCIONES
        mensual = PG_TASA_DEVOLUCION_MENSUAL
    else:
        detalle = SQLITE_DEVOLUCIONES
        mensual = SQLITE_TASA_DEVOLUCION_MENSUAL
    schema_editor.execute(DROP_TASA_DEVOLUCION_MENSUAL)
    schema_editor.execute(DROP_DEVOLUCIONES)
    schema_editor.execute(detalle)
    schema_editor.execute(mensual)


def borrar_vistas(apps, schema_editor):
    schema_editor.execute(DROP_TASA_DEVOLUCION_MENSUAL)
    schema_editor.execute(DROP_DEVOLUCIONES)


class Migration(migrations.Migration):
    dependencies = [
        ("requerimientos", "0013_vista_tiempo_atencion"),
    ]

    operations = [
        migrations.RunPython(crear_vistas, borrar_vistas),
    ]
