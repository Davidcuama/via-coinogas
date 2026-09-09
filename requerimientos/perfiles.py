"""Perfiles de usuario del sistema.

Los tres perfiles salen del prototipo de interfaces del Sprint 0 y del propio
proceso de Coinogas: quien pide la compra, quien la atiende y quien parametriza
el sistema. Se modelan como grupos de Django y no como un campo en el usuario,
porque una persona puede cumplir dos papeles —un analista de compras también
radica sus propios requerimientos— y un grupo admite esa superposición.

El perfil decide dos cosas: a dónde cae el usuario después de entrar y a qué
pantallas alcanza.
"""

from django.contrib.auth.models import Group

SOLICITANTE = "Solicitante"
ANALISTA = "Analista de compras"
ADMINISTRADOR = "Administrador"

PERFILES = (SOLICITANTE, ANALISTA, ADMINISTRADOR)

DESCRIPCIONES = {
    SOLICITANTE: ("Diligencia el requerimiento y consulta el estado de lo que ha radicado."),
    ANALISTA: ("Recibe las radicaciones en una bandeja y revisa el detalle de cada una."),
    ADMINISTRADOR: ("Parametriza áreas, centros de costo y prioridades, y gestiona las cuentas."),
}


def asegurar_grupos():
    """Crea los tres grupos si faltan. Idempotente."""
    return [Group.objects.get_or_create(name=nombre)[0] for nombre in PERFILES]


def perfiles_de(usuario):
    """Nombres de los perfiles que tiene el usuario."""
    if not usuario.is_authenticated:
        return set()
    perfiles = set(usuario.groups.values_list("name", flat=True))
    # Un superusuario administra el sistema aunque nadie lo haya puesto en el
    # grupo: si no fuera así, quien instala el proyecto quedaría fuera.
    if usuario.is_superuser:
        perfiles.add(ADMINISTRADOR)
    return perfiles


def es(usuario, perfil):
    return perfil in perfiles_de(usuario)


def destino_tras_ingresar(usuario):
    """Nombre de ruta a donde cae el usuario después de autenticarse.

    El orden importa: quien es analista y solicitante a la vez entra por la
    bandeja, que es su trabajo del día; para radicar tiene el enlace en la barra.
    """
    perfiles = perfiles_de(usuario)
    if ANALISTA in perfiles:
        return "requerimientos:bandeja"
    if ADMINISTRADOR in perfiles:
        return "admin:index"
    return "requerimientos:crear"
