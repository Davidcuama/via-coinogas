"""Borrador del requerimiento (HU-18).

El borrador es deliberadamente temporal: vive en la sesión del solicitante, no en
la base de datos. Un requerimiento a medio diligenciar no puede guardarse como
``Requerimiento`` por dos razones del propio diseño del formato ADM-F-22:

* HU-15 exige que no quede ningún campo sin diligenciar, así que un borrador
  nunca pasaría la validación del modelo.
* HU-16 asigna el consecutivo de radicación al guardar, y no tiene sentido
  quemar un número de radicación en algo que todavía no se ha radicado.

Por eso el borrador guarda los valores tal como los escribió el solicitante, sin
validarlos, y se descarta en cuanto el requerimiento queda radicado.
"""

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .forms import RequerimientoForm

# Clave bajo la que vive el borrador dentro de la sesión.
CLAVE_SESION = "borrador_requerimiento"

# Campos que se conservan: los mismos que expone el formulario de radicación.
CAMPOS_BORRADOR = tuple(RequerimientoForm.Meta.fields)

# `prioridad` llega siempre con el valor por defecto (Media, HU-04), de modo que
# no es información que el solicitante haya diligenciado: no cuenta para decidir
# si el formulario está en blanco.
CAMPOS_DILIGENCIABLES = tuple(campo for campo in CAMPOS_BORRADOR if campo != "prioridad")


def _texto(datos, campo):
    """Valor de un campo como texto plano, sin espacios sobrantes."""
    return (datos.get(campo) or "").strip()


def esta_en_blanco(datos):
    """``True`` si el solicitante no diligenció nada: no hay borrador que guardar."""
    return not any(_texto(datos, campo) for campo in CAMPOS_DILIGENCIABLES)


def guardar(sesion, datos):
    """Guarda en la sesión lo diligenciado hasta el momento, sin validarlo.

    Un borrador es incompleto por definición; se almacenan los valores crudos
    para poder devolvérselos al solicitante cuando retome el formulario.
    """
    sesion[CLAVE_SESION] = {
        "valores": {campo: _texto(datos, campo) for campo in CAMPOS_BORRADOR},
        "guardado_en": timezone.now().isoformat(),
    }
    sesion.modified = True


def descartar(sesion):
    """Elimina el borrador. Se llama al descartarlo y al radicar el requerimiento.

    Devuelve ``True`` si había un borrador que eliminar.
    """
    if CLAVE_SESION not in sesion:
        return False
    del sesion[CLAVE_SESION]
    sesion.modified = True
    return True


def valores(sesion):
    """Valores del borrador listos para precargar el formulario.

    Se omiten los campos vacíos para que el formulario aplique sus propios
    valores iniciales (por ejemplo la prioridad Media de HU-04).
    """
    borrador = sesion.get(CLAVE_SESION)
    if not borrador:
        return {}
    return {campo: valor for campo, valor in borrador["valores"].items() if valor}


def resumen(sesion):
    """Datos del borrador para el aviso en pantalla, o ``None`` si no hay ninguno."""
    borrador = sesion.get(CLAVE_SESION)
    if not borrador:
        return None
    return {
        "guardado_en": parse_datetime(borrador["guardado_en"]),
        "campos_diligenciados": sum(1 for valor in borrador["valores"].values() if valor),
    }
