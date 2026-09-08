import smtplib
import threading
from datetime import date, timedelta
from decimal import Decimal
from unittest import mock, skipUnless

from django.conf import settings
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.db import connection, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import notificaciones
from .borradores import CLAVE_SESION as CLAVE_SESION_BORRADOR
from .forms import CAMPOS_OBLIGATORIOS, ItemForm, RequerimientoForm
from .models import (
    Area,
    CentroCosto,
    Item,
    Prioridad,
    Requerimiento,
    SecuenciaRadicacion,
    UnidadMedida,
)


def datos_items(*descripciones):
    """Datos POST del formset de ítems (HU-06, HU-07).

    Radicar exige al menos un ítem, así que toda prueba que envíe el formulario
    completo tiene que incluir esta parte además del encabezado. La unidad de
    medida se asegura aquí para que la prueba no tenga que sembrar el catálogo.
    """
    unidad, _ = UnidadMedida.objects.get_or_create(codigo="UND", defaults={"nombre": "Unidad"})
    descripciones = descripciones or ("Resma de papel carta",)
    datos = {
        "items-TOTAL_FORMS": str(len(descripciones)),
        "items-INITIAL_FORMS": "0",
        "items-MIN_NUM_FORMS": "1",
        "items-MAX_NUM_FORMS": "1000",
    }
    for indice, descripcion in enumerate(descripciones):
        datos[f"items-{indice}-cantidad"] = "1"
        datos[f"items-{indice}-unidad_medida"] = unidad.pk
        datos[f"items-{indice}-descripcion"] = descripcion
        datos[f"items-{indice}-id"] = ""
    return datos


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
            **datos_items(),
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
            **datos_items(),
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


class BorradorRequerimientoTests(TestCase):
    """HU-18: el solicitante guarda un borrador y lo retoma después."""

    def setUp(self):
        self.area = Area.objects.create(nombre="Mantenimiento")
        self.centro_costo = CentroCosto.objects.create(codigo="CC-100", nombre="Planta Medellín")
        self.prioridad = Prioridad.objects.create(nombre=Prioridad.MEDIA, orden=2)
        self.url_crear = reverse("requerimientos:crear")
        self.url_guardar = reverse("requerimientos:guardar_borrador")
        self.url_descartar = reverse("requerimientos:descartar_borrador")

    def _datos_parciales(self):
        # Lo que alcanzó a diligenciar antes de que lo interrumpieran: faltan el
        # centro de costo y la fecha requerida.
        return {
            "solicitante": "Ana Gómez",
            "area": str(self.area.pk),
            "centro_costo": "",
            "justificacion": "Reposición de insumos de oficina.",
            "prioridad": str(self.prioridad.pk),
            "fecha_requerida": "",
        }

    def _datos_completos(self):
        return {
            "solicitante": "Ana Gómez",
            "area": self.area.pk,
            "centro_costo": self.centro_costo.pk,
            "justificacion": "Reposición de insumos de oficina.",
            "prioridad": self.prioridad.pk,
            "fecha_requerida": (date.today() + timedelta(days=10)).isoformat(),
            **datos_items(),
        }

    def test_guardar_borrador_no_exige_los_campos_obligatorios(self):
        # HU-15 aplica al radicar, no al guardar: un borrador incompleto se acepta.
        respuesta = self.client.post(self.url_guardar, self._datos_parciales())
        self.assertRedirects(respuesta, self.url_crear)
        self.assertIn(CLAVE_SESION_BORRADOR, self.client.session)

    def test_guardar_borrador_no_crea_un_requerimiento(self):
        self.client.post(self.url_guardar, self._datos_parciales())
        self.assertEqual(Requerimiento.objects.count(), 0)
        self.assertEqual(SecuenciaRadicacion.objects.count(), 0)

    def test_el_borrador_conserva_lo_diligenciado(self):
        self.client.post(self.url_guardar, self._datos_parciales())
        respuesta = self.client.get(self.url_crear)
        formulario = respuesta.context["form"]
        self.assertEqual(formulario.initial["solicitante"], "Ana Gómez")
        self.assertEqual(formulario.initial["justificacion"], "Reposición de insumos de oficina.")
        self.assertEqual(formulario.initial["area"], str(self.area.pk))
        self.assertContains(respuesta, "Ana Gómez")

    def test_los_campos_que_faltaban_siguen_vacios_al_retomar(self):
        self.client.post(self.url_guardar, self._datos_parciales())
        formulario = self.client.get(self.url_crear).context["form"]
        self.assertNotIn("centro_costo", formulario.initial)
        self.assertNotIn("fecha_requerida", formulario.initial)

    def test_el_formulario_avisa_que_se_retomo_un_borrador(self):
        self.client.post(self.url_guardar, self._datos_parciales())
        respuesta = self.client.get(self.url_crear)
        self.assertIsNotNone(respuesta.context["borrador"])
        self.assertContains(respuesta, 'id="aviso-borrador"')

    def test_sin_borrador_el_formulario_abre_en_blanco_y_sin_aviso(self):
        respuesta = self.client.get(self.url_crear)
        self.assertIsNone(respuesta.context["borrador"])
        self.assertNotContains(respuesta, 'id="aviso-borrador"')
        self.assertNotIn("solicitante", respuesta.context["form"].initial)

    def test_formulario_en_blanco_no_guarda_borrador(self):
        vacios = dict.fromkeys(self._datos_parciales(), "")
        vacios["prioridad"] = str(self.prioridad.pk)  # el selector siempre trae la Media
        self.client.post(self.url_guardar, vacios)
        self.assertNotIn(CLAVE_SESION_BORRADOR, self.client.session)

    def test_guardar_de_nuevo_reemplaza_el_borrador_anterior(self):
        self.client.post(self.url_guardar, self._datos_parciales())
        datos = self._datos_parciales()
        datos["solicitante"] = "Carlos Ruiz"
        self.client.post(self.url_guardar, datos)
        formulario = self.client.get(self.url_crear).context["form"]
        self.assertEqual(formulario.initial["solicitante"], "Carlos Ruiz")

    def test_descartar_borrador_deja_el_formulario_en_blanco(self):
        self.client.post(self.url_guardar, self._datos_parciales())
        respuesta = self.client.post(self.url_descartar)
        self.assertRedirects(respuesta, self.url_crear)
        self.assertNotIn(CLAVE_SESION_BORRADOR, self.client.session)
        self.assertIsNone(self.client.get(self.url_crear).context["borrador"])

    def test_radicar_elimina_el_borrador(self):
        self.client.post(self.url_guardar, self._datos_parciales())
        self.client.post(self.url_crear, self._datos_completos())
        self.assertEqual(Requerimiento.objects.count(), 1)
        self.assertNotIn(CLAVE_SESION_BORRADOR, self.client.session)

    def test_un_envio_incompleto_no_borra_el_borrador_guardado(self):
        self.client.post(self.url_guardar, self._datos_parciales())
        respuesta = self.client.post(self.url_crear, self._datos_completos() | {"solicitante": ""})
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn(CLAVE_SESION_BORRADOR, self.client.session)

    def test_el_borrador_es_privado_de_cada_solicitante(self):
        self.client.post(self.url_guardar, self._datos_parciales())
        otro = Client()
        respuesta = otro.get(self.url_crear)
        self.assertIsNone(respuesta.context["borrador"])
        self.assertNotIn("solicitante", respuesta.context["form"].initial)

    def test_el_boton_de_borrador_no_dispara_la_validacion_del_navegador(self):
        respuesta = self.client.get(self.url_crear)
        self.assertContains(respuesta, f'formaction="{self.url_guardar}"')
        self.assertContains(respuesta, "formnovalidate")


@override_settings(COMPRAS_EMAILS=["compras@coinogas.com", "analista@coinogas.com"])
class NotificacionAreaComprasTests(TestCase):
    """HU-19: el área de compras recibe un correo cuando se radica un requerimiento."""

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
            **datos_items(),
        }

    def _radicar(self, datos=None):
        """Radica y ejecuta los avisos diferidos con `transaction.on_commit`."""
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self.url_crear, datos or self.datos)

    def test_radicar_envia_el_aviso_al_area_de_compras(self):
        self._radicar()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["compras@coinogas.com", "analista@coinogas.com"])

    def test_el_asunto_identifica_el_requerimiento_y_su_prioridad(self):
        self._radicar()
        requerimiento = Requerimiento.objects.get()
        self.assertIn(requerimiento.consecutivo, mail.outbox[0].subject)
        self.assertIn("Alta", mail.outbox[0].subject)

    def test_el_cuerpo_resume_el_requerimiento(self):
        self._radicar()
        requerimiento = Requerimiento.objects.get()
        cuerpo = mail.outbox[0].body
        self.assertIn(requerimiento.consecutivo, cuerpo)
        self.assertIn("Ana Gómez", cuerpo)
        self.assertIn("Mantenimiento", cuerpo)
        self.assertIn("CC-100", cuerpo)
        self.assertIn("Reposición de insumos de oficina.", cuerpo)
        self.assertIn(requerimiento.fecha_requerida.strftime("%d/%m/%Y"), cuerpo)

    def test_el_correo_lleva_version_html_ademas_de_texto_plano(self):
        self._radicar()
        alternativas = mail.outbox[0].alternatives
        self.assertEqual(len(alternativas), 1)
        contenido, tipo = alternativas[0].content, alternativas[0].mimetype
        self.assertEqual(tipo, "text/html")
        self.assertIn(Requerimiento.objects.get().consecutivo, contenido)

    def test_el_remitente_es_el_configurado(self):
        self._radicar()
        self.assertEqual(mail.outbox[0].from_email, settings.DEFAULT_FROM_EMAIL)

    def test_un_envio_incompleto_no_notifica(self):
        # HU-15 bloquea la radicación: no hay nada que avisar.
        respuesta = self._radicar(self.datos | {"solicitante": ""})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_cada_radicacion_genera_un_solo_aviso(self):
        self._radicar()
        self._radicar()
        self.assertEqual(Requerimiento.objects.count(), 2)
        self.assertEqual(len(mail.outbox), 2)

    @override_settings(COMPRAS_EMAILS=[])
    def test_sin_buzones_configurados_no_se_envia_pero_se_radica(self):
        with self.assertLogs("requerimientos.notificaciones", level="WARNING") as registro:
            self._radicar()
        self.assertEqual(Requerimiento.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 0)
        self.assertIn("COMPRAS_EMAILS", registro.output[0])

    def test_una_falla_del_servidor_de_correo_no_tumba_la_radicacion(self):
        # El requerimiento ya está guardado con su consecutivo: el solicitante
        # debe ver su confirmación aunque el SMTP esté caído.
        smtp_caido = mock.patch.object(
            EmailMultiAlternatives, "send", side_effect=smtplib.SMTPException("SMTP caído")
        )
        with smtp_caido, self.assertLogs("requerimientos.notificaciones", level="ERROR"):
            respuesta = self._radicar()

        requerimiento = Requerimiento.objects.get()
        self.assertRedirects(
            respuesta, reverse("requerimientos:confirmacion", args=[requerimiento.consecutivo])
        )

    def test_destinatarios_ignora_entradas_vacias(self):
        with override_settings(COMPRAS_EMAILS=["compras@coinogas.com", "  ", ""]):
            self.assertEqual(notificaciones.destinatarios(), ["compras@coinogas.com"])


class ItemTests(TestCase):
    """Cubre HU-06 (varios ítems por requerimiento)."""

    def setUp(self):
        self.area = Area.objects.create(nombre="Laboratorio")
        self.centro_costo = CentroCosto.objects.create(codigo="CC-300", nombre="Planta Rionegro")
        self.prioridad = Prioridad.objects.create(nombre=Prioridad.MEDIA, orden=2)
        self.unidad = UnidadMedida.objects.create(codigo="UND", nombre="Unidad")
        self.requerimiento = Requerimiento.objects.create(
            solicitante="Carlos Ruiz",
            area=self.area,
            centro_costo=self.centro_costo,
            justificacion="Calibración anual de equipos de medición.",
            prioridad=self.prioridad,
            fecha_requerida=date.today() + timedelta(days=15),
        )

    def _crear_items(self, cantidad):
        return [
            Item.objects.create(
                requerimiento=self.requerimiento,
                numero=numero,
                cantidad=numero,
                unidad_medida=self.unidad,
                descripcion=f"Ítem {numero}",
            )
            for numero in range(1, cantidad + 1)
        ]

    def test_un_requerimiento_guarda_varios_items(self):
        # Caso real de calibración: cuatro ítems en una sola solicitud.
        self._crear_items(4)
        self.requerimiento.refresh_from_db()
        self.assertEqual(self.requerimiento.items.count(), 4)
        self.assertEqual(
            list(self.requerimiento.items.values_list("descripcion", flat=True)),
            ["Ítem 1", "Ítem 2", "Ítem 3", "Ítem 4"],
        )

    def test_numeracion_se_corrige_al_eliminar_un_item_intermedio(self):
        self._crear_items(4)
        self.requerimiento.items.get(numero=2).delete()

        self.requerimiento.renumerar_items()

        self.assertEqual(
            list(self.requerimiento.items.values_list("numero", flat=True)),
            [1, 2, 3],
        )
        self.assertEqual(
            list(self.requerimiento.items.values_list("descripcion", flat=True)),
            ["Ítem 1", "Ítem 3", "Ítem 4"],
        )

    def test_los_items_se_borran_con_su_requerimiento(self):
        self._crear_items(2)
        self.requerimiento.delete()
        self.assertEqual(Item.objects.count(), 0)


class RequerimientoVistaTests(TestCase):
    """Cubre el envío completo del formulario: encabezado + ítems (HU-06)."""

    def setUp(self):
        self.area = Area.objects.create(nombre="Producción")
        self.centro_costo = CentroCosto.objects.create(codigo="CC-400", nombre="Sede Cali")
        self.prioridad = Prioridad.objects.create(nombre=Prioridad.ALTA, orden=1)
        self.unidad = UnidadMedida.objects.create(codigo="UND", nombre="Unidad")
        self.url = reverse("requerimientos:crear")

    def _datos(self, descripciones, **overrides):
        datos = {
            "solicitante": "Laura Restrepo",
            "area": self.area.pk,
            "centro_costo": self.centro_costo.pk,
            "justificacion": "Reposición de insumos de planta.",
            "prioridad": self.prioridad.pk,
            "fecha_requerida": date.today() + timedelta(days=7),
            "items-TOTAL_FORMS": str(len(descripciones)),
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "1",
            "items-MAX_NUM_FORMS": "1000",
        }
        for indice, descripcion in enumerate(descripciones):
            datos[f"items-{indice}-cantidad"] = "1" if descripcion else ""
            datos[f"items-{indice}-unidad_medida"] = self.unidad.pk if descripcion else ""
            datos[f"items-{indice}-descripcion"] = descripcion
            datos[f"items-{indice}-id"] = ""
        datos.update(overrides)
        return datos

    def test_formulario_en_blanco_responde_con_el_formset(self):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("items", respuesta.context)

    def test_radicar_con_varios_items_los_guarda_numerados(self):
        descripciones = ["Manómetro", "Termómetro", "Cronómetro", "Balanza"]
        respuesta = self.client.post(self.url, self._datos(descripciones))

        self.assertEqual(respuesta.status_code, 302)
        requerimiento = Requerimiento.objects.get()
        self.assertEqual(
            list(requerimiento.items.values_list("numero", "descripcion")),
            [(1, "Manómetro"), (2, "Termómetro"), (3, "Cronómetro"), (4, "Balanza")],
        )

    def test_radicar_sin_ningun_item_es_rechazado(self):
        datos = self._datos([""])
        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Requerimiento.objects.count(), 0)
        self.assertTrue(respuesta.context["items"].non_form_errors())

    def test_encabezado_invalido_no_guarda_los_items(self):
        datos = self._datos(["Manómetro"], justificacion="")
        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Requerimiento.objects.count(), 0)
        self.assertEqual(Item.objects.count(), 0)

    def test_una_fila_en_blanco_no_crea_un_item(self):
        """La fila que el usuario agrega y deja vacía se ignora, no da error."""
        datos = self._datos(["Válvula de bola 2 pulgadas", ""])
        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Item.objects.count(), 1)


class ItemDatosBasicosTests(TestCase):
    """Cubre HU-07 (cantidad, unidad de medida y descripción del ítem)."""

    def setUp(self):
        self.area = Area.objects.create(nombre="Metrología")
        self.centro_costo = CentroCosto.objects.create(codigo="CC-500", nombre="Sede Itagüí")
        self.prioridad = Prioridad.objects.create(nombre=Prioridad.BAJA, orden=3)
        self.unidad = UnidadMedida.objects.create(codigo="UND", nombre="Unidad")
        self.requerimiento = Requerimiento.objects.create(
            solicitante="Marta Alzate",
            area=self.area,
            centro_costo=self.centro_costo,
            justificacion="Compra de instrumentos.",
            prioridad=self.prioridad,
            fecha_requerida=date.today() + timedelta(days=20),
        )

    def _item(self, **overrides):
        datos = {
            "requerimiento": self.requerimiento,
            "numero": 1,
            "cantidad": 3,
            "unidad_medida": self.unidad,
            "descripcion": "Manómetro de glicerina 0-100 psi",
        }
        datos.update(overrides)
        return Item(**datos)

    def test_cantidad_cero_es_invalida(self):
        with self.assertRaises(ValidationError):
            self._item(cantidad=0).full_clean()

    def test_cantidad_negativa_es_invalida(self):
        with self.assertRaises(ValidationError):
            self._item(cantidad=-2).full_clean()

    def test_cantidad_positiva_es_valida(self):
        self._item(cantidad=1).full_clean()  # no debe lanzar excepción

    def test_descripcion_vacia_es_invalida(self):
        with self.assertRaises(ValidationError):
            self._item(descripcion="   ").full_clean()

    def test_descripcion_larga_y_multilinea_no_se_trunca(self):
        texto = ("Manómetro de glicerina.\nRango 0-100 psi, rosca 1/4 NPT inferior.\n") * 20
        item = self._item(descripcion=texto)
        item.full_clean()
        item.save()
        item.refresh_from_db()
        self.assertEqual(item.descripcion, texto)

    def test_unidad_de_medida_es_obligatoria(self):
        with self.assertRaises(ValidationError):
            self._item(unidad_medida=None).full_clean()

    def test_unidad_de_medida_se_conserva_al_consultar(self):
        item = self._item()
        item.full_clean()
        item.save()
        item.refresh_from_db()
        self.assertEqual(item.unidad_medida, self.unidad)

    # --- Formulario ---
    def test_formulario_de_item_propone_unidad_por_defecto(self):
        form = ItemForm()
        self.assertEqual(form.fields["unidad_medida"].initial, self.unidad.pk)

    def test_formulario_de_item_rechaza_cantidad_cero(self):
        form = ItemForm(
            data={
                "cantidad": 0,
                "unidad_medida": self.unidad.pk,
                "descripcion": "Termómetro digital",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("cantidad", form.errors)

    def test_formulario_de_item_exige_los_tres_campos(self):
        form = ItemForm(data={"cantidad": "", "unidad_medida": "", "descripcion": ""})
        self.assertFalse(form.is_valid())
        for campo in ("cantidad", "unidad_medida", "descripcion"):
            self.assertIn(campo, form.errors)


class ItemMarcasTests(TestCase):
    """Cubre HU-08 (marcas de calibración y de reembolsable)."""

    def setUp(self):
        self.area = Area.objects.create(nombre="Instrumentación")
        self.centro_costo = CentroCosto.objects.create(codigo="CC-600", nombre="Sede Envigado")
        self.prioridad = Prioridad.objects.create(nombre=Prioridad.ALTA, orden=1)
        self.unidad = UnidadMedida.objects.create(codigo="UND", nombre="Unidad")
        self.url = reverse("requerimientos:crear")
        self.requerimiento = Requerimiento.objects.create(
            solicitante="Diego Marín",
            area=self.area,
            centro_costo=self.centro_costo,
            justificacion="Calibración anual.",
            prioridad=self.prioridad,
            fecha_requerida=date.today() + timedelta(days=12),
        )

    def _item(self, **overrides):
        datos = {
            "requerimiento": self.requerimiento,
            "numero": 1,
            "cantidad": 1,
            "unidad_medida": self.unidad,
            "descripcion": "Patrón de presión",
        }
        datos.update(overrides)
        return Item.objects.create(**datos)

    def test_las_marcas_van_apagadas_por_defecto(self):
        item = self._item()
        item.refresh_from_db()
        self.assertFalse(item.requiere_calibracion)
        self.assertFalse(item.es_reembolsable)

    def test_las_marcas_se_guardan_y_se_recuperan(self):
        item = self._item(requiere_calibracion=True, es_reembolsable=True)
        item.refresh_from_db()
        self.assertTrue(item.requiere_calibracion)
        self.assertTrue(item.es_reembolsable)

    def test_las_marcas_son_independientes_entre_si(self):
        item = self._item(requiere_calibracion=True)
        item.refresh_from_db()
        self.assertTrue(item.requiere_calibracion)
        self.assertFalse(item.es_reembolsable)

    def test_las_marcas_se_registran_desde_el_formulario(self):
        datos = {
            "solicitante": "Diego Marín",
            "area": self.area.pk,
            "centro_costo": self.centro_costo.pk,
            "justificacion": "Calibración anual de patrones.",
            "prioridad": self.prioridad.pk,
            "fecha_requerida": date.today() + timedelta(days=12),
            "items-TOTAL_FORMS": "2",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "1",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-cantidad": "1",
            "items-0-unidad_medida": self.unidad.pk,
            "items-0-descripcion": "Patrón de presión",
            "items-0-requiere_calibracion": "on",
            "items-0-id": "",
            "items-1-cantidad": "2",
            "items-1-unidad_medida": self.unidad.pk,
            "items-1-descripcion": "Tiquetes de transporte",
            "items-1-es_reembolsable": "on",
            "items-1-id": "",
        }
        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 302)
        nuevo = Requerimiento.objects.exclude(pk=self.requerimiento.pk).get()
        primero, segundo = nuevo.items.all()
        self.assertTrue(primero.requiere_calibracion)
        self.assertFalse(primero.es_reembolsable)
        self.assertFalse(segundo.requiere_calibracion)
        self.assertTrue(segundo.es_reembolsable)


class ItemEspecificacionesTests(TestCase):
    """Cubre HU-09 (especificaciones técnicas del ítem)."""

    FICHA = (
        'Manómetro de glicerina, diámetro 4".\n'
        "Rango 0-100 psi, precisión ±1,6 %.\n"
        'Conexión 1/4" NPT inferior, caja en acero inoxidable 304.\n'
        "Debe cumplir la norma EN 837-1."
    )

    def setUp(self):
        self.area = Area.objects.create(nombre="Mantenimiento eléctrico")
        self.centro_costo = CentroCosto.objects.create(codigo="CC-700", nombre="Sede Bello")
        self.prioridad = Prioridad.objects.create(nombre=Prioridad.MEDIA, orden=2)
        self.unidad = UnidadMedida.objects.create(codigo="UND", nombre="Unidad")
        self.url = reverse("requerimientos:crear")
        self.requerimiento = Requerimiento.objects.create(
            solicitante="Sara Ochoa",
            area=self.area,
            centro_costo=self.centro_costo,
            justificacion="Reposición de instrumentación.",
            prioridad=self.prioridad,
            fecha_requerida=date.today() + timedelta(days=25),
        )

    def _item(self, **overrides):
        datos = {
            "requerimiento": self.requerimiento,
            "numero": 1,
            "cantidad": 1,
            "unidad_medida": self.unidad,
            "descripcion": "Manómetro",
        }
        datos.update(overrides)
        return Item(**datos)

    def test_especificaciones_largas_se_guardan_integras(self):
        item = self._item(especificaciones_tecnicas=self.FICHA)
        item.full_clean()
        item.save()
        item.refresh_from_db()
        self.assertEqual(item.especificaciones_tecnicas, self.FICHA)

    def test_especificaciones_son_opcionales(self):
        item = self._item()
        item.full_clean()  # no debe lanzar excepción
        item.save()
        self.assertEqual(item.especificaciones_tecnicas, "")

    def test_especificaciones_con_solo_espacios_quedan_vacias(self):
        item = self._item(especificaciones_tecnicas="   \n  ")
        item.full_clean()
        item.save()
        item.refresh_from_db()
        self.assertEqual(item.especificaciones_tecnicas, "")

    def _datos_formulario(self, **overrides):
        datos = {
            "solicitante": "Sara Ochoa",
            "area": self.area.pk,
            "centro_costo": self.centro_costo.pk,
            "justificacion": "Reposición de instrumentación.",
            "prioridad": self.prioridad.pk,
            "fecha_requerida": date.today() + timedelta(days=25),
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "1",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-cantidad": "2",
            "items-0-unidad_medida": self.unidad.pk,
            "items-0-descripcion": "Manómetro",
            "items-0-especificaciones_tecnicas": self.FICHA,
            "items-0-id": "",
        }
        datos.update(overrides)
        return datos

    def test_especificaciones_viajan_desde_el_formulario(self):
        respuesta = self.client.post(self.url, self._datos_formulario())

        self.assertEqual(respuesta.status_code, 302)
        nuevo = Requerimiento.objects.exclude(pk=self.requerimiento.pk).get()
        self.assertEqual(nuevo.items.get().especificaciones_tecnicas, self.FICHA)

    def test_una_fila_con_solo_especificaciones_no_se_descarta_en_silencio(self):
        datos = self._datos_formulario(
            **{
                "items-0-cantidad": "",
                "items-0-descripcion": "",
            }
        )
        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Item.objects.count(), 0)
        self.assertIn("descripcion", respuesta.context["items"].forms[0].errors)


class TotalesTests(TestCase):
    """Cubre HU-10 (cálculo automático de totales)."""

    def setUp(self):
        self.area = Area.objects.create(nombre="Compras técnicas")
        self.centro_costo = CentroCosto.objects.create(codigo="CC-800", nombre="Sede Sabaneta")
        self.prioridad = Prioridad.objects.create(nombre=Prioridad.MEDIA, orden=2)
        self.unidad = UnidadMedida.objects.create(codigo="UND", nombre="Unidad")
        self.url = reverse("requerimientos:crear")
        self.requerimiento = Requerimiento.objects.create(
            solicitante="Andrés Vélez",
            area=self.area,
            centro_costo=self.centro_costo,
            justificacion="Compra de repuestos.",
            prioridad=self.prioridad,
            fecha_requerida=date.today() + timedelta(days=30),
        )

    def _item(self, numero=1, **overrides):
        datos = {
            "requerimiento": self.requerimiento,
            "numero": numero,
            "cantidad": 2,
            "unidad_medida": self.unidad,
            "descripcion": f"Repuesto {numero}",
            "precio_referencia": Decimal("1500.00"),
        }
        datos.update(overrides)
        return Item.objects.create(**datos)

    def test_total_del_item_es_cantidad_por_precio(self):
        item = self._item(cantidad=3, precio_referencia=Decimal("12500.50"))
        item.refresh_from_db()
        self.assertEqual(item.total, Decimal("37501.50"))

    def test_total_del_item_se_recalcula_al_editarlo(self):
        item = self._item(cantidad=2, precio_referencia=Decimal("1000.00"))
        item.cantidad = 5
        item.save()
        item.refresh_from_db()
        self.assertEqual(item.total, Decimal("5000.00"))

    def test_item_sin_precio_aporta_cero(self):
        item = self._item(precio_referencia=None)
        item.refresh_from_db()
        self.assertEqual(item.total, Decimal("0.00"))

    def test_precio_negativo_es_invalido(self):
        item = Item(
            requerimiento=self.requerimiento,
            numero=1,
            cantidad=1,
            unidad_medida=self.unidad,
            descripcion="Repuesto",
            precio_referencia=Decimal("-1.00"),
        )
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_total_del_requerimiento_suma_sus_items(self):
        self._item(numero=1, cantidad=2, precio_referencia=Decimal("1500.00"))
        self._item(numero=2, cantidad=1, precio_referencia=Decimal("300.25"))
        self._item(numero=3, cantidad=4, precio_referencia=Decimal("10.00"))
        self.assertEqual(self.requerimiento.total_estimado, Decimal("3340.25"))

    def test_total_del_requerimiento_sin_items_es_cero(self):
        self.assertEqual(self.requerimiento.total_estimado, Decimal("0.00"))

    def test_total_del_requerimiento_se_ajusta_al_eliminar_un_item(self):
        self._item(numero=1, cantidad=1, precio_referencia=Decimal("100.00"))
        segundo = self._item(numero=2, cantidad=1, precio_referencia=Decimal("400.00"))
        segundo.delete()
        self.assertEqual(self.requerimiento.total_estimado, Decimal("100.00"))

    def test_requerimiento_avisa_si_algun_item_no_tiene_precio(self):
        self._item(numero=1, precio_referencia=Decimal("100.00"))
        self.assertFalse(self.requerimiento.tiene_items_sin_precio)
        self._item(numero=2, precio_referencia=None)
        self.assertTrue(self.requerimiento.tiene_items_sin_precio)

    def test_totales_se_calculan_al_radicar_desde_el_formulario(self):
        datos = {
            "solicitante": "Andrés Vélez",
            "area": self.area.pk,
            "centro_costo": self.centro_costo.pk,
            "justificacion": "Compra de repuestos.",
            "prioridad": self.prioridad.pk,
            "fecha_requerida": date.today() + timedelta(days=30),
            "items-TOTAL_FORMS": "2",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "1",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-cantidad": "3",
            "items-0-unidad_medida": self.unidad.pk,
            "items-0-descripcion": "Empaque",
            "items-0-precio_referencia": "2500",
            "items-0-id": "",
            "items-1-cantidad": "2",
            "items-1-unidad_medida": self.unidad.pk,
            "items-1-descripcion": "Sello mecánico",
            "items-1-precio_referencia": "40000.75",
            "items-1-id": "",
        }
        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 302)
        nuevo = Requerimiento.objects.exclude(pk=self.requerimiento.pk).get()
        self.assertEqual(
            list(nuevo.items.values_list("total", flat=True)),
            [Decimal("7500.00"), Decimal("80001.50")],
        )
        self.assertEqual(nuevo.total_estimado, Decimal("87501.50"))
