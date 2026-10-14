"""Notificaciones por correo de la radicación (HU-19, HU-35) y la devolución (HU-24).

El área de compras y el propio solicitante se enteran de que hay un requerimiento
nuevo por correo, sin tener que entrar a revisar el sistema. Los avisos salen una
sola vez, cuando la radicación ya quedó confirmada en la base de datos.

Regla de negocio: **la notificación nunca puede tumbar la radicación**. Cuando el
solicitante ve su consecutivo, el requerimiento ya está guardado; si el servidor
SMTP está caído o mal configurado, el fallo se registra en el log y el solicitante
recibe su confirmación igual.
"""

import logging
import smtplib

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

ASUNTO = "[VIA Compras] Requerimiento {consecutivo} - prioridad {prioridad}"

PLANTILLA_TEXTO = "requerimientos/email/radicacion.txt"
PLANTILLA_HTML = "requerimientos/email/radicacion.html"

# HU-35: confirmación al solicitante.
ASUNTO_SOLICITANTE = "[VIA Compras] Confirmación de tu requerimiento {consecutivo}"
PLANTILLA_TEXTO_SOLICITANTE = "requerimientos/email/confirmacion_solicitante.txt"
PLANTILLA_HTML_SOLICITANTE = "requerimientos/email/confirmacion_solicitante.html"

# HU-24: devolución al solicitante y reenvío a compras.
ASUNTO_DEVOLUCION = "[VIA Compras] Tu requerimiento {consecutivo} necesita correcciones"
PLANTILLA_TEXTO_DEVOLUCION = "requerimientos/email/devolucion.txt"
PLANTILLA_HTML_DEVOLUCION = "requerimientos/email/devolucion.html"

ASUNTO_REENVIO = "[VIA Compras] {consecutivo} corregido y reenviado"
PLANTILLA_TEXTO_REENVIO = "requerimientos/email/reenvio.txt"
PLANTILLA_HTML_REENVIO = "requerimientos/email/reenvio.html"


def destinatarios():
    """Buzones del área de compras configurados en `COMPRAS_EMAILS` (ver `.env`)."""
    return [correo.strip() for correo in settings.COMPRAS_EMAILS if correo.strip()]


def notificar_radicacion(requerimiento):
    """Avisa al área de compras que se radicó un requerimiento.

    Devuelve ``True`` si el correo salió, ``False`` si no había a quién enviarlo o
    si el servidor de correo falló. En ningún caso propaga la excepción.
    """
    correos = destinatarios()
    if not correos:
        logger.warning(
            "HU-19: %s se radicó sin notificar, no hay buzones de compras "
            "configurados (COMPRAS_EMAILS).",
            requerimiento.consecutivo,
        )
        return False

    contexto = {
        "requerimiento": requerimiento,
        # HU-19 + HU-06: sin los ítems el aviso no le sirve al analista, que es
        # quien tiene que salir a cotizar. Se traen con su unidad de medida para
        # no disparar una consulta por fila.
        "items": requerimiento.items.select_related("unidad_medida"),
    }
    mensaje = EmailMultiAlternatives(
        subject=ASUNTO.format(
            consecutivo=requerimiento.consecutivo,
            prioridad=requerimiento.prioridad,
        ),
        body=render_to_string(PLANTILLA_TEXTO, contexto),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=correos,
    )
    # Cuerpo enriquecido para los clientes que lo soportan; el de texto plano
    # queda como alternativa para los que no.
    mensaje.attach_alternative(render_to_string(PLANTILLA_HTML, contexto), "text/html")

    try:
        mensaje.send()
    except (OSError, smtplib.SMTPException):
        # El requerimiento ya está radicado: se deja constancia y se sigue.
        logger.exception(
            "HU-19: no se pudo notificar la radicación de %s al área de compras.",
            requerimiento.consecutivo,
        )
        return False
    return True


def notificar_confirmacion_solicitante(requerimiento):
    """Envía al solicitante un correo de confirmación de su propia radicación (HU-35).

    El destinatario es el correo de la cuenta que radicó (`creado_por`), no el
    nombre libre del campo «solicitante»: ese campo se puede diligenciar a nombre
    de un compañero, pero quien necesita el respaldo por escrito es quien está en
    sesión. Sin cuenta asociada o sin correo registrado no hay a quién avisar.

    Devuelve ``True`` si el correo salió, ``False`` si no había a quién enviarlo o
    si el servidor de correo falló. En ningún caso propaga la excepción.
    """
    cuenta = requerimiento.creado_por
    correo = (cuenta.email if cuenta else "").strip()
    if not correo:
        logger.warning(
            "HU-35: %s se radicó sin confirmar al solicitante, la cuenta no tiene "
            "correo registrado.",
            requerimiento.consecutivo,
        )
        return False

    contexto = {
        "requerimiento": requerimiento,
        "items": requerimiento.items.select_related("unidad_medida"),
    }
    mensaje = EmailMultiAlternatives(
        subject=ASUNTO_SOLICITANTE.format(consecutivo=requerimiento.consecutivo),
        body=render_to_string(PLANTILLA_TEXTO_SOLICITANTE, contexto),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[correo],
    )
    mensaje.attach_alternative(render_to_string(PLANTILLA_HTML_SOLICITANTE, contexto), "text/html")

    try:
        mensaje.send()
    except (OSError, smtplib.SMTPException):
        # El requerimiento ya está radicado: se deja constancia y se sigue.
        logger.exception(
            "HU-35: no se pudo enviar la confirmación de %s al solicitante.",
            requerimiento.consecutivo,
        )
        return False
    return True


def _enviar(asunto, plantilla_texto, plantilla_html, contexto, para, historia):
    """Arma y envía un correo con versión de texto y HTML.

    Devuelve ``True`` si salió. Si el servidor de correo falla se registra y
    devuelve ``False``: el cambio que lo disparó ya quedó guardado y no se
    deshace por un aviso.
    """
    mensaje = EmailMultiAlternatives(
        subject=asunto,
        body=render_to_string(plantilla_texto, contexto),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=para,
    )
    mensaje.attach_alternative(render_to_string(plantilla_html, contexto), "text/html")
    try:
        mensaje.send()
    except (OSError, smtplib.SMTPException):
        logger.exception(
            "%s: no se pudo enviar el aviso de %s.",
            historia,
            contexto["requerimiento"].consecutivo,
        )
        return False
    return True


def notificar_devolucion(requerimiento, cambio, enlace_correccion):
    """Avisa al solicitante que su requerimiento fue devuelto y por qué (HU-24).

    Va a la cuenta que radicó, igual que la confirmación de HU-35, y lleva la
    observación del analista y el enlace directo para corregir: la idea es que
    no tenga que llamar ni escribir para saber qué falta.
    """
    cuenta = requerimiento.creado_por
    correo = (cuenta.email if cuenta else "").strip()
    if not correo:
        logger.warning(
            "HU-24: %s se devolvió sin avisar por correo, la cuenta no tiene correo "
            "registrado. El solicitante lo verá al entrar al sistema.",
            requerimiento.consecutivo,
        )
        return False

    contexto = {"requerimiento": requerimiento, "cambio": cambio, "enlace": enlace_correccion}
    return _enviar(
        ASUNTO_DEVOLUCION.format(consecutivo=requerimiento.consecutivo),
        PLANTILLA_TEXTO_DEVOLUCION,
        PLANTILLA_HTML_DEVOLUCION,
        contexto,
        [correo],
        "HU-24",
    )


def notificar_reenvio(requerimiento, cambio, enlace_ficha):
    """Avisa al área de compras que un requerimiento devuelto volvió corregido (HU-24)."""
    correos = destinatarios()
    if not correos:
        logger.warning(
            "HU-24: %s se reenvió sin notificar, no hay buzones de compras "
            "configurados (COMPRAS_EMAILS).",
            requerimiento.consecutivo,
        )
        return False

    contexto = {"requerimiento": requerimiento, "cambio": cambio, "enlace": enlace_ficha}
    return _enviar(
        ASUNTO_REENVIO.format(consecutivo=requerimiento.consecutivo),
        PLANTILLA_TEXTO_REENVIO,
        PLANTILLA_HTML_REENVIO,
        contexto,
        correos,
        "HU-24",
    )
