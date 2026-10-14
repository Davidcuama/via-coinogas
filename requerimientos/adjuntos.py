"""Adjuntos del requerimiento (HU-11).

Fotografías del artículo y documentos de soporte —fichas técnicas, cotizaciones
de referencia— para que compras no tenga que adivinar qué se está pidiendo.

Las reglas viven aquí y no en el formulario porque también las usa la
corrección de un requerimiento devuelto (HU-24), que suma adjuntos a los que ya
había.

Sobre la validación: la extensión la escoge quien sube el archivo, así que no
basta. Se revisan además los primeros bytes —la "firma" que cada formato lleva
al principio—, de modo que un ejecutable renombrado a ``.pdf`` no pasa. No se
abre ni se interpreta el contenido: leer la firma es suficiente para saber qué
es, y es más seguro que procesar un archivo que todavía no se sabe si es
legítimo.
"""

from pathlib import Path

from django.core.exceptions import ValidationError
from django.template.defaultfilters import filesizeformat

from . import perfiles
from .models import Adjunto

# Un archivo de más de 10 MB no es una foto de celular ni una ficha técnica:
# casi siempre es un video o un escaneo sin comprimir, y llenaría el disco.
TAMANO_MAXIMO = 10 * 1024 * 1024

# Diez alcanzan para un requerimiento con varios ítems, cada uno con su foto y
# su ficha. Más que eso suele ser un paquete que corresponde a otro canal.
MAX_ADJUNTOS = 10

_JPEG = (b"\xff\xd8\xff",)
_PNG = (b"\x89PNG\r\n\x1a\n",)
_PDF = (b"%PDF-",)
# Word y Excel modernos son archivos ZIP por dentro.
_OFFICE_ZIP = (b"PK\x03\x04",)
# Word y Excel anteriores a 2007 usan el contenedor OLE de Microsoft.
_OFFICE_OLE = (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",)

# Marcas que identifican un HEIC/HEIF —el formato de las fotos de iPhone—
# dentro de la caja `ftyp` del archivo.
_MARCAS_HEIF = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"}

# extensión -> (tipo de adjunto, firmas válidas). Las firmas `None` se revisan
# con una función propia porque no están al inicio exacto del archivo.
FORMATOS = {
    ".jpg": (Adjunto.Tipo.FOTO, _JPEG),
    ".jpeg": (Adjunto.Tipo.FOTO, _JPEG),
    ".png": (Adjunto.Tipo.FOTO, _PNG),
    ".webp": (Adjunto.Tipo.FOTO, None),
    ".heic": (Adjunto.Tipo.FOTO, None),
    ".heif": (Adjunto.Tipo.FOTO, None),
    ".pdf": (Adjunto.Tipo.DOCUMENTO, _PDF),
    ".docx": (Adjunto.Tipo.DOCUMENTO, _OFFICE_ZIP),
    ".xlsx": (Adjunto.Tipo.DOCUMENTO, _OFFICE_ZIP),
    ".doc": (Adjunto.Tipo.DOCUMENTO, _OFFICE_OLE),
    ".xls": (Adjunto.Tipo.DOCUMENTO, _OFFICE_OLE),
}

EXTENSIONES = tuple(FORMATOS)

# Lo que el navegador acepta en el selector de archivos. Es solo una ayuda: el
# servidor vuelve a revisar todo.
ACCEPT = ",".join(EXTENSIONES)

# Tipos que el navegador puede mostrar en una pestaña en vez de descargarlos.
# HEIC queda fuera: la mayoría de navegadores no lo muestran.
_SE_VEN_EN_EL_NAVEGADOR = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}


def _cabecera(archivo, largo=16):
    """Primeros bytes del archivo, sin mover su posición de lectura."""
    archivo.seek(0)
    cabecera = archivo.read(largo)
    archivo.seek(0)
    return cabecera


def _firma_valida(extension, cabecera):
    _, firmas = FORMATOS[extension]
    if firmas is not None:
        return any(cabecera.startswith(firma) for firma in firmas)
    if extension == ".webp":
        # RIFF....WEBP: el tamaño ocupa los bytes 4 a 8.
        return cabecera[:4] == b"RIFF" and cabecera[8:12] == b"WEBP"
    # HEIC/HEIF: ....ftyp<marca>
    return cabecera[4:8] == b"ftyp" and cabecera[8:12] in _MARCAS_HEIF


def validar_archivo(archivo):
    """Revisa un archivo subido y devuelve el tipo de adjunto que le corresponde.

    Lanza ``ValidationError`` con un mensaje que nombra el archivo, para que
    quien sube varios sepa cuál fue el que falló.
    """
    nombre = archivo.name
    extension = Path(nombre).suffix.lower()

    if extension not in FORMATOS:
        raise ValidationError(
            f"«{nombre}» no es un tipo de archivo admitido. "
            "Sube fotos (JPG, PNG, WEBP, HEIC) o documentos (PDF, Word, Excel).",
            code="tipo_no_admitido",
        )
    if archivo.size == 0:
        raise ValidationError(f"«{nombre}» está vacío.", code="vacio")
    if archivo.size > TAMANO_MAXIMO:
        raise ValidationError(
            f"«{nombre}» pesa {filesizeformat(archivo.size)}; "
            f"el máximo por archivo es {filesizeformat(TAMANO_MAXIMO)}.",
            code="muy_grande",
        )
    if not _firma_valida(extension, _cabecera(archivo)):
        raise ValidationError(
            f"«{nombre}» no es realmente un archivo {extension[1:].upper()}: "
            "su contenido no corresponde a la extensión.",
            code="contenido_no_coincide",
        )
    return FORMATOS[extension][0]


def validar_cantidad(nuevos, existentes=0):
    """Revisa que no se pase del máximo de adjuntos por requerimiento."""
    if existentes + nuevos > MAX_ADJUNTOS:
        disponibles = max(MAX_ADJUNTOS - existentes, 0)
        if existentes:
            mensaje = (
                f"Este requerimiento ya tiene {existentes} adjuntos; puedes sumar "
                f"{disponibles} más (el máximo es {MAX_ADJUNTOS})."
            )
        else:
            mensaje = f"Puedes adjuntar hasta {MAX_ADJUNTOS} archivos; seleccionaste {nuevos}."
        raise ValidationError(mensaje, code="demasiados")


def guardar(requerimiento, archivos, usuario):
    """Crea los adjuntos de un requerimiento ya guardado.

    Recibe pares ``(archivo, tipo)`` ya validados. Se llama dentro de la misma
    transacción que guarda el requerimiento: si algo falla, no queda un
    requerimiento a medias ni adjuntos huérfanos en la base de datos.
    """
    return [
        Adjunto.objects.create(
            requerimiento=requerimiento,
            archivo=archivo,
            nombre_original=Path(archivo.name).name[:255],
            tipo=tipo,
            tamano=archivo.size,
            subido_por=usuario,
        )
        for archivo, tipo in archivos
    ]


def puede_ver(usuario, adjunto):
    """Un adjunto lo ve quien radicó el requerimiento y el área de compras.

    Es la misma regla de la confirmación de radicación: el consecutivo que va
    en la ruta del archivo es adivinable, así que no basta con tener sesión.
    """
    if not usuario.is_authenticated:
        return False
    if perfiles.perfiles_de(usuario) & {perfiles.ANALISTA, perfiles.ADMINISTRADOR}:
        return True
    return adjunto.requerimiento.creado_por_id == usuario.pk


def se_ve_en_el_navegador(adjunto):
    """``True`` si el navegador puede mostrarlo en una pestaña.

    Las fotos y los PDF se abren directamente; Word, Excel y HEIC se descargan,
    porque el navegador no sabe mostrarlos.
    """
    return Path(adjunto.archivo.name).suffix.lower() in _SE_VEN_EN_EL_NAVEGADOR
