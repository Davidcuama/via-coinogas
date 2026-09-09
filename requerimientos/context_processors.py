"""Datos del usuario que la barra superior necesita en todas las pantallas."""

from . import perfiles


def perfil(request):
    """Perfil, iniciales y permisos de navegación de quien está en sesión."""
    usuario = getattr(request, "user", None)
    if usuario is None or not usuario.is_authenticated:
        return {}

    nombre = usuario.get_full_name() or usuario.get_username()
    partes = nombre.split()
    # Dos letras: iniciales del nombre y el apellido, o las dos primeras del
    # usuario cuando solo hay una palabra.
    iniciales = (partes[0][:1] + partes[1][:1]).upper() if len(partes) >= 2 else nombre[:2].upper()

    del_usuario = perfiles.perfiles_de(usuario)
    # Se muestra uno solo, el de mayor alcance, para no llenar la barra.
    for candidato in (perfiles.ADMINISTRADOR, perfiles.ANALISTA, perfiles.SOLICITANTE):
        if candidato in del_usuario:
            actual = candidato
            break
    else:
        actual = perfiles.SOLICITANTE

    return {
        "perfil_actual": actual,
        "iniciales_usuario": iniciales,
        "es_analista": perfiles.ANALISTA in del_usuario,
        "es_administrador": perfiles.ADMINISTRADOR in del_usuario,
    }
