"""Crea las cuentas de validación del cliente para la entrega final.

Cada cuenta se crea con su correo corporativo de Coinogas y un perfil temporal
asignado para validar los flujos del sistema (Administrador, Analista y
Solicitante). Luego se ajustará al rol operativo definitivo de cada persona.
"""

import secrets
import string

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from requerimientos import perfiles

# Cuentas de validación de Coinogas con perfiles temporales para pruebas y entrega
CUENTAS_CLIENTE = (
    (
        "gerardo.cuadros",
        "gerardo.cuadros@coinogas.com",
        "Gerardo",
        "Cuadros",
        perfiles.ADMINISTRADOR,
    ),
    (
        "sergio.quintero",
        "sergio.quintero@coinogas.com",
        "Sergio",
        "Quintero",
        perfiles.ANALISTA,
    ),
    (
        "alejandra.silva",
        "alejandra.silva@coinogas.com",
        "Alejandra",
        "Silva",
        perfiles.SOLICITANTE,
    ),
)


def _clave_aleatoria(largo=14):
    alfabeto = string.ascii_letters + string.digits
    return "".join(secrets.choice(alfabeto) for _ in range(largo))


class Command(BaseCommand):
    help = "Crea las 3 cuentas de validación del cliente con correo corporativo y perfil temporal."

    def handle(self, *args, **options):
        grupos = {g.name: g for g in perfiles.asegurar_grupos()}
        modelo_usuario = get_user_model()

        for usuario, email, nombre, apellido, perfil in CUENTAS_CLIENTE:
            cuenta, creada = modelo_usuario.objects.get_or_create(
                username=usuario,
                defaults={
                    "email": email,
                    "first_name": nombre,
                    "last_name": apellido,
                    "is_staff": perfil == perfiles.ADMINISTRADOR,
                },
            )
            # Asegurar el grupo correspondiente al perfil
            if perfil in grupos:
                cuenta.groups.set([grupos[perfil]])

            if creada:
                # La clave se imprime una sola vez, al crearla. Si la cuenta ya
                # existía no se toca: cambiarla en silencio dejaría fuera a
                # quien ya la estuviera usando.
                clave = _clave_aleatoria()
                cuenta.set_password(clave)
                cuenta.save()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  {usuario} ({email} / {perfil}) — clave generada: {clave}"
                    )
                )
            else:
                cuenta.save()
                self.stdout.write(
                    f"  {usuario} ({email} / {perfil}) — ya existía, clave sin cambios."
                )
