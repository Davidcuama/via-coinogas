"""Señales de la aplicación.

HU-36: al iniciar sesión cualquier usuario, se le envía a su propia cuenta un
correo de alerta de seguridad. La señal ``user_logged_in`` de Django se dispara
después de autenticar, así que el aviso no interfiere con el ingreso.
"""

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .notificaciones import notificar_alerta_login


@receiver(user_logged_in)
def avisar_inicio_de_sesion(sender, request, user, **kwargs):
    """Dispara la alerta de inicio de sesión al usuario que acaba de entrar (HU-36).

    ``notificar_alerta_login`` ya captura sus propios errores de correo y nunca
    propaga una excepción, de modo que un fallo de SMTP no puede bloquear el
    acceso del usuario.
    """
    notificar_alerta_login(user, request=request)
