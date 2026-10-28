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


def tasa_devolucion():
    """Indicador de tasa de requerimientos devueltos (HU-32).

    Mide qué porcentaje de los requerimientos radicados han sido devueltos al
    menos una vez por información incompleta o errores:
    ``(requerimientos_devueltos / total_requerimientos) * 100``.

    Devuelve la tasa general, el desglose por área (de mayor a menor tasa para
    focalizar acciones de capacitación) y la evolución cronológica por mes de
    radicación. Si no hay requerimientos radicados, no produce división por cero.
    """
    from django.db.models import Case, IntegerField, Sum, When

    from .analitica import DevolucionAnalitica

    todos = DevolucionAnalitica.objects.all()
    total_general = todos.count()
    if total_general == 0:
        return {
            "tasa": None,
            "total": 0,
            "devueltos": 0,
            "sin_devolucion": 0,
            "por_area": [],
            "por_mes": [],
        }

    agregados = todos.aggregate(
        devueltos=Sum(
            Case(When(fue_devuelto=True, then=1), default=0, output_field=IntegerField())
        ),
    )
    devueltos_general = agregados["devueltos"] or 0
    tasa_general = round((devueltos_general * 100.0) / total_general, 1)

    por_area = []
    filas_area = (
        todos.values("area")
        .annotate(
            total=Count("id"),
            devueltos=Sum(
                Case(When(fue_devuelto=True, then=1), default=0, output_field=IntegerField())
            ),
        )
        .order_by("area")
    )
    for fila in filas_area:
        tot = fila["total"]
        dev = fila["devueltos"] or 0
        tasa = round((dev * 100.0) / tot, 1) if tot else 0.0
        por_area.append(
            {
                "area": fila["area"],
                "total": tot,
                "devueltos": dev,
                "tasa": tasa,
            }
        )
    por_area.sort(key=lambda x: (-x["tasa"], x["area"]))

    por_mes = []
    filas_mes = (
        todos.values("anio_solicitud", "mes_solicitud")
        .annotate(
            total=Count("id"),
            devueltos=Sum(
                Case(When(fue_devuelto=True, then=1), default=0, output_field=IntegerField())
            ),
        )
        .order_by("anio_solicitud", "mes_solicitud")
    )
    for fila in filas_mes:
        tot = fila["total"]
        dev = fila["devueltos"] or 0
        tasa = round((dev * 100.0) / tot, 1) if tot else 0.0
        por_mes.append(
            {
                "mes": etiqueta_mes(fila["anio_solicitud"], fila["mes_solicitud"]),
                "total": tot,
                "devueltos": dev,
                "tasa": tasa,
            }
        )

    return {
        "tasa": tasa_general,
        "total": total_general,
        "devueltos": devueltos_general,
        "sin_devolucion": total_general - devueltos_general,
        "por_area": _con_ancho(por_area, "tasa"),
        "por_mes": _con_ancho(por_mes, "tasa"),
    }
