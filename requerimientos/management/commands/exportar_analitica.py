"""Exporta las vistas analíticas a CSV, para construir el tablero (HU-30).

Power BI Desktop no tiene conector nativo para SQLite, que es el motor que usa
el equipo en desarrollo para no tener que instalar PostgreSQL. Sin un puente, el
tablero no se puede construir en una máquina de desarrollo.

Este comando salva esa distancia: vuelca las dos vistas de HU-29 a CSV, que
Power BI lee de forma nativa en cualquier sistema operativo y sin controladores.

En producción el tablero se conecta directo a PostgreSQL con el rol de solo
lectura (ver «Analítica · Diccionario de Vistas» en la Wiki); el CSV es el
camino para desarrollar y para sustentar sin montar un servidor.
"""

import csv
import datetime
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

# Las vistas que crean las migraciones 0009 (HU-29), 0013 (HU-31) y 0014 (HU-32).
VISTAS = (
    "analitica_requerimientos",
    "analitica_items",
    "analitica_tiempo_atencion",
    "analitica_tiempo_atencion_mensual",
    "analitica_devoluciones",
    "analitica_tasa_devolucion_mensual",
)

DESTINO_POR_OMISION = "analitica"


def _valor_csv(valor):
    """Convierte un valor de la base a texto apto para CSV.

    Las fechas se escriben en ISO (``2026-10-13``) porque es lo que Power BI
    reconoce sin ambigüedad: con ``13/10/2026`` interpretaría mes y día al revés
    según la configuración regional de quien abra el archivo.
    """
    if valor is None:
        return ""
    if isinstance(valor, (datetime.datetime, datetime.date)):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, bool):
        # `true`/`false` en minúscula: Power BI los reconoce como booleanos.
        return "true" if valor else "false"
    return str(valor)


class Command(BaseCommand):
    help = (
        "Exporta las vistas analíticas (HU-29) a archivos CSV para construir el "
        "tablero de indicadores (HU-30) con Power BI Desktop."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--destino",
            default=DESTINO_POR_OMISION,
            help=f"Carpeta donde escribir los CSV (por omisión `{DESTINO_POR_OMISION}`).",
        )

    def handle(self, *args, **options):
        destino = Path(options["destino"])
        destino.mkdir(parents=True, exist_ok=True)

        for vista in VISTAS:
            filas, archivo = self._exportar(vista, destino)
            self.stdout.write(self.style.SUCCESS(f"{archivo} — {filas} filas."))

        self.stdout.write("")
        self.stdout.write(
            "Abre Power BI Desktop → Obtener datos → Texto/CSV y selecciona los "
            "archivos. Guía completa en la Wiki: «Tablero de Indicadores»."
        )

    def _exportar(self, vista, destino):
        archivo = destino / f"{vista}.csv"
        with connection.cursor() as cursor:
            try:
                cursor.execute(f"SELECT * FROM {vista}")  # noqa: S608 - nombre de lista fija
            except Exception as error:  # la vista no existe: falta migrar
                raise CommandError(
                    f"No se pudo leer la vista `{vista}`: {error}. ¿Corriste `manage.py migrate`?"
                ) from error

            encabezados = [columna[0] for columna in cursor.description]
            registros = cursor.fetchall()

        # `utf-8-sig` escribe la marca de orden de bytes que Power BI y Excel
        # necesitan para leer bien las tildes y la ñ. Sin ella, «Logística»
        # llega como «LogÃ­stica».
        with archivo.open("w", encoding="utf-8-sig", newline="") as salida:
            escritor = csv.writer(salida)
            escritor.writerow(encabezados)
            escritor.writerows([_valor_csv(valor) for valor in fila] for fila in registros)

        return len(registros), archivo
