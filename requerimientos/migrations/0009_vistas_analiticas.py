"""HU-29: vistas SQL analíticas de solo lectura.

Crea dos vistas desnormalizadas (``analitica_requerimientos`` y
``analitica_items``) que el tablero consume sin tocar las tablas transaccionales.

El SQL de las fechas difiere entre motores: PostgreSQL usa ``EXTRACT`` y SQLite
``strftime``. Se elige según el motor en uso para que la misma migración corra
tanto en producción (PostgreSQL) como en las pruebas (SQLite).
"""

from django.db import migrations

# --- PostgreSQL (producción) ---
PG_REQUERIMIENTOS = """
CREATE VIEW analitica_requerimientos AS
SELECT
    r.id,
    r.consecutivo,
    r.solicitante,
    a.nombre               AS area,
    cc.codigo              AS centro_costo_codigo,
    cc.nombre              AS centro_costo_nombre,
    p.nombre               AS prioridad,
    r.fecha_solicitud,
    r.fecha_requerida,
    EXTRACT(YEAR  FROM r.fecha_solicitud)::int  AS anio_solicitud,
    EXTRACT(MONTH FROM r.fecha_solicitud)::int  AS mes_solicitud,
    COALESCE(i.numero_items, 0)                 AS numero_items,
    COALESCE(i.total_estimado, 0)               AS total_estimado
FROM requerimientos_requerimiento r
JOIN requerimientos_area        a  ON a.id  = r.area_id
JOIN requerimientos_centrocosto cc ON cc.id = r.centro_costo_id
JOIN requerimientos_prioridad   p  ON p.id  = r.prioridad_id
LEFT JOIN (
    SELECT requerimiento_id,
           COUNT(*)     AS numero_items,
           SUM(total)   AS total_estimado
    FROM requerimientos_item
    GROUP BY requerimiento_id
) i ON i.requerimiento_id = r.id;
"""

PG_ITEMS = """
CREATE VIEW analitica_items AS
SELECT
    it.id,
    it.requerimiento_id,
    r.consecutivo,
    it.numero,
    it.descripcion,
    it.cantidad,
    um.nombre AS unidad_medida,
    it.precio_referencia,
    it.total,
    it.requiere_calibracion,
    it.es_reembolsable
FROM requerimientos_item it
JOIN requerimientos_requerimiento r  ON r.id  = it.requerimiento_id
JOIN requerimientos_unidadmedida  um ON um.id = it.unidad_medida_id;
"""

# --- SQLite (pruebas) ---
SQLITE_REQUERIMIENTOS = """
CREATE VIEW analitica_requerimientos AS
SELECT
    r.id,
    r.consecutivo,
    r.solicitante,
    a.nombre  AS area,
    cc.codigo AS centro_costo_codigo,
    cc.nombre AS centro_costo_nombre,
    p.nombre  AS prioridad,
    r.fecha_solicitud,
    r.fecha_requerida,
    CAST(strftime('%Y', r.fecha_solicitud) AS INTEGER) AS anio_solicitud,
    CAST(strftime('%m', r.fecha_solicitud) AS INTEGER) AS mes_solicitud,
    COALESCE(i.numero_items, 0)   AS numero_items,
    COALESCE(i.total_estimado, 0) AS total_estimado
FROM requerimientos_requerimiento r
JOIN requerimientos_area        a  ON a.id  = r.area_id
JOIN requerimientos_centrocosto cc ON cc.id = r.centro_costo_id
JOIN requerimientos_prioridad   p  ON p.id  = r.prioridad_id
LEFT JOIN (
    SELECT requerimiento_id,
           COUNT(*)   AS numero_items,
           SUM(total) AS total_estimado
    FROM requerimientos_item
    GROUP BY requerimiento_id
) i ON i.requerimiento_id = r.id;
"""

SQLITE_ITEMS = """
CREATE VIEW analitica_items AS
SELECT
    it.id,
    it.requerimiento_id,
    r.consecutivo,
    it.numero,
    it.descripcion,
    it.cantidad,
    um.nombre AS unidad_medida,
    it.precio_referencia,
    it.total,
    it.requiere_calibracion,
    it.es_reembolsable
FROM requerimientos_item it
JOIN requerimientos_requerimiento r  ON r.id  = it.requerimiento_id
JOIN requerimientos_unidadmedida  um ON um.id = it.unidad_medida_id;
"""

DROP_REQUERIMIENTOS = "DROP VIEW IF EXISTS analitica_requerimientos;"
DROP_ITEMS = "DROP VIEW IF EXISTS analitica_items;"


def crear_vistas(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    if vendor == "postgresql":
        req_sql, item_sql = PG_REQUERIMIENTOS, PG_ITEMS
    else:
        # SQLite en pruebas; otros motores comparten la sintaxis estándar.
        req_sql, item_sql = SQLITE_REQUERIMIENTOS, SQLITE_ITEMS
    schema_editor.execute(DROP_REQUERIMIENTOS)
    schema_editor.execute(DROP_ITEMS)
    schema_editor.execute(req_sql)
    schema_editor.execute(item_sql)


def borrar_vistas(apps, schema_editor):
    schema_editor.execute(DROP_ITEMS)
    schema_editor.execute(DROP_REQUERIMIENTOS)


class Migration(migrations.Migration):
    dependencies = [
        ("requerimientos", "0008_requerimiento_creado_por"),
    ]

    operations = [
        migrations.RunPython(crear_vistas, borrar_vistas),
    ]
