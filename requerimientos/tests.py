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


class RequerimientoJustificacionTests(TestCase):
    """HU-03: justificación del requerimiento."""

    def setUp(self):
        self.area = Area.objects.create(nombre="Compras")
        self.centro_costo = CentroCosto.objects.create(codigo="CC-200", nombre="Sede Bogotá")

    def test_justificacion_vacia_es_invalida(self):
        from django.core.exceptions import ValidationError
        req = Requerimiento(
            solicitante="Ana Gómez", area=self.area, centro_costo=self.centro_costo,
            justificacion="   ",
        )
        with self.assertRaises(ValidationError):
            req.full_clean()

    def test_justificacion_se_conserva_integra(self):
        texto = "Línea 1.\nLínea 2 con más detalle sobre la compra."
        req = Requerimiento.objects.create(
            solicitante="Ana Gómez", area=self.area, centro_costo=self.centro_costo,
            justificacion=texto,
        )
        req.refresh_from_db()
        self.assertEqual(req.justificacion, texto)
