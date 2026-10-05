"""Notificaciones por correo de la radicación (HU-19, HU-35).

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
    mensaje.attach_alternative(
        render_to_string(PLANTILLA_HTML_SOLICITANTE, contexto), "text/html"
    )

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
