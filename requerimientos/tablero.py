"""Actualización programada de los datos del tablero de Power BI (HU-33).

El cliente trabaja con Power BI Desktop, sin licencias del servicio de Power BI,
así que el tablero no se puede refrescar solo en la nube. Lo que sí se puede es
que los datos que lee estén siempre al día: una tarea programada del servidor
(``despliegue/crontab``) corre ``manage.py actualizar_tablero`` todos los días y
regenera los CSV de las vistas analíticas. El jefe del área los descarga desde la
página «Indicadores» y en Power BI solo pulsa *Actualizar*.

Tres decisiones:

- **Todo o nada.** Los CSV se escriben primero en una carpeta aparte y solo se
  pasan a la definitiva cuando salieron todos. Si la exportación falla a la
  mitad, quedan los del día anterior completos, y no una mezcla de ayer y hoy
  cuyos números no cuadran entre sí.
- **Constancia en un archivo, no en la base.** Cada corrida deja
  ``ultima_actualizacion.json`` con la fecha y el resultado. Una tabla nueva
  obligaría a una migración para algo que solo lee la página de indicadores, y
  si la base es justo lo que falló, ahí no quedaría registrado el fallo.
- **Un fallo no toca la aplicación.** La tarea corre en un proceso aparte del
  servidor web; si falla, se registra, la página avisa y la radicación sigue.
"""

import json
import logging
import os
import shutil
import zipfile
from datetime import datetime
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.utils import timezone

from .management.commands.exportar_analitica import VISTAS

logger = logging.getLogger(__name__)

ARCHIVO_ESTADO = "ultima_actualizacion.json"
ARCHIVO_PAQUETE = "datos-tablero-via-compras.zip"
CARPETA_EN_CURSO = ".en-curso"

RESULTADO_EXITOSO = "exitosa"
RESULTADO_FALLIDO = "fallida"


def carpeta_datos():
    """Carpeta donde quedan los CSV, el paquete para descargar y la constancia."""
    return Path(settings.ANALITICA_DIR)


def ruta_paquete():
    return carpeta_datos() / ARCHIVO_PAQUETE


def actualizar():
    """Regenera los datos del tablero y deja constancia del resultado.

    Devuelve la constancia guardada. Si algo falla, la constancia queda como
    fallida (conservando la fecha de la última actualización buena) y la
    excepción se vuelve a lanzar, para que la tarea programada termine con error
    y quede en su registro.
    """
    destino = carpeta_datos()
    intento = timezone.now()
    anterior = leer_estado()
    ultima_exitosa = anterior["ultima_exitosa"] if anterior else None

    try:
        destino.mkdir(parents=True, exist_ok=True)
        en_curso = destino / CARPETA_EN_CURSO
        shutil.rmtree(en_curso, ignore_errors=True)
        call_command("exportar_analitica", destino=str(en_curso), stdout=StringIO())
        _publicar(en_curso, destino)
    except Exception as error:
        logger.exception("Falló la actualización programada del tablero (HU-33).")
        _guardar_estado(
            destino,
            {
                "resultado": RESULTADO_FALLIDO,
                "ultimo_intento": intento.isoformat(),
                "ultima_exitosa": ultima_exitosa.isoformat() if ultima_exitosa else None,
                "detalle": str(error),
            },
        )
        raise

    estado = {
        "resultado": RESULTADO_EXITOSO,
        "ultimo_intento": intento.isoformat(),
        "ultima_exitosa": intento.isoformat(),
        "detalle": "",
    }
    _guardar_estado(destino, estado)
    logger.info("Datos del tablero actualizados en %s.", destino)
    return leer_estado()


def _publicar(en_curso, destino):
    """Pasa los CSV recién generados a su carpeta y arma el paquete descargable."""
    for vista in VISTAS:
        # `os.replace` reemplaza cada archivo de una sola vez: quien lo esté
        # leyendo en ese instante ve el viejo o el nuevo, nunca uno a medias.
        os.replace(en_curso / f"{vista}.csv", destino / f"{vista}.csv")
    shutil.rmtree(en_curso, ignore_errors=True)

    paquete_temporal = destino / f"{ARCHIVO_PAQUETE}.tmp"
    with zipfile.ZipFile(paquete_temporal, "w", compression=zipfile.ZIP_DEFLATED) as paquete:
        for vista in VISTAS:
            paquete.write(destino / f"{vista}.csv", arcname=f"{vista}.csv")
    os.replace(paquete_temporal, destino / ARCHIVO_PAQUETE)


def _guardar_estado(destino, estado):
    """Escribe la constancia; si ni eso se puede, lo deja en el registro."""
    try:
        destino.mkdir(parents=True, exist_ok=True)
        temporal = destino / f"{ARCHIVO_ESTADO}.tmp"
        temporal.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporal, destino / ARCHIVO_ESTADO)
    except OSError:
        logger.exception("No se pudo guardar la constancia de actualización del tablero.")


def leer_estado():
    """Constancia de la última corrida, con las fechas ya convertidas.

    Devuelve ``None`` si la tarea no ha corrido nunca o si el archivo no se
    puede leer: la página de indicadores no debe caerse por esto.
    """
    archivo = carpeta_datos() / ARCHIVO_ESTADO
    try:
        datos = json.loads(archivo.read_text(encoding="utf-8"))
        return {
            "resultado": datos["resultado"],
            "exitosa": datos["resultado"] == RESULTADO_EXITOSO,
            "ultimo_intento": _fecha(datos.get("ultimo_intento")),
            "ultima_exitosa": _fecha(datos.get("ultima_exitosa")),
            "detalle": datos.get("detalle", ""),
            "hay_paquete": ruta_paquete().exists(),
        }
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _fecha(texto):
    return datetime.fromisoformat(texto) if texto else None
