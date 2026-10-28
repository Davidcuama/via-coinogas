"""Cálculo de los indicadores del área de compras (Épica 7 - Analítica).

La pantalla «Indicadores» lee **solo** las vistas analíticas de solo lectura
(``analitica.py``), igual que Power BI: así lo que ve el jefe del área en la
aplicación y lo que ve en el tablero sale de la misma fuente y da lo mismo.

Los promedios generales y por área se calculan sobre la vista de detalle, nunca
promediando los promedios mensuales: un mes con un solo cierre pesaría lo mismo
que uno con cincuenta y el número saldría sesgado.

Los modelos de ``analitica`` se importan dentro de cada función, como en las
pruebas de HU-29: son ``managed = False`` y no tienen migración propia (las
vistas las crea el SQL), así que no deben quedar registrados al arrancar.
"""

from django.db.models import Avg, Count, Max, Min

MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def _redondear(valor, decimales=1):
    """Redondea un promedio para mostrarlo; ``None`` si no hay con qué calcularlo.

    PostgreSQL devuelve ``Decimal`` y SQLite ``float``: se normaliza a ``float``.
    """
    if valor is None:
        return None
    return round(float(valor), decimales)


def etiqueta_mes(anio, mes):
    """``(2026, 3)`` → ``"mar 2026"``."""
    return f"{MESES[mes - 1]} {anio}"


def _con_ancho(filas, campo):
    """Agrega a cada fila el ancho relativo de su barra (0-100) según ``campo``."""
    maximo = max((fila[campo] or 0 for fila in filas), default=0)
    for fila in filas:
        fila["ancho"] = round((fila[campo] or 0) * 100 / maximo) if maximo else 0
    return filas


def tiempo_atencion():
    """Indicador de tiempo de atención: radicación → cierre (HU-31).

    Devuelve el promedio general, el desglose por área (de la más lenta a la
    más rápida, que es lo que el jefe busca) y la evolución por mes de cierre.
    Lo que sigue abierto no entra en los promedios, pero se cuenta aparte para
    que se vea cuánto falta por atender.
    """
    from .analitica import TiempoAtencion

    cerrados = TiempoAtencion.objects.filter(dias_atencion__isnull=False)
    general = cerrados.aggregate(
        promedio=Avg("dias_atencion"),
        minimo=Min("dias_atencion"),
        maximo=Max("dias_atencion"),
        cerrados=Count("id"),
    )

    por_area = [
        {
            "area": fila["area"],
            "cerrados": fila["cerrados"],
            "promedio": _redondear(fila["promedio"]),
            "maximo": fila["maximo"],
        }
        for fila in cerrados.values("area")
        .annotate(
            cerrados=Count("id"),
            promedio=Avg("dias_atencion"),
            maximo=Max("dias_atencion"),
        )
        .order_by("-promedio", "area")
    ]

    por_mes = [
        {
            "mes": etiqueta_mes(fila["anio_cierre"], fila["mes_cierre"]),
            "cerrados": fila["cerrados"],
            "promedio": _redondear(fila["promedio"]),
        }
        for fila in cerrados.values("anio_cierre", "mes_cierre")
        .annotate(cerrados=Count("id"), promedio=Avg("dias_atencion"))
        .order_by("anio_cierre", "mes_cierre")
    ]

    return {
        "promedio": _redondear(general["promedio"]),
        "minimo": general["minimo"],
        "maximo": general["maximo"],
        "cerrados": general["cerrados"],
        "abiertos": TiempoAtencion.objects.filter(dias_atencion__isnull=True).count(),
        "por_area": _con_ancho(por_area, "promedio"),
        "por_mes": _con_ancho(por_mes, "promedio"),
    }
