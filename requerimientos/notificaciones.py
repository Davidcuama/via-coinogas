"""Notificación por correo al área de compras (HU-19).

El analista de compras se entera de que hay un requerimiento nuevo por correo, sin
tener que entrar a revisar el sistema. El aviso sale una sola vez, cuando la
radicación ya quedó confirmada en la base de datos.

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
