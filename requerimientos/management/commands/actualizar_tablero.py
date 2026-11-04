"""Actualiza los datos del tablero de Power BI (HU-33).

Lo corre la tarea programada del servidor (``despliegue/crontab``) todos los
días; también se puede correr a mano para no esperar a la siguiente corrida:

    python manage.py actualizar_tablero

La lógica vive en ``requerimientos/tablero.py``.
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from requerimientos import tablero


class Command(BaseCommand):
    help = (
        "Regenera los CSV de las vistas analíticas que lee el tablero de Power BI "
        "y deja constancia de la actualización (HU-33)."
    )

    def handle(self, *args, **options):
        try:
            estado = tablero.actualizar()
        except Exception as error:
            # Código de salida distinto de cero: el fallo queda en el registro
            # de la tarea programada y la página de indicadores lo avisa.
            raise CommandError(f"No se pudo actualizar el tablero: {error}") from error

        fecha = timezone.localtime(estado["ultima_exitosa"]).strftime("%Y-%m-%d %H:%M")
        self.stdout.write(
            self.style.SUCCESS(f"Tablero actualizado ({fecha}) en {tablero.carpeta_datos()}.")
        )
