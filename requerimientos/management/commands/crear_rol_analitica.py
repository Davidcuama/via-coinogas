"""HU-29: crea el rol de base de datos de solo lectura para analítica.

El tablero (Power BI o el propio, HU-30) se conecta con este rol, que solo puede
hacer ``SELECT`` sobre las dos vistas analíticas. No alcanza las tablas
transaccionales ni puede insertar, actualizar o eliminar nada. Así, abrir el dato
al reporte no abre una puerta para corromper la operación.

Solo aplica a PostgreSQL (el motor de producción). Es idempotente: se puede
correr varias veces sin romper nada.

Uso:
    python manage.py crear_rol_analitica --password "<clave-segura>"

Si no se pasa ``--password``, se toma de la variable de entorno
``ANALITICA_DB_PASSWORD``.
"""

import os

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

ROL = "analitica_lectura"

VISTAS = ("analitica_requerimientos", "analitica_items")


class Command(BaseCommand):
    help = "Crea/actualiza el rol de solo lectura para las vistas analíticas (HU-29)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            help="Contraseña del rol. Si se omite, se usa ANALITICA_DB_PASSWORD.",
        )
        parser.add_argument(
            "--rol",
            default=ROL,
            help=f"Nombre del rol a crear (por defecto '{ROL}').",
        )

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError(
                f"Este comando solo aplica a PostgreSQL. El motor actual es '{connection.vendor}'."
            )

        clave = options["password"] or os.environ.get("ANALITICA_DB_PASSWORD")
        if not clave:
            raise CommandError(
                "Falta la contraseña: pásala con --password o define ANALITICA_DB_PASSWORD."
            )

        rol = options["rol"]
        db = connection.settings_dict["NAME"]

        with connection.cursor() as cursor:
            # El nombre del rol es un identificador, no un parámetro: no puede ir
            # como placeholder. Se restringe a un identificador simple para evitar
            # inyección.
            if not rol.replace("_", "").isalnum():
                raise CommandError("El nombre del rol debe ser alfanumérico (con guión bajo).")

            # Crear el rol si no existe; si existe, solo actualizar la contraseña.
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s;", [rol])
            existe = cursor.fetchone() is not None
            if existe:
                cursor.execute(f'ALTER ROLE "{rol}" WITH LOGIN PASSWORD %s;', [clave])
                self.stdout.write(self.style.WARNING(f"Rol '{rol}' ya existía: clave actualizada."))
            else:
                cursor.execute(f'CREATE ROLE "{rol}" WITH LOGIN PASSWORD %s;', [clave])
                self.stdout.write(self.style.SUCCESS(f"Rol '{rol}' creado."))

            # Permiso de conexión a la base y uso del esquema público.
            cursor.execute(f'GRANT CONNECT ON DATABASE "{db}" TO "{rol}";')
            cursor.execute(f'GRANT USAGE ON SCHEMA public TO "{rol}";')

            # Partimos de cero: el rol no debe heredar permisos amplios.
            cursor.execute(f'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "{rol}";')

            # Solo SELECT, y solo sobre las vistas analíticas.
            for vista in VISTAS:
                cursor.execute(f'GRANT SELECT ON "{vista}" TO "{rol}";')

        self.stdout.write(
            self.style.SUCCESS(
                f"Listo. '{rol}' puede hacer SELECT únicamente sobre: {', '.join(VISTAS)}."
            )
        )
