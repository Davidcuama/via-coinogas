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

from .forms import ItemFormSet, RequerimientoForm

# Clave bajo la que vive el borrador dentro de la sesión.
CLAVE_SESION = "borrador_requerimiento"

# Campos que se conservan: los mismos que expone el formulario de radicación.
CAMPOS_BORRADOR = tuple(RequerimientoForm.Meta.fields)

# `prioridad` llega siempre con el valor por defecto (Media, HU-04), de modo que
# no es información que el solicitante haya diligenciado: no cuenta para decidir
# si el formulario está en blanco.
CAMPOS_DILIGENCIABLES = tuple(campo for campo in CAMPOS_BORRADOR if campo != "prioridad")

# HU-18 + HU-06: la tabla de ítems también forma parte de lo diligenciado. Se
# guarda fila por fila, con los mismos campos que expone el formulario de ítem.
PREFIJO_ITEMS = ItemFormSet.get_default_prefix()

CAMPOS_ITEM = (
    "cantidad",
    "unidad_medida",
    "descripcion",
    "especificaciones_tecnicas",
    "precio_referencia",
)

# Las casillas no viajan en el POST cuando están desmarcadas, así que se guardan
# como booleanos y no como texto.
CAMPOS_ITEM_BOOLEANOS = ("requiere_calibracion", "es_reembolsable")

# `unidad_medida` llega siempre preseleccionada (HU-07), igual que `prioridad` en
# el encabezado: una fila que solo la trae a ella sigue estando en blanco.
CAMPOS_ITEM_DILIGENCIABLES = tuple(campo for campo in CAMPOS_ITEM if campo != "unidad_medida")

# Tope defensivo: TOTAL_FORMS viene del navegador y no se recorre a ciegas.
MAX_FILAS_ITEM = 1000


def _texto(datos, campo):
    """Valor de un campo como texto plano, sin espacios sobrantes."""
    return (datos.get(campo) or "").strip()


def _filas_items(datos):
    """Filas de ítems diligenciadas dentro de un envío del formulario (HU-18).

    Se descartan las filas marcadas para eliminar y las que quedaron en blanco:
    una fila que el usuario agregó y no llenó no es información que valga la
    pena conservar.
    """
    try:
        total = int(datos.get(f"{PREFIJO_ITEMS}-TOTAL_FORMS", 0))
    except (TypeError, ValueError):
        return []

    filas = []
    for indice in range(min(total, MAX_FILAS_ITEM)):
        campo = f"{PREFIJO_ITEMS}-{indice}-%s"
        if datos.get(campo % "DELETE"):
            continue
        fila = {nombre: _texto(datos, campo % nombre) for nombre in CAMPOS_ITEM}
        fila.update({nombre: bool(datos.get(campo % nombre)) for nombre in CAMPOS_ITEM_BOOLEANOS})
        if any(fila[nombre] for nombre in CAMPOS_ITEM_DILIGENCIABLES):
            filas.append(fila)
    return filas


def esta_en_blanco(datos):
    """``True`` si el solicitante no diligenció nada: ni encabezado ni ítems."""
    encabezado = any(_texto(datos, campo) for campo in CAMPOS_DILIGENCIABLES)
    return not encabezado and not _filas_items(datos)


def guardar(sesion, datos):
    """Guarda en la sesión lo diligenciado hasta el momento, sin validarlo.

    Un borrador es incompleto por definición; se almacenan los valores crudos
    para poder devolvérselos al solicitante cuando retome el formulario.
    """
    sesion[CLAVE_SESION] = {
        "valores": {campo: _texto(datos, campo) for campo in CAMPOS_BORRADOR},
        "items": _filas_items(datos),
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


def items(sesion):
    """Filas de ítems guardadas en el borrador (HU-18).

    Se lee con ``get`` porque una sesión abierta antes de que el borrador
    guardara ítems no trae esa clave; en ese caso simplemente no hay filas.
    """
    borrador = sesion.get(CLAVE_SESION)
    if not borrador:
        return []
    return borrador.get("items", [])


def resumen(sesion):
    """Datos del borrador para el aviso en pantalla, o ``None`` si no hay ninguno."""
    borrador = sesion.get(CLAVE_SESION)
    if not borrador:
        return None
    return {
        "guardado_en": parse_datetime(borrador["guardado_en"]),
        "campos_diligenciados": sum(1 for valor in borrador["valores"].values() if valor),
        "items": len(borrador.get("items", [])),
    }
