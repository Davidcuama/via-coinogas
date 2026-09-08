import threading
from datetime import date, timedelta
from unittest import skipUnless

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from .forms import CAMPOS_OBLIGATORIOS, RequerimientoForm
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


class ValidacionCamposObligatoriosTests(TestCase):
    """HU-15: el sistema impide radicar un requerimiento incompleto y señala qué falta."""

    def setUp(self):
        self.area = Area.objects.create(nombre="Mantenimiento")
        self.centro_costo = CentroCosto.objects.create(codigo="CC-100", nombre="Planta Medellín")
        self.prioridad = Prioridad.objects.create(nombre=Prioridad.MEDIA, orden=2)
        self.url = reverse("requerimientos:crear")

    def _datos_validos(self, **overrides):
        datos = {
            "solicitante": "Ana Gómez",
            "area": self.area.pk,
            "centro_costo": self.centro_costo.pk,
            "justificacion": "Reposición de insumos de oficina.",
            "prioridad": self.prioridad.pk,
            "fecha_requerida": (date.today() + timedelta(days=10)).isoformat(),
        }
        datos.update(overrides)
        return datos

    def test_todos_los_campos_del_formato_son_obligatorios(self):
        form = RequerimientoForm()
        for nombre in CAMPOS_OBLIGATORIOS:
            with self.subTest(campo=nombre):
                self.assertTrue(form.fields[nombre].required)

    def test_cada_campo_vacio_por_separado_bloquea_el_envio(self):
        # Se prueba el envío con cada campo obligatorio vacío, uno a la vez.
        for nombre in CAMPOS_OBLIGATORIOS:
            with self.subTest(campo=nombre):
                respuesta = self.client.post(self.url, self._datos_validos(**{nombre: ""}))
                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(Requerimiento.objects.count(), 0)
                self.assertEqual(list(respuesta.context["form"].errors), [nombre])

    def test_campo_solo_con_espacios_se_considera_vacio(self):
        respuesta = self.client.post(self.url, self._datos_validos(solicitante="   "))
        self.assertEqual(Requerimiento.objects.count(), 0)
        self.assertIn("solicitante", respuesta.context["form"].errors)

    def test_campo_faltante_se_resalta_y_muestra_que_se_espera(self):
        respuesta = self.client.post(self.url, self._datos_validos(justificacion=""))
        form = respuesta.context["form"]
        self.assertIn("is-invalid", form.fields["justificacion"].widget.attrs["class"])
        self.assertEqual(form.errors["justificacion"], ["Este campo es obligatorio."])
        self.assertContains(respuesta, 'id="resumen-errores"')
        self.assertContains(respuesta, "Justificación")

    def test_campo_de_lista_vacio_pide_seleccionar_una_opcion(self):
        respuesta = self.client.post(self.url, self._datos_validos(area=""))
        self.assertEqual(
            respuesta.context["form"].errors["area"], ["Selecciona una opción de la lista."]
        )

    def test_informacion_diligenciada_se_conserva_cuando_falla_la_validacion(self):
        respuesta = self.client.post(self.url, self._datos_validos(fecha_requerida=""))
        self.assertContains(respuesta, 'value="Ana Gómez"')
        self.assertContains(respuesta, "Reposición de insumos de oficina.")
        self.assertContains(respuesta, f'<option value="{self.area.pk}" selected>')

    def test_validacion_aplica_a_peticiones_directas_sin_navegador(self):
        # El cliente de pruebas envía el POST sin pasar por el formulario HTML,
        # equivalente a omitir la validación del navegador.
        respuesta = self.client.post(self.url, {})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Requerimiento.objects.count(), 0)
        self.assertEqual(set(respuesta.context["form"].errors), set(CAMPOS_OBLIGATORIOS))

    def test_formulario_en_blanco_marca_los_campos_como_required_en_html(self):
        respuesta = self.client.get(self.url)
        for nombre in CAMPOS_OBLIGATORIOS:
            with self.subTest(campo=nombre):
                self.assertRegex(respuesta.content.decode(), rf'name="{nombre}"[^>]*\brequired\b')

    def test_envio_completo_crea_el_requerimiento(self):
        respuesta = self.client.post(self.url, self._datos_validos())
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Requerimiento.objects.count(), 1)


class ConfirmacionRadicacionTests(TestCase):
    """HU-17: confirmación de radicación en pantalla."""

    def setUp(self):
        self.area = Area.objects.create(nombre="Mantenimiento")
        self.centro_costo = CentroCosto.objects.create(codigo="CC-100", nombre="Planta Medellín")
        self.prioridad = Prioridad.objects.create(nombre=Prioridad.ALTA, orden=1)
        self.url_crear = reverse("requerimientos:crear")
        self.datos = {
            "solicitante": "Ana Gómez",
            "area": self.area.pk,
            "centro_costo": self.centro_costo.pk,
            "justificacion": "Reposición de insumos de oficina.",
            "prioridad": self.prioridad.pk,
            "fecha_requerida": (date.today() + timedelta(days=10)).isoformat(),
        }

    def test_envio_exitoso_redirige_a_la_confirmacion(self):
        respuesta = self.client.post(self.url_crear, self.datos)
        req = Requerimiento.objects.get()
        self.assertRedirects(
            respuesta, reverse("requerimientos:confirmacion", args=[req.consecutivo])
        )

    def test_confirmacion_muestra_el_consecutivo_destacado(self):
        respuesta = self.client.post(self.url_crear, self.datos, follow=True)
        req = Requerimiento.objects.get()
        self.assertContains(respuesta, f'id="consecutivo">{req.consecutivo}<')

    def test_confirmacion_resume_el_requerimiento(self):
        respuesta = self.client.post(self.url_crear, self.datos, follow=True)
        req = Requerimiento.objects.get()
        self.assertContains(respuesta, "Ana Gómez")
        self.assertContains(respuesta, "Mantenimiento")
        self.assertContains(respuesta, "CC-100")
        self.assertContains(respuesta, "Alta")
        self.assertContains(respuesta, req.fecha_requerida.strftime("%d/%m/%Y"))

    def test_recargar_la_confirmacion_no_duplica_el_requerimiento(self):
        respuesta = self.client.post(self.url_crear, self.datos)
        url_confirmacion = respuesta["Location"]
        for _ in range(3):
            self.client.get(url_confirmacion)
        self.assertEqual(Requerimiento.objects.count(), 1)

    def test_confirmacion_ofrece_radicar_uno_nuevo(self):
        respuesta = self.client.post(self.url_crear, self.datos, follow=True)
        self.assertContains(respuesta, f'href="{self.url_crear}"')

    def test_consecutivo_inexistente_devuelve_404(self):
        respuesta = self.client.get(reverse("requerimientos:confirmacion", args=["REQ-2026-9999"]))
        self.assertEqual(respuesta.status_code, 404)
