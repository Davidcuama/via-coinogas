from datetime import date

from django.test import TestCase

from .models import Area, CentroCosto, Prioridad, Requerimiento


class RequerimientoModelTests(TestCase):
    """HU-02: encabezado del requerimiento."""

    def setUp(self):
        self.area = Area.objects.create(nombre="Mantenimiento")
        self.centro_costo = CentroCosto.objects.create(codigo="CC-100", nombre="Planta Medellín")
        # A partir de HU-04 la prioridad es obligatoria; se crea "Media" para
        # que el default del modelo pueda resolverse en estas pruebas.
        Prioridad.objects.create(nombre=Prioridad.MEDIA, orden=2)

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
        Prioridad.objects.create(nombre=Prioridad.MEDIA, orden=2)

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


class RequerimientoPrioridadTests(TestCase):
    """HU-04: prioridad de la compra."""

    def setUp(self):
        self.area = Area.objects.create(nombre="Compras")
        self.centro_costo = CentroCosto.objects.create(codigo="CC-300", nombre="Sede Cali")
        self.media = Prioridad.objects.create(nombre=Prioridad.MEDIA, orden=2)
        Prioridad.objects.create(nombre=Prioridad.ALTA, orden=1)
        Prioridad.objects.create(nombre=Prioridad.BAJA, orden=3)

    def test_prioridad_por_defecto_es_media(self):
        from .forms import RequerimientoForm
        form = RequerimientoForm()
        self.assertEqual(form.fields["prioridad"].initial, self.media.pk)

    def test_prioridad_se_conserva_al_consultar(self):
        req = Requerimiento.objects.create(
            solicitante="Luis Ríos", area=self.area, centro_costo=self.centro_costo,
            justificacion="Compra de papelería.", prioridad=self.media,
        )
        req.refresh_from_db()
        self.assertEqual(req.prioridad, self.media)
