from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase

from .forms import RequerimientoForm
from .models import Area, CentroCosto, Prioridad, Requerimiento


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
