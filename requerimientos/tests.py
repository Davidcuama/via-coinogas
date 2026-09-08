import threading
from datetime import date, timedelta
from unittest import skipUnless

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from .forms import RequerimientoForm
from .models import Area, CentroCosto, Prioridad, Requerimiento, SecuenciaRadicacion


class RequerimientoModelTests(TestCase):
    """Cubre HU-02 (encabezado) y HU-05 (fecha requerida)."""

    def setUp(self):
        self.area = Area.objects.create(nombre="Mantenimiento")
        self.centro_costo = CentroCosto.objects.create(codigo="CC-100", nombre="Planta Medellín")
        self.prioridad = Prioridad.objects.create(nombre=Prioridad.MEDIA, orden=2)

    def _requerimiento(self, **overrides):
        datos = {
            "solicitante": "Juan Pérez",
            "area": self.area,
            "centro_costo": self.centro_costo,
            "justificacion": "Se requiere repuesto urgente para la línea 2.",
            "prioridad": self.prioridad,
            "fecha_requerida": date.today() + timedelta(days=5),
        }
        datos.update(overrides)
        return Requerimiento(**datos)

    # --- HU-02 ---
    def test_encabezado_se_guarda_correctamente(self):
        req = self._requerimiento()
        req.full_clean()
        req.save()
        self.assertEqual(req.solicitante, "Juan Pérez")
        self.assertEqual(req.area, self.area)
        self.assertEqual(req.centro_costo, self.centro_costo)

    def test_fecha_solicitud_se_asigna_automaticamente(self):
        req = self._requerimiento()
        req.save()
        self.assertEqual(req.fecha_solicitud, date.today())

    # --- HU-03 ---
    def test_justificacion_vacia_es_invalida(self):
        req = self._requerimiento(justificacion="   ")
        with self.assertRaises(ValidationError):
            req.full_clean()

    def test_justificacion_se_conserva_integra(self):
        texto = "Línea 1.\nLínea 2 con más detalle sobre la compra."
        req = self._requerimiento(justificacion=texto)
        req.full_clean()
        req.save()
        req.refresh_from_db()
        self.assertEqual(req.justificacion, texto)

    # --- HU-04 ---
    def test_prioridad_por_defecto_es_media(self):
        form = RequerimientoForm()
        self.assertEqual(form.fields["prioridad"].initial, self.prioridad.pk)

    def test_prioridad_se_conserva_al_consultar(self):
        req = self._requerimiento()
        req.full_clean()
        req.save()
        req.refresh_from_db()
        self.assertEqual(req.prioridad, self.prioridad)

    # --- HU-05 ---
    def test_fecha_requerida_no_puede_ser_anterior_a_solicitud(self):
        req = self._requerimiento(fecha_requerida=date.today() - timedelta(days=1))
        with self.assertRaises(ValidationError):
            req.full_clean()

    def test_fecha_requerida_futura_sin_limite_es_valida(self):
        req = self._requerimiento(fecha_requerida=date.today() + timedelta(days=365 * 3))
        req.full_clean()  # no debe lanzar excepción


class RequerimientoFormTests(TestCase):
    """Pruebas de formulario que refuerzan las validaciones de las 4 HUs."""

    def setUp(self):
        self.area = Area.objects.create(nombre="Compras")
        self.centro_costo = CentroCosto.objects.create(codigo="CC-200", nombre="Sede Bogotá")
        Prioridad.objects.create(nombre=Prioridad.ALTA, orden=1)
        Prioridad.objects.create(nombre=Prioridad.MEDIA, orden=2)
        Prioridad.objects.create(nombre=Prioridad.BAJA, orden=3)

    def _datos_validos(self, **overrides):
        prioridad = Prioridad.objects.get(nombre=Prioridad.ALTA)
        datos = {
            "solicitante": "Ana Gómez",
            "area": self.area.pk,
            "centro_costo": self.centro_costo.pk,
            "justificacion": "Reposición de insumos de oficina.",
            "prioridad": prioridad.pk,
            "fecha_requerida": date.today() + timedelta(days=10),
        }
        datos.update(overrides)
        return datos

    def test_formulario_valido_con_datos_correctos(self):
        form = RequerimientoForm(data=self._datos_validos())
        self.assertTrue(form.is_valid(), form.errors)

    def test_formulario_rechaza_justificacion_vacia(self):
        form = RequerimientoForm(data=self._datos_validos(justificacion=""))
        self.assertFalse(form.is_valid())
        self.assertIn("justificacion", form.errors)

    def test_formulario_rechaza_fecha_requerida_pasada(self):
        form = RequerimientoForm(
            data=self._datos_validos(fecha_requerida=date.today() - timedelta(days=1))
        )
        self.assertFalse(form.is_valid())
        self.assertIn("fecha_requerida", form.errors)

    def test_prioridad_es_obligatoria_y_de_lista_cerrada(self):
        form = RequerimientoForm(data=self._datos_validos(prioridad=""))
        self.assertFalse(form.is_valid())
        self.assertIn("prioridad", form.errors)

    def test_area_y_centro_costo_son_de_lista_cerrada(self):
        # Un id inexistente debe rechazarse: no se puede "escribir" libremente.
        form = RequerimientoForm(data=self._datos_validos(area=9999))
        self.assertFalse(form.is_valid())
        self.assertIn("area", form.errors)


class ConsecutivoRadicacionTests(TestCase):
    """HU-16: consecutivo único de radicación."""

    def setUp(self):
        self.area = Area.objects.create(nombre="Mantenimiento")
        self.centro_costo = CentroCosto.objects.create(codigo="CC-100", nombre="Planta Medellín")
        self.prioridad = Prioridad.objects.create(nombre=Prioridad.MEDIA, orden=2)

    def _crear(self):
        return Requerimiento.objects.create(
            solicitante="Juan Pérez",
            area=self.area,
            centro_costo=self.centro_costo,
            justificacion="Repuesto para la línea 2.",
            prioridad=self.prioridad,
            fecha_requerida=date.today() + timedelta(days=5),
        )

    def test_consecutivo_se_asigna_al_guardar_con_formato_definido(self):
        req = self._crear()
        anio = timezone.localdate().year
        self.assertEqual(req.consecutivo, f"REQ-{anio}-0001")

    def test_consecutivos_son_correlativos(self):
        primero, segundo, tercero = self._crear(), self._crear(), self._crear()
        anio = timezone.localdate().year
        self.assertEqual(
            [primero.consecutivo, segundo.consecutivo, tercero.consecutivo],
            [f"REQ-{anio}-0001", f"REQ-{anio}-0002", f"REQ-{anio}-0003"],
        )

    def test_consecutivo_no_cambia_al_editar(self):
        req = self._crear()
        original = req.consecutivo
        req.solicitante = "Otro nombre"
        req.save()
        req.refresh_from_db()
        self.assertEqual(req.consecutivo, original)

    def test_consecutivo_es_unico_en_base_de_datos(self):
        campo = Requerimiento._meta.get_field("consecutivo")
        self.assertTrue(campo.unique)
        self.assertFalse(campo.editable)

    def test_secuencia_reinicia_por_anio(self):
        with transaction.atomic():
            self.assertEqual(SecuenciaRadicacion.siguiente_consecutivo(2025), "REQ-2025-0001")
            self.assertEqual(SecuenciaRadicacion.siguiente_consecutivo(2025), "REQ-2025-0002")
            self.assertEqual(SecuenciaRadicacion.siguiente_consecutivo(2026), "REQ-2026-0001")

    def test_str_muestra_consecutivo(self):
        req = self._crear()
        self.assertIn(req.consecutivo, str(req))


@skipUnless(
    connection.vendor == "postgresql",
    "La prueba de concurrencia requiere bloqueo de filas (SELECT FOR UPDATE) de PostgreSQL.",
)
class ConsecutivoConcurrenciaTests(TransactionTestCase):
    """HU-16: dos envíos simultáneos nunca reciben el mismo número."""

    HILOS = 10

    def setUp(self):
        self.area = Area.objects.create(nombre="Operaciones")
        self.centro_costo = CentroCosto.objects.create(codigo="CC-300", nombre="Sede Cali")
        self.prioridad = Prioridad.objects.create(nombre=Prioridad.ALTA, orden=1)

    def test_radicaciones_simultaneas_reciben_consecutivos_distintos(self):
        resultados = []
        errores = []
        barrera = threading.Barrier(self.HILOS)

        def radicar():
            try:
                barrera.wait()  # todos los hilos arrancan al mismo tiempo
                req = Requerimiento.objects.create(
                    solicitante="Solicitante concurrente",
                    area=self.area,
                    centro_costo=self.centro_costo,
                    justificacion="Prueba de concurrencia.",
                    prioridad=self.prioridad,
                    fecha_requerida=date.today() + timedelta(days=3),
                )
                resultados.append(req.consecutivo)
            except Exception as exc:
                errores.append(exc)
            finally:
                connection.close()

        hilos = [threading.Thread(target=radicar) for _ in range(self.HILOS)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        self.assertEqual(errores, [])
        self.assertEqual(len(resultados), self.HILOS)
        self.assertEqual(len(set(resultados)), self.HILOS, "Se repitió un consecutivo")
        self.assertEqual(SecuenciaRadicacion.objects.get().ultimo_numero, self.HILOS)
