from django.core.management.base import BaseCommand

from requerimientos.models import Prioridad


class Command(BaseCommand):
    help = "Carga los valores iniciales del catálogo de prioridades: Alta, Media, Baja (HU-04)."

    def handle(self, *args, **options):
        valores = [
            (Prioridad.ALTA, 1),
            (Prioridad.MEDIA, 2),
            (Prioridad.BAJA, 3),
        ]
        for nombre, orden in valores:
            obj, creado = Prioridad.objects.update_or_create(
                nombre=nombre,
                defaults={"orden": orden},
            )
            estado = "creada" if creado else "actualizada"
            self.stdout.write(self.style.SUCCESS(f"Prioridad '{obj}' {estado}."))

        self.stdout.write(
            self.style.WARNING(
                "Nota: Area y CentroCosto no se cargan aquí porque sus valores "
                "dependen de la información real de Coinogas. Agrégalos desde "
                "/admin o extiende este comando cuando tengan esos datos."
            )
        )
