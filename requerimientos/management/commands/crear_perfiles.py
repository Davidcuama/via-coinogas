"""Crea los grupos de perfil y, opcionalmente, cuentas de demostración."""

import secrets
import string

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from requerimientos import perfiles

# Cuentas que se crean con --con-demo, para poder recorrer los tres perfiles
# sin tener que darlos de alta a mano en el admin.
CUENTAS_DEMO = (
    ("solicitante", "Daniela", "Arango", perfiles.SOLICITANTE),
    ("analista", "Daryi", "Silva", perfiles.ANALISTA),
    ("admin.compras", "David", "Cuadros", perfiles.ADMINISTRADOR),
)


def _clave_aleatoria(largo=14):
    alfabeto = string.ascii_letters + string.digits
    return "".join(secrets.choice(alfabeto) for _ in range(largo))


class Command(BaseCommand):
    help = (
        "Crea los grupos de perfil (Solicitante, Analista de compras, "
        "Administrador). Con --con-demo agrega una cuenta de cada uno."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--con-demo",
            action="store_true",
            help="Crea también una cuenta de ejemplo por perfil, con clave aleatoria.",
        )

    def handle(self, *args, **options):
        for grupo in perfiles.asegurar_grupos():
            self.stdout.write(self.style.SUCCESS(f"Perfil '{grupo.name}' disponible."))

        if not options["con_demo"]:
            self.stdout.write(
                self.style.WARNING(
                    "Las cuentas se crean desde /admin. Usa --con-demo si quieres "
                    "una de cada perfil para probar."
                )
            )
            return

        modelo_usuario = get_user_model()
        for usuario, nombre, apellido, perfil in CUENTAS_DEMO:
            cuenta, creada = modelo_usuario.objects.get_or_create(
                username=usuario,
                defaults={
                    "first_name": nombre,
                    "last_name": apellido,
                    # El administrador necesita entrar al panel de Django.
                    "is_staff": perfil == perfiles.ADMINISTRADOR,
                },
            )
            cuenta.groups.set([g for g in perfiles.asegurar_grupos() if g.name == perfil])

            if creada:
                # La clave se imprime una sola vez, al crearla. Si la cuenta ya
                # existía no se toca: cambiarla en silencio dejaría fuera a
                # quien ya la estuviera usando.
                clave = _clave_aleatoria()
                cuenta.set_password(clave)
                cuenta.save()
                self.stdout.write(self.style.SUCCESS(f"  {usuario} ({perfil}) — clave: {clave}"))
            else:
                cuenta.save()
                self.stdout.write(f"  {usuario} ({perfil}) — ya existía, clave sin cambios.")

        self.stdout.write(
            self.style.WARNING("Cuentas de demostración: no las dejes en un entorno real.")
        )
