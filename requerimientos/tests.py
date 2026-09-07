from datetime import date

from django.test import TestCase

from .models import Area, CentroCosto, Requerimiento


class RequerimientoModelTests(TestCase):
    """HU-02: encabezado del requerimiento."""

    def setUp(self):
        self.area = Area.objects.create(nombre="Mantenimiento")
        self.centro_costo = CentroCosto.objects.create(codigo="CC-100", nombre="Planta Medellín")

    def test_encabezado_se_guarda_correctamente(self):
        req = Requerimiento.objects.create(
            solicitante="Juan Pérez", area=self.area, centro_costo=self.centro_costo,
        )
        self.assertEqual(req.solicitante, "Juan Pérez")
        self.assertEqual(req.area, self.area)
        self.assertEqual(req.centro_costo, self.centro_costo)

    def test_fecha_solicitud_se_asigna_automaticamente(self):
        req = Requerimiento.objects.create(
            solicitante="Juan Pérez", area=self.area, centro_costo=self.centro_costo,
        )
        self.assertEqual(req.fecha_solicitud, date.today())
