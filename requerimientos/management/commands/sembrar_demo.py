"""Siembra requerimientos de demostración variados (apoyo a HU-30).

El tablero de indicadores (HU-30) y la bandeja de compras no se pueden mostrar
con datos reales: el sistema todavía no está en producción. Y con dos o tres
requerimientos de prueba, todos del mismo área y la misma prioridad, las
gráficas de «distribución por área» y «por prioridad» salen con una sola barra.

Este comando genera un volumen creíble y repartido —varias áreas, las tres
prioridades, distintos meses, ítems con y sin precio— para que el tablero y las
pantallas de consulta se puedan construir y sustentar.

No toca el modelo ni agrega migraciones: solo inserta filas.
"""

import random
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from requerimientos.models import (
    Area,
    CambioEstado,
    CentroCosto,
    EstadoRequerimiento,
    Item,
    Prioridad,
    Requerimiento,
    UnidadMedida,
)

# Prefijo de las cuentas que crea este comando. Es lo que permite reconocer
# después qué datos son de demostración y borrarlos sin tocar nada real.
PREFIJO_DEMO = "demo."

SOLICITANTES = (
    ("ana.gomez", "Ana", "Gómez"),
    ("luis.mesa", "Luis", "Mesa"),
    ("carmen.ruiz", "Carmen", "Ruiz"),
    ("jorge.patino", "Jorge", "Patiño"),
)

# Quien mueve los estados en la demostración (HU-31): la bitácora pide un autor.
ANALISTA_DEMO = ("compras", "Analista", "Compras")

# HU-31: etapas del flujo normal de compras (HU-23) y cuántos días puede tomar
# cada una. Sin esta historia el indicador de tiempo de atención saldría vacío.
ETAPAS_ATENCION = (
    (EstadoRequerimiento.EN_REVISION, (0, 3)),
    (EstadoRequerimiento.EN_COTIZACION, (1, 6)),
    (EstadoRequerimiento.CERRADO, (1, 12)),
)

# Hasta qué etapa llega cada requerimiento: 0 = sigue radicado, 3 = cerrado. El
# cierre pesa doble para que haya suficientes cerrados con qué promediar.
AVANCES_POSIBLES = (0, 1, 2, 3, 3)

AREAS = (
    "Mantenimiento",
    "Producción",
    "Administración",
    "Logística",
    "HSEQ",
)

CENTROS_COSTO = (
    ("CC-100", "Planta Medellín"),
    ("CC-200", "Planta Bogotá"),
    ("CC-300", "Sede administrativa"),
    ("CC-400", "Flota de transporte"),
)

# Ítems verosímiles del negocio: insumos de oficina, repuestos y servicios.
CATALOGO_ITEMS = (
    ("Resma de papel carta", "UND", Decimal("24500")),
    ("Tóner negro para impresora multifuncional", "UND", Decimal("189000")),
    ("Manómetro de línea 0-100 psi", "UND", Decimal("320000")),
    ("Guantes de nitrilo talla M", "CJA", Decimal("48000")),
    ("Aceite hidráulico ISO 68", "GLN", Decimal("136000")),
    ("Válvula de bola 1/2 pulgada", "UND", Decimal("72000")),
    ("Servicio de calibración de equipo de medición", "SRV", Decimal("450000")),
    ("Botas de seguridad dieléctricas", "UND", Decimal("210000")),
    ("Rollo de cinta teflón", "ROL", Decimal("4800")),
    ("Mantenimiento preventivo de compresor", "SRV", Decimal("1250000")),
    ("Extintor multipropósito 10 lb", "UND", Decimal("95000")),
    ("Juego de llaves mixtas", "JGO", Decimal("185000")),
)

ESPECIFICACIONES = (
    "",
    "Marca equivalente o superior a la referencia actual.",
    "Rango 0-100 psi, norma ISO 5171, con certificado de fábrica.",
    "Debe cumplir norma NTC 2021 y traer ficha técnica.",
    "Compatible con el equipo instalado en la línea 2.",
)

JUSTIFICACIONES = (
    "Reposición de insumos agotados en el almacén.",
    "Mantenimiento preventivo programado para el próximo trimestre.",
    "Reemplazo de equipo que salió de servicio en la línea de producción.",
    "Dotación de personal nuevo que ingresa al área.",
    "Cumplimiento de requisito de la última auditoría de seguridad.",
)


class Command(BaseCommand):
    help = (
        "Siembra requerimientos de demostración variados para poder construir "
        "el tablero de indicadores (HU-30) y mostrar las pantallas de consulta. "
        "Solo para entornos de desarrollo."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--cantidad",
            type=int,
            default=40,
            help="Cuántos requerimientos sembrar (por omisión 40).",
        )
        parser.add_argument(
            "--meses",
            type=int,
            default=6,
            help="En cuántos meses hacia atrás repartirlos (por omisión 6).",
        )
        parser.add_argument(
            "--limpiar",
            action="store_true",
            help="Borra los datos de demostración sembrados antes y termina.",
        )
        parser.add_argument(
            "--forzar",
            action="store_true",
            help="Permite ejecutarlo con DEBUG=False. Úsalo solo si sabes por qué.",
        )
        parser.add_argument(
            "--semilla",
            type=int,
            default=None,
            help="Semilla aleatoria, para obtener siempre el mismo conjunto.",
        )

    def handle(self, *args, **options):
        # Son datos falsos: nunca deben entrar por accidente a un entorno real.
        if not settings.DEBUG and not options["forzar"]:
            raise CommandError(
                "DEBUG está en False: esto parece un entorno real y el comando "
                "siembra datos de demostración. Si de verdad lo quieres aquí, "
                "repítelo con --forzar."
            )

        if options["limpiar"]:
            self._limpiar()
            return

        existentes = self._consulta_demo().count()
        if existentes:
            raise CommandError(
                f"Ya hay {existentes} requerimientos de demostración sembrados. "
                "Ejecuta primero `manage.py sembrar_demo --limpiar` si quieres "
                "reemplazarlos."
            )

        cantidad = options["cantidad"]
        if cantidad < 1:
            raise CommandError("--cantidad tiene que ser al menos 1.")
        meses = max(options["meses"], 1)

        azar = random.Random(options["semilla"])  # noqa: S311 - datos de ejemplo, no criptografía
        self._sembrar(cantidad, meses, azar)

    # --- Limpieza ---

    def _consulta_demo(self):
        """Requerimientos sembrados por este comando."""
        return Requerimiento.objects.filter(creado_por__username__startswith=PREFIJO_DEMO)

    def _limpiar(self):
        borrados, _ = self._consulta_demo().delete()
        cuentas = get_user_model().objects.filter(username__startswith=PREFIJO_DEMO)
        numero_cuentas = cuentas.count()
        cuentas.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Datos de demostración eliminados: {borrados} filas y "
                f"{numero_cuentas} cuentas `{PREFIJO_DEMO}*`."
            )
        )

    # --- Siembra ---

    def _catalogos(self):
        """Asegura áreas, centros de costo, prioridades y unidades."""
        areas = [Area.objects.get_or_create(nombre=nombre)[0] for nombre in AREAS]
        centros = [
            CentroCosto.objects.get_or_create(codigo=codigo, defaults={"nombre": nombre})[0]
            for codigo, nombre in CENTROS_COSTO
        ]
        prioridades = [
            Prioridad.objects.get_or_create(nombre=nombre, defaults={"orden": orden})[0]
            for nombre, orden in ((Prioridad.ALTA, 1), (Prioridad.MEDIA, 2), (Prioridad.BAJA, 3))
        ]
        unidades = {
            codigo: UnidadMedida.objects.get_or_create(codigo=codigo, defaults={"nombre": codigo})[
                0
            ]
            for codigo in {codigo for _, codigo, _ in CATALOGO_ITEMS}
        }
        return areas, centros, prioridades, unidades

    def _cuentas(self):
        """Cuentas de demostración, con el prefijo que permite borrarlas después."""
        modelo = get_user_model()
        cuentas = []
        for usuario, nombre, apellido in SOLICITANTES:
            cuenta, _ = modelo.objects.get_or_create(
                username=f"{PREFIJO_DEMO}{usuario}",
                defaults={"first_name": nombre, "last_name": apellido},
            )
            cuentas.append(cuenta)
        return cuentas

    def _sembrar(self, cantidad, meses, azar):
        areas, centros, prioridades, unidades = self._catalogos()
        cuentas = self._cuentas()
        analista = self._analista()
        hoy = timezone.localdate()

        # Se reparten dentro del año en curso: el consecutivo lleva el año de
        # radicación (HU-16) y no tiene sentido que diga 2026 con fecha de 2025.
        dias_atras_max = min(meses * 30, (hoy - hoy.replace(month=1, day=1)).days)

        creados = 0
        with transaction.atomic():
            for _ in range(cantidad):
                cuenta = azar.choice(cuentas)
                requerimiento = Requerimiento.objects.create(
                    solicitante=f"{cuenta.first_name} {cuenta.last_name}",
                    area=azar.choice(areas),
                    centro_costo=azar.choice(centros),
                    justificacion=azar.choice(JUSTIFICACIONES),
                    prioridad=azar.choice(prioridades),
                    fecha_requerida=hoy + timedelta(days=azar.randint(5, 45)),
                    creado_por=cuenta,
                )

                self._agregar_items(requerimiento, unidades, azar)

                # `fecha_solicitud` es auto_now_add, así que create() siempre
                # pone hoy: la fecha se corre después con un UPDATE directo,
                # que es la única forma de saltarse auto_now_add.
                dias = azar.randint(0, dias_atras_max) if dias_atras_max else 0
                fecha_solicitud = hoy - timedelta(days=dias)
                Requerimiento.objects.filter(pk=requerimiento.pk).update(
                    fecha_solicitud=fecha_solicitud,
                    # La fecha requerida siempre cae después de la de solicitud.
                    fecha_requerida=fecha_solicitud + timedelta(days=azar.randint(5, 45)),
                )
                self._simular_atencion(requerimiento, fecha_solicitud, analista, hoy, azar)
                creados += 1

        self._resumen(creados)

    def _analista(self):
        """Cuenta de demostración que firma los cambios de estado (HU-31)."""
        usuario, nombre, apellido = ANALISTA_DEMO
        cuenta, _ = get_user_model().objects.get_or_create(
            username=f"{PREFIJO_DEMO}{usuario}",
            defaults={"first_name": nombre, "last_name": apellido},
        )
        return cuenta

    def _simular_atencion(self, requerimiento, fecha_solicitud, analista, hoy, azar):
        """Avanza el requerimiento por el flujo de compras con fechas creíbles (HU-31).

        Usa ``cambiar_estado``, así que respeta las transiciones permitidas y deja
        la bitácora igual que en la operación real. Nunca fecha un cambio en el
        futuro: si la siguiente etapa caería después de hoy, se queda donde va.
        """
        fecha = fecha_solicitud
        for estado, (minimo, maximo) in ETAPAS_ATENCION[: azar.choice(AVANCES_POSIBLES)]:
            fecha += timedelta(days=azar.randint(minimo, maximo))
            if fecha > hoy:
                return
            self._transicion(requerimiento, estado, analista, fecha)

    @staticmethod
    def _transicion(requerimiento, estado, usuario, fecha, observacion=""):
        """Hace el cambio de estado y lo fecha en el día simulado, a media mañana."""
        cambio = requerimiento.cambiar_estado(estado, usuario, observacion)
        # `fecha` es auto_now_add: igual que con la solicitud, se corrige con UPDATE.
        momento = timezone.make_aware(datetime.combine(fecha, time(10, 0)))
        CambioEstado.objects.filter(pk=cambio.pk).update(fecha=momento)

    def _agregar_items(self, requerimiento, unidades, azar):
        """Entre 1 y 4 ítems, algunos sin precio para que el total salga parcial."""
        for numero, (descripcion, unidad, precio) in enumerate(
            azar.sample(CATALOGO_ITEMS, azar.randint(1, 4)), start=1
        ):
            # Uno de cada cinco va sin precio: así el tablero y la confirmación
            # muestran el aviso de total parcial (HU-10), que es un caso real.
            sin_precio = azar.randint(1, 5) == 1
            Item.objects.create(
                requerimiento=requerimiento,
                numero=numero,
                cantidad=azar.randint(1, 20),
                unidad_medida=unidades[unidad],
                descripcion=descripcion,
                especificaciones_tecnicas=azar.choice(ESPECIFICACIONES),
                precio_referencia=None if sin_precio else precio,
                requiere_calibracion=azar.randint(1, 6) == 1,
                es_reembolsable=azar.randint(1, 8) == 1,
            )

    def _resumen(self, creados):
        self.stdout.write(self.style.SUCCESS(f"{creados} requerimientos de demostración creados."))

        demo = self._consulta_demo()
        self.stdout.write("")
        self.stdout.write("Reparto sembrado:")
        for etiqueta, campo in (
            ("Área", "area__nombre"),
            ("Prioridad", "prioridad__nombre"),
            ("Estado", "estado"),
        ):
            self.stdout.write(f"  Por {etiqueta.lower()}:")
            conteos = demo.values_list(campo).order_by(campo)
            vistos = {}
            for (valor,) in conteos:
                vistos[valor] = vistos.get(valor, 0) + 1
            for valor, total in sorted(vistos.items(), key=lambda par: -par[1]):
                self.stdout.write(f"    {valor}: {total}")

        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                "Son datos de demostración. Para quitarlos: manage.py sembrar_demo --limpiar"
            )
        )
