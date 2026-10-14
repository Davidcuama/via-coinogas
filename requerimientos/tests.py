import csv
import shutil
import smtplib
import tempfile
import threading
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest import mock, skipUnless

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import notificaciones, perfiles
from .borradores import CLAVE_SESION as CLAVE_SESION_BORRADOR
from .forms import CAMPOS_OBLIGATORIOS, ItemForm, RequerimientoForm
from .models import (
    Adjunto,
    Area,
    CambioEstado,
    CentroCosto,
    EstadoRequerimiento,
    Item,
    Prioridad,
    ProveedorSugerido,
    Requerimiento,
    SecuenciaRadicacion,
    UnidadMedida,
    ruta_adjunto,
)


def crear_usuario(usuario="ana.gomez", nombre="Ana", apellido="Gómez", perfil=None, clave=None):
    """Cuenta de prueba, opcionalmente con un perfil asignado.

    Sin `clave` la cuenta queda sin contraseña utilizable: basta para
    `force_login` y evita el costo de cifrarla, que multiplicaba por veinte la
    duración de la suite. Solo las pruebas del ingreso piden una de verdad.
    """
    cuenta = get_user_model().objects.create_user(
        username=usuario, password=clave, first_name=nombre, last_name=apellido
    )
    if perfil:
        grupos = {g.name: g for g in perfiles.asegurar_grupos()}
        cuenta.groups.add(grupos[perfil])
    return cuenta


class VistaTestCase(TestCase):
    """Base de las pruebas que golpean vistas.

    Desde que el sistema exige cuenta, ninguna pantalla responde a un anónimo,
    así que estas pruebas entran con una sesión antes de cada caso.
    """

    perfil_de_prueba = perfiles.SOLICITANTE

    def setUp(self):
        super().setUp()
        self.usuario = crear_usuario(perfil=self.perfil_de_prueba)
        self.client.force_login(self.usuario)


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


class ValidacionCamposObligatoriosTests(VistaTestCase):
    """HU-15: el sistema impide radicar un requerimiento incompleto y señala qué falta."""

    def setUp(self):
        super().setUp()
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


class ConfirmacionRadicacionTests(VistaTestCase):
    """HU-17: confirmación de radicación en pantalla."""

    def setUp(self):
        super().setUp()
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

    def test_confirmacion_resume_el_numero_de_items_radicados(self):
        datos = self.datos | datos_items("Resma de papel carta", "Tóner negro", "Caja de esferos")
        respuesta = self.client.post(self.url_crear, datos, follow=True)
        self.assertEqual(Requerimiento.objects.get().items.count(), 3)
        self.assertContains(respuesta, 'id="numero-items">3<')

    def test_confirmacion_lista_los_items_radicados(self):
        datos = self.datos | datos_items("Resma de papel carta", "Tóner negro")
        respuesta = self.client.post(self.url_crear, datos, follow=True)
        self.assertContains(respuesta, "Resma de papel carta")
        self.assertContains(respuesta, "Tóner negro")

    def test_confirmacion_muestra_el_total_estimado(self):
        datos = self.datos | datos_items("Resma de papel carta")
        datos["items-0-cantidad"] = "4"
        datos["items-0-precio_referencia"] = "25000"
        respuesta = self.client.post(self.url_crear, datos, follow=True)
        self.assertEqual(Requerimiento.objects.get().total_estimado, Decimal("100000.00"))
        # El proyecto corre en es-co: separador decimal de coma (ver settings).
        self.assertContains(respuesta, 'id="total-estimado">100000,00<')

    def test_confirmacion_advierte_cuando_el_total_es_parcial(self):
        # Sin precio de referencia el total sigue siendo valido, pero incompleto.
        respuesta = self.client.post(self.url_crear, self.datos, follow=True)
        self.assertContains(respuesta, 'id="aviso-total-parcial"')

    def test_confirmacion_no_advierte_si_todos_los_items_tienen_precio(self):
        datos = self.datos | datos_items("Resma de papel carta")
        datos["items-0-precio_referencia"] = "25000"
        respuesta = self.client.post(self.url_crear, datos, follow=True)
        self.assertNotContains(respuesta, 'id="aviso-total-parcial"')


class BorradorRequerimientoTests(VistaTestCase):
    """HU-18: el solicitante guarda un borrador y lo retoma después."""

    def setUp(self):
        super().setUp()
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
        # El unico valor precargado es el nombre de quien esta en sesion; no
        # arrastra nada de un requerimiento anterior (HU-01).
        self.assertEqual(respuesta.context["form"].initial["solicitante"], "Ana Gómez")
        self.assertNotIn("justificacion", respuesta.context["form"].initial)

    def test_formulario_en_blanco_no_guarda_borrador(self):
        vacios = dict.fromkeys(self._datos_parciales(), "")
        vacios["prioridad"] = str(self.prioridad.pk)  # el selector siempre trae la Media
        # La fila de item obligatoria viaja vacia, salvo la unidad preseleccionada.
        vacios.update(datos_items(""))
        vacios["items-0-cantidad"] = ""
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

        otra_cuenta = crear_usuario("luis.mesa", "Luis", "Mesa")
        otro = Client()
        otro.force_login(otra_cuenta)
        respuesta = otro.get(self.url_crear)

        self.assertIsNone(respuesta.context["borrador"])
        # Ve su propio nombre, nunca lo que escribio el otro solicitante.
        self.assertEqual(respuesta.context["form"].initial["solicitante"], "Luis Mesa")

    def test_el_boton_de_borrador_no_dispara_la_validacion_del_navegador(self):
        respuesta = self.client.get(self.url_crear)
        self.assertContains(respuesta, f'formaction="{self.url_guardar}"')
        self.assertContains(respuesta, "formnovalidate")

    # --- HU-18 + HU-06: el borrador tambien conserva la tabla de items ---

    def _datos_parciales_con_items(self, *descripciones):
        return self._datos_parciales() | datos_items(*descripciones)

    def test_el_borrador_conserva_los_items(self):
        self.client.post(
            self.url_guardar,
            self._datos_parciales_con_items("Resma de papel carta", "Toner negro"),
        )
        formset = self.client.get(self.url_crear).context["items"]
        self.assertEqual(len(formset.forms), 2)
        self.assertEqual(
            [f.initial["descripcion"] for f in formset.forms],
            ["Resma de papel carta", "Toner negro"],
        )

    def test_los_items_del_borrador_se_pintan_en_el_formulario(self):
        self.client.post(self.url_guardar, self._datos_parciales_con_items("Toner negro"))
        respuesta = self.client.get(self.url_crear)
        self.assertContains(respuesta, "Toner negro")

    def test_el_borrador_conserva_las_marcas_del_item(self):
        datos = self._datos_parciales_con_items("Manometro de linea")
        datos["items-0-requiere_calibracion"] = "on"
        datos["items-0-especificaciones_tecnicas"] = "Rango 0-100 psi, norma ISO 5171."
        self.client.post(self.url_guardar, datos)
        fila = self.client.get(self.url_crear).context["items"].forms[0].initial
        self.assertTrue(fila["requiere_calibracion"])
        self.assertFalse(fila["es_reembolsable"])
        self.assertEqual(fila["especificaciones_tecnicas"], "Rango 0-100 psi, norma ISO 5171.")

    def test_las_filas_en_blanco_no_entran_al_borrador(self):
        datos = self._datos_parciales_con_items("Resma de papel carta", "")
        datos["items-1-cantidad"] = ""
        self.client.post(self.url_guardar, datos)
        self.assertEqual(len(self.client.get(self.url_crear).context["items"].forms), 1)

    def test_las_filas_marcadas_para_eliminar_no_entran_al_borrador(self):
        datos = self._datos_parciales_con_items("Resma de papel carta", "Toner negro")
        datos["items-1-DELETE"] = "on"
        self.client.post(self.url_guardar, datos)
        formset = self.client.get(self.url_crear).context["items"]
        self.assertEqual(
            [f.initial["descripcion"] for f in formset.forms], ["Resma de papel carta"]
        )

    def test_un_borrador_solo_de_items_tambien_se_guarda(self):
        # El encabezado en blanco pero con items diligenciados no es "nada".
        datos = dict.fromkeys(self._datos_parciales(), "")
        datos["prioridad"] = str(self.prioridad.pk)
        datos.update(datos_items("Resma de papel carta"))
        self.client.post(self.url_guardar, datos)
        self.assertIn(CLAVE_SESION_BORRADOR, self.client.session)

    def test_el_aviso_dice_cuantos_items_trae_el_borrador(self):
        self.client.post(
            self.url_guardar,
            self._datos_parciales_con_items("Resma de papel carta", "Toner negro"),
        )
        respuesta = self.client.get(self.url_crear)
        self.assertEqual(respuesta.context["borrador"]["items"], 2)
        self.assertContains(respuesta, "2 ítems")

    def test_radicar_elimina_el_borrador_con_items(self):
        self.client.post(self.url_guardar, self._datos_parciales_con_items("Resma de papel carta"))
        self.client.post(self.url_crear, self._datos_completos())
        self.assertEqual(Requerimiento.objects.count(), 1)
        self.assertNotIn(CLAVE_SESION_BORRADOR, self.client.session)
        self.assertEqual(self.client.get(self.url_crear).context["items"].forms[0].initial, {})

    def test_sin_borrador_la_tabla_abre_con_una_sola_fila_vacia(self):
        formset = self.client.get(self.url_crear).context["items"]
        self.assertEqual(len(formset.forms), 1)
        self.assertEqual(formset.forms[0].initial, {})


@override_settings(COMPRAS_EMAILS=["compras@coinogas.com", "analista@coinogas.com"])
class NotificacionAreaComprasTests(VistaTestCase):
    """HU-19: el área de compras recibe un correo cuando se radica un requerimiento."""

    def setUp(self):
        super().setUp()
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

    # --- HU-19 + HU-06: el aviso tiene que decir que se esta pidiendo ---

    def test_el_correo_lista_los_items_solicitados(self):
        self._radicar(self.datos | datos_items("Resma de papel carta", "Toner negro"))
        cuerpo = mail.outbox[0].body
        self.assertIn("Ítems solicitados: 2", cuerpo)
        self.assertIn("Resma de papel carta", cuerpo)
        self.assertIn("Toner negro", cuerpo)

    def test_la_version_html_tambien_lista_los_items(self):
        self._radicar(self.datos | datos_items("Resma de papel carta"))
        html = mail.outbox[0].alternatives[0].content
        self.assertIn("Resma de papel carta", html)

    def test_el_correo_detalla_cantidad_unidad_y_especificaciones(self):
        datos = self.datos | datos_items("Manometro de linea")
        datos["items-0-cantidad"] = "3"
        datos["items-0-especificaciones_tecnicas"] = "Rango 0-100 psi, norma ISO 5171."
        self._radicar(datos)
        cuerpo = mail.outbox[0].body
        self.assertIn("3 Unidad (UND) - Manometro de linea", cuerpo)
        self.assertIn("Rango 0-100 psi, norma ISO 5171.", cuerpo)

    def test_el_correo_advierte_calibracion_y_reembolsable(self):
        datos = self.datos | datos_items("Manometro de linea")
        datos["items-0-requiere_calibracion"] = "on"
        datos["items-0-es_reembolsable"] = "on"
        self._radicar(datos)
        cuerpo = mail.outbox[0].body
        self.assertIn("Requiere certificado de calibración.", cuerpo)
        self.assertIn("Compra reembolsable.", cuerpo)

    def test_el_correo_incluye_el_total_estimado(self):
        datos = self.datos | datos_items("Resma de papel carta")
        datos["items-0-cantidad"] = "4"
        datos["items-0-precio_referencia"] = "25000"
        self._radicar(datos)
        self.assertIn("Total estimado: 100000,00", mail.outbox[0].body)

    def test_el_correo_avisa_cuando_el_total_es_parcial(self):
        self._radicar()  # el item por defecto no trae precio
        cuerpo = mail.outbox[0].body
        self.assertIn("Sin precio de referencia.", cuerpo)
        self.assertIn("parcial", cuerpo)


@override_settings(COMPRAS_EMAILS=["compras@coinogas.com"])
class NotificacionConfirmacionSolicitanteTests(VistaTestCase):
    """HU-35: el solicitante recibe un correo de confirmación de su propia radicación."""

    def setUp(self):
        super().setUp()
        self.usuario.email = "ana.gomez@coinogas.com"
        self.usuario.save()
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

    def _correo_solicitante(self):
        """De los dos correos que salen al radicar (HU-19 + HU-35), el del solicitante."""
        return next(m for m in mail.outbox if m.to == [self.usuario.email])

    # --- Happy path ---
    def test_radicar_envia_tambien_la_confirmacion_al_solicitante(self):
        self._radicar()
        self.assertEqual(len(mail.outbox), 2)  # compras (HU-19) + solicitante (HU-35)
        correo = self._correo_solicitante()
        self.assertEqual(correo.to, [self.usuario.email])

    def test_el_asunto_identifica_el_requerimiento(self):
        self._radicar()
        requerimiento = Requerimiento.objects.get()
        self.assertIn(requerimiento.consecutivo, self._correo_solicitante().subject)

    def test_el_cuerpo_resume_el_requerimiento_y_sus_items(self):
        self._radicar(self.datos | datos_items("Resma de papel carta"))
        requerimiento = Requerimiento.objects.get()
        cuerpo = self._correo_solicitante().body
        self.assertIn(requerimiento.consecutivo, cuerpo)
        self.assertIn("Reposición de insumos de oficina.", cuerpo)
        self.assertIn("Resma de papel carta", cuerpo)

    def test_el_correo_lleva_version_html_ademas_de_texto_plano(self):
        self._radicar()
        alternativas = self._correo_solicitante().alternatives
        self.assertEqual(len(alternativas), 1)
        self.assertEqual(alternativas[0].mimetype, "text/html")

    def test_el_remitente_es_el_configurado(self):
        self._radicar()
        self.assertEqual(self._correo_solicitante().from_email, settings.DEFAULT_FROM_EMAIL)

    def test_cada_radicacion_genera_una_sola_confirmacion(self):
        self._radicar()
        self._radicar()
        correos_al_solicitante = [m for m in mail.outbox if m.to == [self.usuario.email]]
        self.assertEqual(len(correos_al_solicitante), 2)

    # --- Flujo alterno: sin correo a donde enviar ---
    def test_cuenta_sin_correo_registrado_no_se_notifica_pero_se_radica(self):
        self.usuario.email = ""
        self.usuario.save()
        with self.assertLogs("requerimientos.notificaciones", level="WARNING") as registro:
            respuesta = self._radicar()
        self.assertEqual(Requerimiento.objects.count(), 1)
        self.assertEqual(respuesta.status_code, 302)
        # Sigue saliendo el aviso a compras (HU-19); solo falta el del solicitante.
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("HU-35", registro.output[0])

    def test_un_envio_incompleto_no_notifica_al_solicitante(self):
        # HU-15 bloquea la radicación: no hay nada que confirmar.
        respuesta = self._radicar(self.datos | {"solicitante": ""})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_una_falla_del_servidor_de_correo_no_tumba_la_radicacion(self):
        smtp_caido = mock.patch.object(
            EmailMultiAlternatives, "send", side_effect=smtplib.SMTPException("SMTP caído")
        )
        with smtp_caido, self.assertLogs("requerimientos.notificaciones", level="ERROR"):
            respuesta = self._radicar()

        requerimiento = Requerimiento.objects.get()
        self.assertRedirects(
            respuesta, reverse("requerimientos:confirmacion", args=[requerimiento.consecutivo])
        )

    def test_la_confirmacion_no_depende_de_que_compras_tenga_buzones(self):
        # HU-19 y HU-35 son independientes: sin COMPRAS_EMAILS, compras no recibe
        # nada pero el solicitante sí recibe su confirmación.
        with override_settings(COMPRAS_EMAILS=[]):
            self._radicar()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.usuario.email])


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


class RequerimientoVistaTests(VistaTestCase):
    """Cubre el envío completo del formulario: encabezado + ítems (HU-06)."""

    def setUp(self):
        super().setUp()
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


class ItemMarcasTests(VistaTestCase):
    """Cubre HU-08 (marcas de calibración y de reembolsable)."""

    def setUp(self):
        super().setUp()
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


class ItemEspecificacionesTests(VistaTestCase):
    """Cubre HU-09 (especificaciones técnicas del ítem)."""

    FICHA = (
        'Manómetro de glicerina, diámetro 4".\n'
        "Rango 0-100 psi, precisión ±1,6 %.\n"
        'Conexión 1/4" NPT inferior, caja en acero inoxidable 304.\n'
        "Debe cumplir la norma EN 837-1."
    )

    def setUp(self):
        super().setUp()
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


class TotalesTests(VistaTestCase):
    """Cubre HU-10 (cálculo automático de totales)."""

    def setUp(self):
        super().setUp()
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


class RutaRaizTests(VistaTestCase):
    """La raíz del sitio lleva al formulario, no a un 404."""

    def test_la_raiz_redirige_al_formulario(self):
        respuesta = self.client.get("/")
        self.assertRedirects(respuesta, reverse("requerimientos:crear"))

    def test_la_redireccion_es_temporal(self):
        # 302 y no 301: cuando exista la bandeja (HU-20) el destino cambia, y
        # una redirección permanente se queda cacheada en el navegador.
        respuesta = self.client.get("/")
        self.assertEqual(respuesta.status_code, 302)


class IdentidadVisualTests(VistaTestCase):
    """La plantilla base carga la identidad de Coinogas en todas las pantallas."""

    def setUp(self):
        super().setUp()
        self.url = reverse("requerimientos:crear")

    def test_declara_el_viewport(self):
        # Sin esta etiqueta el grid de Bootstrap no responde en celular.
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, 'name="viewport"')

    def test_muestra_el_logo_y_el_sello_del_formato(self):
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "logo-coinogas.png")
        self.assertContains(respuesta, "ADM-F-22")

    def test_carga_la_hoja_de_estilos_propia_despues_de_bootstrap(self):
        contenido = self.client.get(self.url).content.decode()
        self.assertIn("via-compras.css", contenido)
        self.assertLess(contenido.index("bootstrap"), contenido.index("via-compras.css"))


class PortadaTests(TestCase):
    """La raíz es pública y presenta el sistema (HU-01)."""

    def test_la_portada_responde_sin_sesion(self):
        respuesta = self.client.get(reverse("portada"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "requerimientos/portada.html")

    def test_presenta_los_tres_perfiles(self):
        respuesta = self.client.get(reverse("portada"))
        for nombre in perfiles.PERFILES:
            self.assertContains(respuesta, nombre)

    def test_ofrece_entrar_al_sistema(self):
        respuesta = self.client.get(reverse("portada"))
        self.assertContains(respuesta, reverse("ingresar"))

    def test_a_quien_ya_entro_no_le_muestra_la_portada(self):
        # Volver a la presentación comercial cuando ya tienes sesión es un paso
        # de más: se va derecho a la pantalla del perfil.
        self.client.force_login(crear_usuario(perfil=perfiles.SOLICITANTE))
        respuesta = self.client.get(reverse("portada"))
        self.assertRedirects(respuesta, reverse("requerimientos:crear"))


class IngresoTests(TestCase):
    """Ingreso con cuenta y enrutamiento según el perfil."""

    CLAVE = "clave-de-prueba-123"

    def setUp(self):
        self.url = reverse("ingresar")

    def _entrar(self, usuario):
        return self.client.post(
            self.url, {"username": usuario, "password": self.CLAVE}, follow=False
        )

    def test_la_pantalla_de_ingreso_es_publica(self):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "registration/login.html")

    def test_credenciales_incorrectas_no_abren_sesion(self):
        crear_usuario("ana.gomez", perfil=perfiles.SOLICITANTE, clave=self.CLAVE)
        respuesta = self.client.post(
            self.url, {"username": "ana.gomez", "password": "no-es"}, follow=False
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'id="error-ingreso"')
        self.assertFalse(respuesta.wsgi_request.user.is_authenticated)

    def test_el_solicitante_cae_en_el_formulario(self):
        crear_usuario("ana.gomez", perfil=perfiles.SOLICITANTE, clave=self.CLAVE)
        respuesta = self._entrar("ana.gomez")
        self.assertRedirects(respuesta, reverse("requerimientos:crear"))

    def test_el_analista_cae_en_la_bandeja(self):
        crear_usuario("daryi.silva", perfil=perfiles.ANALISTA, clave=self.CLAVE)
        respuesta = self._entrar("daryi.silva")
        self.assertRedirects(respuesta, reverse("requerimientos:bandeja"))

    def test_el_administrador_cae_en_el_panel(self):
        cuenta = crear_usuario("admin.compras", perfil=perfiles.ADMINISTRADOR, clave=self.CLAVE)
        cuenta.is_staff = True
        cuenta.save()
        respuesta = self._entrar("admin.compras")
        self.assertRedirects(respuesta, reverse("admin:index"), fetch_redirect_response=False)

    def test_un_usuario_sin_perfil_asignado_puede_radicar(self):
        # Sin grupo, el sistema lo trata como solicitante: es lo mínimo que
        # cualquier empleado necesita hacer.
        crear_usuario("nuevo.empleado", clave=self.CLAVE)
        respuesta = self._entrar("nuevo.empleado")
        self.assertRedirects(respuesta, reverse("requerimientos:crear"))

    def test_respeta_la_pantalla_que_se_intentaba_abrir(self):
        crear_usuario("ana.gomez", perfil=perfiles.SOLICITANTE, clave=self.CLAVE)
        destino = reverse("requerimientos:mios")
        respuesta = self.client.post(
            self.url, {"username": "ana.gomez", "password": self.CLAVE, "next": destino}
        )
        self.assertRedirects(respuesta, destino)

    def test_salir_cierra_la_sesion_y_vuelve_a_la_portada(self):
        self.client.force_login(crear_usuario(perfil=perfiles.SOLICITANTE))
        respuesta = self.client.post(reverse("salir"))
        self.assertRedirects(respuesta, reverse("portada"))
        self.assertFalse(respuesta.wsgi_request.user.is_authenticated)


class AccesoSinSesionTests(TestCase):
    """Ninguna pantalla de trabajo responde a quien no ha entrado."""

    def setUp(self):
        self.protegidas = [
            reverse("requerimientos:crear"),
            reverse("requerimientos:bandeja"),
            reverse("requerimientos:mios"),
        ]

    def test_las_pantallas_de_trabajo_mandan_al_ingreso(self):
        for url in self.protegidas:
            with self.subTest(url=url):
                respuesta = self.client.get(url)
                self.assertRedirects(respuesta, f"{reverse('ingresar')}?next={url}")

    def test_radicar_sin_sesion_no_crea_nada(self):
        respuesta = self.client.post(reverse("requerimientos:crear"), {})
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Requerimiento.objects.count(), 0)


class AutoriaRequerimientoTests(VistaTestCase):
    """El requerimiento queda atado a la cuenta que lo radicó."""

    def setUp(self):
        super().setUp()
        self.area = Area.objects.create(nombre="Mantenimiento")
        self.centro_costo = CentroCosto.objects.create(codigo="CC-100", nombre="Planta Medellín")
        self.prioridad = Prioridad.objects.create(nombre=Prioridad.MEDIA, orden=2)
        self.url = reverse("requerimientos:crear")

    def _datos(self, **overrides):
        datos = {
            "solicitante": "Ana Gómez",
            "area": self.area.pk,
            "centro_costo": self.centro_costo.pk,
            "justificacion": "Reposición de insumos.",
            "prioridad": self.prioridad.pk,
            "fecha_requerida": (date.today() + timedelta(days=10)).isoformat(),
            **datos_items(),
        }
        datos.update(overrides)
        return datos

    def test_el_formulario_propone_el_nombre_de_la_cuenta(self):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.context["form"].initial["solicitante"], "Ana Gómez")

    def test_al_radicar_queda_registrada_la_cuenta(self):
        self.client.post(self.url, self._datos())
        self.assertEqual(Requerimiento.objects.get().creado_por, self.usuario)

    def test_mis_requerimientos_solo_muestra_los_propios(self):
        self.client.post(self.url, self._datos())
        mio = Requerimiento.objects.get()

        otra_cuenta = crear_usuario("luis.mesa", "Luis", "Mesa")
        otro = Client()
        otro.force_login(otra_cuenta)

        propios = self.client.get(reverse("requerimientos:mios")).context["requerimientos"]
        ajenos = otro.get(reverse("requerimientos:mios")).context["requerimientos"]

        self.assertEqual(list(propios), [mio])
        self.assertEqual(list(ajenos), [])

    def test_la_confirmacion_ajena_no_se_puede_espiar(self):
        # El consecutivo es adivinable, así que la pantalla no puede quedar
        # abierta a cualquiera que esté en sesión.
        self.client.post(self.url, self._datos())
        consecutivo = Requerimiento.objects.get().consecutivo

        otro = Client()
        otro.force_login(crear_usuario("luis.mesa", "Luis", "Mesa"))
        respuesta = otro.get(reverse("requerimientos:confirmacion", args=[consecutivo]))

        self.assertEqual(respuesta.status_code, 404)


class BandejaTests(VistaTestCase):
    """Bandeja del área de compras: quién entra y qué ve."""

    perfil_de_prueba = perfiles.ANALISTA

    def setUp(self):
        super().setUp()
        self.area = Area.objects.create(nombre="Mantenimiento")
        self.centro_costo = CentroCosto.objects.create(codigo="CC-100", nombre="Planta Medellín")
        self.prioridad = Prioridad.objects.create(nombre=Prioridad.ALTA, orden=1)
        self.unidad = UnidadMedida.objects.create(codigo="UND", nombre="Unidad")
        self.url = reverse("requerimientos:bandeja")

    def _radicar(self, solicitante, creado_por=None):
        requerimiento = Requerimiento.objects.create(
            solicitante=solicitante,
            area=self.area,
            centro_costo=self.centro_costo,
            justificacion="Compra de repuestos.",
            prioridad=self.prioridad,
            fecha_requerida=date.today() + timedelta(days=10),
            creado_por=creado_por,
        )
        Item.objects.create(
            requerimiento=requerimiento,
            numero=1,
            cantidad=2,
            unidad_medida=self.unidad,
            descripcion="Empaque",
            precio_referencia=Decimal("1500.00"),
        )
        return requerimiento

    def test_el_analista_ve_todo_lo_radicado(self):
        self._radicar("Ana Gómez")
        self._radicar("Luis Mesa")
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.context["requerimientos"]), 2)

    def test_muestra_el_consecutivo_y_el_total(self):
        requerimiento = self._radicar("Ana Gómez")
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, requerimiento.consecutivo)
        self.assertContains(respuesta, "3.000")

    def test_el_solicitante_no_entra_a_la_bandeja(self):
        otro = Client()
        otro.force_login(crear_usuario("luis.mesa", "Luis", "Mesa", perfiles.SOLICITANTE))
        self.assertEqual(otro.get(self.url).status_code, 403)

    def test_el_administrador_si_entra(self):
        otro = Client()
        otro.force_login(crear_usuario("dc", "David", "Cuadros", perfiles.ADMINISTRADOR))
        self.assertEqual(otro.get(self.url).status_code, 200)

    def test_la_barra_ofrece_la_bandeja_solo_a_quien_puede_entrar(self):
        self.assertContains(self.client.get(self.url), reverse("requerimientos:bandeja"))

        otro = Client()
        otro.force_login(crear_usuario("luis.mesa", "Luis", "Mesa", perfiles.SOLICITANTE))
        respuesta = otro.get(reverse("requerimientos:crear"))
        self.assertNotContains(respuesta, reverse("requerimientos:bandeja"))


class PerfilesTests(TestCase):
    """Reglas de los perfiles, sin pasar por las vistas."""

    def test_los_grupos_se_crean_una_sola_vez(self):
        perfiles.asegurar_grupos()
        perfiles.asegurar_grupos()
        self.assertEqual(Group.objects.filter(name__in=perfiles.PERFILES).count(), 3)

    def test_un_superusuario_administra_aunque_no_tenga_grupo(self):
        # Si no fuera así, quien instala el proyecto quedaría fuera del sistema.
        raiz = get_user_model().objects.create_superuser(username="raiz", password=None)
        self.assertIn(perfiles.ADMINISTRADOR, perfiles.perfiles_de(raiz))

    def test_quien_es_analista_y_solicitante_entra_por_la_bandeja(self):
        cuenta = crear_usuario("mixta", perfil=perfiles.ANALISTA)
        grupos = {g.name: g for g in perfiles.asegurar_grupos()}
        cuenta.groups.add(grupos[perfiles.SOLICITANTE])
        self.assertEqual(perfiles.destino_tras_ingresar(cuenta), "requerimientos:bandeja")

    def test_un_anonimo_no_tiene_perfiles(self):
        self.assertEqual(perfiles.perfiles_de(AnonymousUser()), set())


class VistasAnaliticasTests(TransactionTestCase):
    """HU-29: vistas SQL desnormalizadas de solo lectura.

    Se usa TransactionTestCase porque las vistas las crea una migración con SQL
    crudo (RunPython), y deben existir en la base de datos de prueba al consultar.
    """

    def setUp(self):
        from .analitica import ItemAnalitico, RequerimientoAnalitico

        self.RequerimientoAnalitico = RequerimientoAnalitico
        self.ItemAnalitico = ItemAnalitico

        self.area = Area.objects.create(nombre="Mantenimiento")
        self.centro_costo = CentroCosto.objects.create(codigo="CC-100", nombre="Planta Medellín")
        self.prioridad = Prioridad.objects.create(nombre=Prioridad.ALTA, orden=1)
        self.unidad = UnidadMedida.objects.create(codigo="UND", nombre="Unidad")

        self.req = Requerimiento.objects.create(
            solicitante="Ana Gómez",
            area=self.area,
            centro_costo=self.centro_costo,
            justificacion="Reposición de insumos.",
            prioridad=self.prioridad,
            fecha_requerida=date.today() + timedelta(days=10),
        )
        Item.objects.create(
            requerimiento=self.req,
            numero=1,
            cantidad=4,
            unidad_medida=self.unidad,
            descripcion="Resma de papel",
            precio_referencia=Decimal("25000.00"),
        )
        Item.objects.create(
            requerimiento=self.req,
            numero=2,
            cantidad=1,
            unidad_medida=self.unidad,
            descripcion="Tóner",
            precio_referencia=Decimal("150000.00"),
        )

    # --- Happy path ---
    def test_la_vista_de_requerimientos_desnormaliza_area_prioridad_y_fechas(self):
        fila = self.RequerimientoAnalitico.objects.get(consecutivo=self.req.consecutivo)
        self.assertEqual(fila.area, "Mantenimiento")
        self.assertEqual(fila.prioridad, Prioridad.ALTA)
        self.assertEqual(fila.centro_costo_codigo, "CC-100")
        self.assertEqual(fila.fecha_solicitud, self.req.fecha_solicitud)
        self.assertEqual(fila.fecha_requerida, self.req.fecha_requerida)

    def test_la_vista_agrega_conteo_y_total_de_items(self):
        fila = self.RequerimientoAnalitico.objects.get(consecutivo=self.req.consecutivo)
        self.assertEqual(fila.numero_items, 2)
        # 4 * 25000 + 1 * 150000 = 250000
        self.assertEqual(Decimal(fila.total_estimado), Decimal("250000.00"))

    def test_la_vista_de_items_trae_consecutivo_y_unidad(self):
        filas = self.ItemAnalitico.objects.filter(consecutivo=self.req.consecutivo).order_by(
            "numero"
        )
        self.assertEqual(filas.count(), 2)
        self.assertEqual(filas[0].unidad_medida, "Unidad")
        self.assertEqual(filas[0].descripcion, "Resma de papel")

    # --- Flujo alternativo ---
    def test_un_requerimiento_sin_items_reporta_cero(self):
        vacio = Requerimiento.objects.create(
            solicitante="Luis Mesa",
            area=self.area,
            centro_costo=self.centro_costo,
            justificacion="Sin ítems todavía.",
            prioridad=self.prioridad,
            fecha_requerida=date.today() + timedelta(days=5),
        )
        fila = self.RequerimientoAnalitico.objects.get(consecutivo=vacio.consecutivo)
        self.assertEqual(fila.numero_items, 0)
        self.assertEqual(Decimal(fila.total_estimado), Decimal("0"))

    def test_la_vista_es_de_solo_lectura(self):
        # Escribir desde el ORM a través de la vista está prohibido por diseño.
        fila = self.RequerimientoAnalitico.objects.first()
        with self.assertRaises(NotImplementedError):
            fila.save()
        with self.assertRaises(NotImplementedError):
            fila.delete()


class AvisoConfirmacionRadicacionTests(VistaTestCase):
    """HU-34: aviso de confirmación antes de enviar.

    El comportamiento vivo (abrir el modal, llenar el resumen) ocurre en el
    navegador y se verifica en las pruebas de usabilidad. Aquí se comprueba lo
    que el servidor sí controla: que la plantilla entrega el modal, su resumen y
    el botón de confirmación, y que una radicación confirmada sigue funcionando
    (el aviso no debe estorbar el envío real).
    """

    def setUp(self):
        super().setUp()
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

    # --- Happy path ---
    def test_el_formulario_incluye_el_modal_de_confirmacion(self):
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, 'id="modal-confirmar-radicacion"')
        self.assertContains(respuesta, 'id="confirmar-radicacion"')

    def test_el_modal_resume_los_datos_clave_antes_de_enviar(self):
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, 'id="resumen-solicitante"')
        self.assertContains(respuesta, 'id="resumen-prioridad"')
        self.assertContains(respuesta, 'id="resumen-fecha"')
        self.assertContains(respuesta, 'id="resumen-items"')

    def test_radicacion_confirmada_crea_el_requerimiento(self):
        # El aviso es del lado del cliente: un POST válido (equivalente a haber
        # confirmado en el modal) debe radicar con normalidad.
        respuesta = self.client.post(self.url, self._datos_validos())
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Requerimiento.objects.count(), 1)

    # --- Flujo alternativo ---
    def test_un_envio_invalido_no_crea_el_requerimiento(self):
        # Si faltan campos, la validación de HU-15 frena antes del aviso: ni se
        # abre el modal ni se radica.
        respuesta = self.client.post(self.url, self._datos_validos(solicitante=""))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Requerimiento.objects.count(), 0)

    def test_guardar_borrador_no_pasa_por_el_aviso(self):
        # El botón de borrador lleva `formnovalidate` y una acción propia: no
        # debe quedar atrapado por el aviso de confirmación.
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "formnovalidate")
        self.assertContains(respuesta, reverse("requerimientos:guardar_borrador"))


class FichaRequerimientoTests(TestCase):
    """HU-22: ficha completa del requerimiento para el área de compras."""

    def setUp(self):
        self.area = Area.objects.create(nombre="Mantenimiento")
        self.centro_costo = CentroCosto.objects.create(codigo="CC-100", nombre="Planta Medellín")
        self.prioridad = Prioridad.objects.create(nombre=Prioridad.ALTA, orden=1)
        self.unidad = UnidadMedida.objects.create(codigo="UND", nombre="Unidad")

        self.req = Requerimiento.objects.create(
            solicitante="Ana Gómez",
            area=self.area,
            centro_costo=self.centro_costo,
            justificacion="Reposición de insumos de oficina.",
            prioridad=self.prioridad,
            fecha_requerida=date.today() + timedelta(days=10),
        )
        Item.objects.create(
            requerimiento=self.req,
            numero=1,
            cantidad=2,
            unidad_medida=self.unidad,
            descripcion="Manómetro de línea",
            especificaciones_tecnicas="Rango 0-100 psi, norma ISO 5171.",
            requiere_calibracion=True,
            precio_referencia=Decimal("80000.00"),
        )
        self.req.renumerar_items()

        self.analista = crear_usuario("compras", "Carla", "Ruiz", perfiles.ANALISTA)
        self.url = reverse("requerimientos:ficha", args=[self.req.consecutivo])

    # --- Happy path ---
    def test_el_analista_ve_la_ficha_completa(self):
        self.client.force_login(self.analista)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.req.consecutivo)
        self.assertContains(respuesta, "Ana Gómez")
        self.assertContains(respuesta, "CC-100")
        self.assertContains(respuesta, "Reposición de insumos de oficina.")

    def test_la_ficha_muestra_el_detalle_de_los_items(self):
        self.client.force_login(self.analista)
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "Manómetro de línea")
        self.assertContains(respuesta, "Rango 0-100 psi")
        self.assertContains(respuesta, "Requiere calibración")

    def test_la_ficha_muestra_el_total_estimado(self):
        self.client.force_login(self.analista)
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, 'id="total-estimado">160000,00<')

    def test_el_administrador_tambien_entra(self):
        admin = crear_usuario("dc", "David", "Cuadros", perfiles.ADMINISTRADOR)
        self.client.force_login(admin)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    # --- Flujo alternativo ---
    def test_un_solicitante_no_puede_abrir_la_ficha_de_gestion(self):
        solicitante = crear_usuario("luis.mesa", "Luis", "Mesa", perfiles.SOLICITANTE)
        self.client.force_login(solicitante)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_un_consecutivo_inexistente_devuelve_404(self):
        self.client.force_login(self.analista)
        url = reverse("requerimientos:ficha", args=["REQ-2026-9999"])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_sin_sesion_pide_ingresar(self):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("ingresar"), respuesta["Location"])


class MisRequerimientosTests(VistaTestCase):
    """HU-25: el solicitante consulta y busca entre lo que ha radicado."""

    def setUp(self):
        super().setUp()
        self.area = Area.objects.create(nombre="Mantenimiento")
        self.centro_costo = CentroCosto.objects.create(codigo="CC-100", nombre="Planta Medellín")
        self.prioridad = Prioridad.objects.create(nombre=Prioridad.MEDIA, orden=2)
        self.unidad, _ = UnidadMedida.objects.get_or_create(
            codigo="UND", defaults={"nombre": "Unidad"}
        )
        self.url = reverse("requerimientos:mios")

    def _radicar(self, *descripciones, cuenta=None):
        """Crea un requerimiento con sus ítems, atado a una cuenta."""
        requerimiento = Requerimiento.objects.create(
            solicitante="Ana Gómez",
            area=self.area,
            centro_costo=self.centro_costo,
            justificacion="Reposición de insumos.",
            prioridad=self.prioridad,
            fecha_requerida=date.today() + timedelta(days=10),
            creado_por=cuenta or self.usuario,
        )
        for numero, descripcion in enumerate(descripciones or ("Resma de papel carta",), start=1):
            Item.objects.create(
                requerimiento=requerimiento,
                numero=numero,
                cantidad=1,
                unidad_medida=self.unidad,
                descripcion=descripcion,
            )
        return requerimiento

    def _listado(self, **parametros):
        return self.client.get(self.url, parametros).context["requerimientos"]

    # --- Listado ---

    def test_lista_lo_radicado_por_la_cuenta_en_sesion(self):
        req = self._radicar()
        self.assertEqual(list(self._listado()), [req])

    def test_lo_mas_reciente_aparece_primero(self):
        primero = self._radicar("Resma de papel carta")
        segundo = self._radicar("Tóner negro")
        self.assertEqual(list(self._listado()), [segundo, primero])

    def test_sin_requerimientos_lo_dice_en_pantalla(self):
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "Todavía no has radicado ningún requerimiento.")

    # --- Búsqueda (HU-25) ---

    def test_busca_por_consecutivo(self):
        buscado = self._radicar("Resma de papel carta")
        self._radicar("Tóner negro")
        self.assertEqual(list(self._listado(q=buscado.consecutivo)), [buscado])

    def test_busca_por_consecutivo_parcial(self):
        buscado = self._radicar()
        ultimos = buscado.consecutivo[-4:]
        self.assertEqual(list(self._listado(q=ultimos)), [buscado])

    def test_busca_por_lo_que_se_pidio(self):
        resmas = self._radicar("Resma de papel carta")
        self._radicar("Tóner negro")
        self.assertEqual(list(self._listado(q="resma")), [resmas])

    def test_la_busqueda_ignora_mayusculas_y_espacios_sobrantes(self):
        resmas = self._radicar("Resma de papel carta")
        self.assertEqual(list(self._listado(q="  RESMA  ")), [resmas])

    def test_un_requerimiento_con_varios_items_que_coinciden_aparece_una_sola_vez(self):
        # Sin `distinct` el cruce con ítems lo repetiría una vez por coincidencia.
        req = self._radicar("Resma de papel carta", "Resma de papel oficio")
        self.assertEqual(list(self._listado(q="resma")), [req])

    def test_la_busqueda_no_alcanza_requerimientos_ajenos(self):
        otra_cuenta = crear_usuario("luis.mesa", "Luis", "Mesa")
        ajeno = self._radicar("Resma de papel carta", cuenta=otra_cuenta)
        self.assertEqual(list(self._listado(q="resma")), [])
        self.assertEqual(list(self._listado(q=ajeno.consecutivo)), [])

    def test_sin_coincidencias_lo_dice_sin_sugerir_que_no_ha_radicado_nada(self):
        self._radicar("Resma de papel carta")
        respuesta = self.client.get(self.url, {"q": "motobomba"})
        self.assertContains(respuesta, "Ningún requerimiento tuyo coincide con esa búsqueda.")
        self.assertNotContains(respuesta, "Todavía no has radicado ningún requerimiento.")

    def test_la_pantalla_informa_cuantos_resultados_hubo(self):
        self._radicar("Resma de papel carta")
        respuesta = self.client.get(self.url, {"q": "resma"})
        self.assertContains(respuesta, 'id="conteo-resultados"')
        self.assertContains(respuesta, "1 resultado")

    def test_el_buscador_conserva_lo_escrito(self):
        respuesta = self.client.get(self.url, {"q": "resma"})
        self.assertEqual(respuesta.context["busqueda"], "resma")
        self.assertContains(respuesta, 'value="resma"')

    def test_la_paginacion_conserva_la_busqueda(self):
        # Sin esto, pasar a la página 2 devolvería el listado completo.
        respuesta = self.client.get(self.url, {"q": "resma", "page": "1"})
        self.assertEqual(respuesta.context["parametros_filtro"], "q=resma")

    def test_una_busqueda_vacia_devuelve_todo(self):
        req = self._radicar()
        self.assertEqual(list(self._listado(q="   ")), [req])

    def test_la_pantalla_no_filtra_comentarios_de_plantilla(self):
        # `{# ... #}` solo comenta una linea en Django: si abarca dos, se
        # imprime en la pagina. Para varias lineas va {% comment %}.
        self._radicar()
        respuesta = self.client.get(self.url)
        self.assertNotContains(respuesta, "{#")
        self.assertNotContains(respuesta, "#}")


@override_settings(DEBUG=True)
class SembrarDemoTests(TestCase):
    """Comando de datos de demostración (apoyo a HU-30)."""

    def _sembrar(self, **opciones):
        salida = StringIO()
        call_command("sembrar_demo", stdout=salida, semilla=7, **opciones)
        return salida.getvalue()

    def _demo(self):
        return Requerimiento.objects.filter(creado_por__username__startswith="demo.")

    def test_siembra_la_cantidad_pedida(self):
        self._sembrar(cantidad=12)
        self.assertEqual(self._demo().count(), 12)

    def test_los_requerimientos_quedan_repartidos_entre_areas_y_prioridades(self):
        # Si todo cayera en la misma área, el tablero saldría con una sola barra.
        self._sembrar(cantidad=40)
        self.assertGreaterEqual(Area.objects.count(), 3)
        self.assertEqual(self._demo().values("prioridad").distinct().count(), 3)
        self.assertGreaterEqual(self._demo().values("area").distinct().count(), 3)

    def test_los_requerimientos_quedan_repartidos_en_el_tiempo(self):
        # El indicador de volumen por mes necesita más de un mes con datos.
        self._sembrar(cantidad=40, meses=6)
        fechas = set(self._demo().values_list("fecha_solicitud", flat=True))
        self.assertGreater(len({(f.year, f.month) for f in fechas}), 1)

    def test_cada_requerimiento_queda_con_items(self):
        self._sembrar(cantidad=10)
        for requerimiento in self._demo():
            with self.subTest(consecutivo=requerimiento.consecutivo):
                self.assertGreaterEqual(requerimiento.items.count(), 1)

    def test_algunos_items_quedan_sin_precio(self):
        # Para que se vea el aviso de total parcial de HU-10.
        self._sembrar(cantidad=40)
        self.assertTrue(Item.objects.filter(precio_referencia__isnull=True).exists())

    def test_la_fecha_requerida_nunca_es_anterior_a_la_de_solicitud(self):
        self._sembrar(cantidad=40)
        for requerimiento in self._demo():
            with self.subTest(consecutivo=requerimiento.consecutivo):
                self.assertGreaterEqual(
                    requerimiento.fecha_requerida, requerimiento.fecha_solicitud
                )

    def test_no_siembra_dos_veces_sin_limpiar(self):
        self._sembrar(cantidad=5)
        with self.assertRaises(CommandError):
            self._sembrar(cantidad=5)
        self.assertEqual(self._demo().count(), 5)

    def test_limpiar_borra_los_datos_de_demostracion_y_sus_cuentas(self):
        self._sembrar(cantidad=5)
        self._sembrar(limpiar=True)
        self.assertEqual(self._demo().count(), 0)
        self.assertEqual(get_user_model().objects.filter(username__startswith="demo.").count(), 0)

    def test_limpiar_no_toca_los_requerimientos_reales(self):
        propio = crear_usuario("ana.real", "Ana", "Real")
        area = Area.objects.create(nombre="Área real")
        centro = CentroCosto.objects.create(codigo="CC-999", nombre="Sede real")
        prioridad = Prioridad.objects.create(nombre=Prioridad.ALTA, orden=1)
        real = Requerimiento.objects.create(
            solicitante="Ana Real",
            area=area,
            centro_costo=centro,
            justificacion="Requerimiento de verdad.",
            prioridad=prioridad,
            fecha_requerida=date.today() + timedelta(days=5),
            creado_por=propio,
        )

        self._sembrar(cantidad=5)
        self._sembrar(limpiar=True)

        self.assertTrue(Requerimiento.objects.filter(pk=real.pk).exists())
        self.assertTrue(get_user_model().objects.filter(username="ana.real").exists())

    @override_settings(DEBUG=False)
    def test_se_niega_a_correr_en_un_entorno_que_parece_real(self):
        with self.assertRaises(CommandError):
            self._sembrar(cantidad=5)
        self.assertEqual(self._demo().count(), 0)

    @override_settings(DEBUG=False)
    def test_con_forzar_corre_aunque_debug_este_apagado(self):
        self._sembrar(cantidad=3, forzar=True)
        self.assertEqual(self._demo().count(), 3)

    def test_la_misma_semilla_produce_el_mismo_conjunto(self):
        self._sembrar(cantidad=8)
        primero = list(self._demo().values_list("area__nombre", "prioridad__nombre"))
        self._sembrar(limpiar=True)
        self._sembrar(cantidad=8)
        self.assertEqual(
            list(self._demo().values_list("area__nombre", "prioridad__nombre")), primero
        )


class ExportarAnaliticaTests(TestCase):
    """Exportación de las vistas analíticas a CSV (apoyo a HU-30)."""

    def setUp(self):
        self.destino = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.destino, True)
        self.area = Area.objects.create(nombre="Logística")
        self.centro = CentroCosto.objects.create(codigo="CC-100", nombre="Planta Medellín")
        self.prioridad = Prioridad.objects.create(nombre=Prioridad.ALTA, orden=1)
        self.unidad = UnidadMedida.objects.create(codigo="UND", nombre="Unidad")

    def _requerimiento(self, precio=None):
        requerimiento = Requerimiento.objects.create(
            solicitante="Ana Gómez",
            area=self.area,
            centro_costo=self.centro,
            justificacion="Reposición de insumos.",
            prioridad=self.prioridad,
            fecha_requerida=date.today() + timedelta(days=10),
        )
        Item.objects.create(
            requerimiento=requerimiento,
            numero=1,
            cantidad=2,
            unidad_medida=self.unidad,
            descripcion="Resma de papel carta",
            precio_referencia=precio,
        )
        return requerimiento

    def _exportar(self):
        salida = StringIO()
        call_command("exportar_analitica", destino=str(self.destino), stdout=salida)
        return salida.getvalue()

    def _leer(self, vista):
        """Exporta y devuelve el contenido del CSV de esa vista."""
        self._exportar()
        archivo = self.destino / f"{vista}.csv"
        # `utf-8-sig` descarta la marca BOM al leer, igual que hace Power BI.
        with archivo.open(encoding="utf-8-sig", newline="") as entrada:
            return list(csv.DictReader(entrada))

    def test_escribe_un_csv_por_vista(self):
        self._requerimiento()
        self._exportar()
        for vista in ("analitica_requerimientos", "analitica_items"):
            with self.subTest(vista=vista):
                self.assertTrue((self.destino / f"{vista}.csv").exists())

    def test_exporta_una_fila_por_requerimiento(self):
        self._requerimiento()
        self._requerimiento()
        self.assertEqual(len(self._leer("analitica_requerimientos")), 2)

    def test_el_csv_lleva_las_columnas_que_el_tablero_necesita(self):
        self._requerimiento()
        fila = self._leer("analitica_requerimientos")[0]
        for columna in ("consecutivo", "area", "prioridad", "anio_solicitud", "mes_solicitud"):
            with self.subTest(columna=columna):
                self.assertIn(columna, fila)

    def test_las_tildes_sobreviven_a_la_exportacion(self):
        # Sin la marca BOM, Power BI leeria «LogÃ­stica» en vez de «Logística».
        self._requerimiento()
        self.assertEqual(self._leer("analitica_requerimientos")[0]["area"], "Logística")

    def test_el_archivo_empieza_con_la_marca_bom(self):
        self._requerimiento()
        self._exportar()
        crudo = (self.destino / "analitica_requerimientos.csv").read_bytes()
        self.assertTrue(crudo.startswith(b"\xef\xbb\xbf"))

    def test_las_fechas_salen_en_formato_iso(self):
        # Con 13/10/2026 Power BI podria leer el mes y el dia al reves.
        self._requerimiento()
        fila = self._leer("analitica_requerimientos")[0]
        self.assertEqual(fila["fecha_solicitud"], date.today().isoformat())

    def test_un_precio_ausente_sale_como_celda_vacia(self):
        self._requerimiento(precio=None)
        self.assertEqual(self._leer("analitica_items")[0]["precio_referencia"], "")

    def test_el_precio_se_exporta_con_punto_decimal(self):
        # Lo que importa no es cuantos decimales queden, sino que el separador
        # sea punto: con coma, Power BI leeria 24.500,50 como texto y no como
        # numero, y la grafica de totales saldria vacia.
        self._requerimiento(precio=Decimal("24500.50"))
        crudo = self._leer("analitica_items")[0]["precio_referencia"]
        self.assertNotIn(",", crudo)
        self.assertEqual(Decimal(crudo), Decimal("24500.50"))

    def test_crea_la_carpeta_destino_si_no_existe(self):
        self._requerimiento()
        nueva = self.destino / "subcarpeta" / "analitica"
        call_command("exportar_analitica", destino=str(nueva), stdout=StringIO())
        self.assertTrue((nueva / "analitica_requerimientos.csv").exists())

    def test_sin_requerimientos_escribe_solo_los_encabezados(self):
        self._exportar()
        self.assertEqual(self._leer("analitica_requerimientos"), [])
        crudo = (self.destino / "analitica_requerimientos.csv").read_text(encoding="utf-8-sig")
        self.assertIn("consecutivo", crudo.splitlines()[0])


class CargarCatalogosTests(TestCase):
    """Comando `cargar_catalogos`: prioridades (HU-04) y unidades de medida (HU-07)."""

    def _cargar(self):
        salida = StringIO()
        call_command("cargar_catalogos", stdout=salida)
        return salida.getvalue()

    def test_carga_las_tres_prioridades_en_orden(self):
        self._cargar()
        nombres = list(Prioridad.objects.order_by("orden").values_list("nombre", flat=True))
        self.assertEqual(nombres, [Prioridad.ALTA, Prioridad.MEDIA, Prioridad.BAJA])

    def test_carga_las_unidades_de_medida(self):
        self._cargar()
        self.assertTrue(UnidadMedida.objects.filter(codigo="UND", nombre="Unidad").exists())
        self.assertEqual(UnidadMedida.objects.count(), 9)

    def test_correrlo_dos_veces_no_duplica_ni_falla(self):
        self._cargar()
        salida = self._cargar()
        self.assertEqual(Prioridad.objects.count(), 3)
        self.assertEqual(UnidadMedida.objects.count(), 9)
        self.assertIn("actualizada", salida)

    def test_corrige_un_orden_alterado_a_mano(self):
        Prioridad.objects.create(nombre=Prioridad.ALTA, orden=9)
        self._cargar()
        self.assertEqual(Prioridad.objects.get(nombre=Prioridad.ALTA).orden, 1)


class CrearPerfilesTests(TestCase):
    """Comando `crear_perfiles`: grupos de perfil y cuentas de demostración."""

    def _crear(self, **opciones):
        salida = StringIO()
        call_command("crear_perfiles", stdout=salida, **opciones)
        return salida.getvalue()

    def test_crea_los_tres_perfiles(self):
        self._crear()
        self.assertEqual(set(Group.objects.values_list("name", flat=True)), set(perfiles.PERFILES))

    def test_sin_con_demo_no_crea_cuentas(self):
        salida = self._crear()
        self.assertFalse(get_user_model().objects.exists())
        self.assertIn("--con-demo", salida)

    def test_con_demo_crea_una_cuenta_por_perfil_con_su_grupo(self):
        self._crear(con_demo=True)
        analista = get_user_model().objects.get(username="analista")
        self.assertTrue(perfiles.es(analista, perfiles.ANALISTA))
        self.assertTrue(analista.has_usable_password())
        administrador = get_user_model().objects.get(username="admin.compras")
        self.assertTrue(administrador.is_staff)

    def test_con_demo_no_cambia_la_clave_de_una_cuenta_existente(self):
        cuenta = crear_usuario(usuario="solicitante", clave="clave-que-ya-usaba")
        salida = self._crear(con_demo=True)
        cuenta.refresh_from_db()
        self.assertTrue(cuenta.check_password("clave-que-ya-usaba"))
        self.assertIn("ya existía", salida)


class CrearRolAnaliticaTests(TestCase):
    """Comando `crear_rol_analitica` (HU-29): rol de BD de solo lectura.

    El comando solo tiene sentido en PostgreSQL. Las validaciones y el SQL que
    emite se prueban con un cursor simulado para que corran en cualquier motor;
    la ejecución real contra PostgreSQL la cubre el CI.
    """

    def _con_cursor_simulado(self, rol_existe):
        cursor = mock.MagicMock()
        cursor.fetchone.return_value = (1,) if rol_existe else None
        contexto = mock.MagicMock()
        contexto.__enter__.return_value = cursor
        parches = (
            mock.patch.object(connection, "vendor", "postgresql"),
            mock.patch.object(connection, "cursor", return_value=contexto),
        )
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)
        return cursor

    def _sql_emitido(self, cursor):
        return [llamada.args[0] for llamada in cursor.execute.call_args_list]

    @skipUnless(connection.vendor != "postgresql", "Valida el rechazo en motores no PostgreSQL.")
    def test_fuera_de_postgresql_se_niega_a_correr(self):
        with self.assertRaisesMessage(CommandError, "solo aplica a PostgreSQL"):
            call_command("crear_rol_analitica", password="x", stdout=StringIO())

    def test_sin_contrasena_falla_con_un_mensaje_claro(self):
        self._con_cursor_simulado(rol_existe=False)
        with mock.patch.dict("os.environ", {}, clear=False) as entorno:
            entorno.pop("ANALITICA_DB_PASSWORD", None)
            with self.assertRaisesMessage(CommandError, "Falta la contraseña"):
                call_command("crear_rol_analitica", stdout=StringIO())

    def test_rechaza_un_nombre_de_rol_que_no_sea_identificador_simple(self):
        self._con_cursor_simulado(rol_existe=False)
        with self.assertRaisesMessage(CommandError, "alfanumérico"):
            call_command(
                "crear_rol_analitica", password="x", rol='x"; DROP TABLE y; --', stdout=StringIO()
            )

    def test_crea_el_rol_y_solo_le_da_select_sobre_las_vistas(self):
        cursor = self._con_cursor_simulado(rol_existe=False)
        salida = StringIO()
        call_command("crear_rol_analitica", password="clave", stdout=salida)
        sql = self._sql_emitido(cursor)
        self.assertTrue(any(s.startswith('CREATE ROLE "analitica_lectura"') for s in sql))
        self.assertTrue(any(s.startswith("REVOKE ALL ON ALL TABLES") for s in sql))
        concedidos = [s for s in sql if s.startswith("GRANT SELECT")]
        self.assertEqual(
            concedidos,
            [
                'GRANT SELECT ON "analitica_requerimientos" TO "analitica_lectura";',
                'GRANT SELECT ON "analitica_items" TO "analitica_lectura";',
            ],
        )
        self.assertIn("creado", salida.getvalue())

    def test_si_el_rol_ya_existe_solo_actualiza_la_clave(self):
        cursor = self._con_cursor_simulado(rol_existe=True)
        with mock.patch.dict("os.environ", {"ANALITICA_DB_PASSWORD": "desde-entorno"}):
            salida = StringIO()
            call_command("crear_rol_analitica", stdout=salida)
        sql = self._sql_emitido(cursor)
        self.assertFalse(any(s.startswith("CREATE ROLE") for s in sql))
        self.assertTrue(any(s.startswith('ALTER ROLE "analitica_lectura"') for s in sql))
        self.assertIn("ya existía", salida.getvalue())


class FiltrosBandejaTests(VistaTestCase):
    """HU-21: filtrar y ordenar la bandeja por área, prioridad y fecha.

    Casos de prueba CP-S2-04 (filtrar) y CP-S2-05 (ordenar) de la Wiki.
    """

    perfil_de_prueba = perfiles.ANALISTA

    def setUp(self):
        super().setUp()
        self.url = reverse("requerimientos:bandeja")
        self.mantenimiento = Area.objects.create(nombre="Mantenimiento")
        self.logistica = Area.objects.create(nombre="Logística")
        self.centro = CentroCosto.objects.create(codigo="CC-100", nombre="Planta Medellín")
        self.alta = Prioridad.objects.create(nombre=Prioridad.ALTA, orden=1)
        self.media = Prioridad.objects.create(nombre=Prioridad.MEDIA, orden=2)
        self.baja = Prioridad.objects.create(nombre=Prioridad.BAJA, orden=3)
        hoy = timezone.localdate()
        # Tres radicaciones que se diferencian en cada criterio de la historia.
        self.antiguo = self._radicar(
            self.mantenimiento, self.baja, radicado=hoy - timedelta(days=20), dias_para_requerir=30
        )
        self.urgente = self._radicar(
            self.logistica, self.alta, radicado=hoy - timedelta(days=10), dias_para_requerir=2
        )
        self.reciente = self._radicar(
            self.mantenimiento, self.media, radicado=hoy, dias_para_requerir=15
        )

    def _radicar(self, area, prioridad, radicado, dias_para_requerir):
        requerimiento = Requerimiento.objects.create(
            solicitante="Ana Gómez",
            area=area,
            centro_costo=self.centro,
            justificacion="Compra de repuestos.",
            prioridad=prioridad,
            fecha_requerida=timezone.localdate() + timedelta(days=dias_para_requerir),
        )
        # `fecha_solicitud` la asigna el sistema al radicar (auto_now_add); para
        # simular radicaciones de otros días se ajusta directo en la base.
        Requerimiento.objects.filter(pk=requerimiento.pk).update(fecha_solicitud=radicado)
        requerimiento.refresh_from_db()
        return requerimiento

    def _consecutivos(self, **parametros):
        respuesta = self.client.get(self.url, parametros)
        self.assertEqual(respuesta.status_code, 200)
        return [r.consecutivo for r in respuesta.context["requerimientos"]]

    # --- Happy path: cada criterio filtra lo que debe ---

    def test_sin_filtros_muestra_todo_de_lo_mas_reciente_a_lo_mas_antiguo(self):
        self.assertEqual(
            self._consecutivos(),
            [self.reciente.consecutivo, self.urgente.consecutivo, self.antiguo.consecutivo],
        )

    def test_filtra_por_area(self):
        consecutivos = self._consecutivos(area=self.logistica.pk)
        self.assertEqual(consecutivos, [self.urgente.consecutivo])

    def test_filtra_por_prioridad(self):
        consecutivos = self._consecutivos(prioridad=self.baja.pk)
        self.assertEqual(consecutivos, [self.antiguo.consecutivo])

    def test_filtra_por_rango_de_fechas_de_radicacion(self):
        hoy = timezone.localdate()
        consecutivos = self._consecutivos(
            desde=(hoy - timedelta(days=15)).isoformat(),
            hasta=(hoy - timedelta(days=5)).isoformat(),
        )
        self.assertEqual(consecutivos, [self.urgente.consecutivo])

    def test_los_filtros_se_combinan(self):
        consecutivos = self._consecutivos(area=self.mantenimiento.pk, prioridad=self.media.pk)
        self.assertEqual(consecutivos, [self.reciente.consecutivo])

    def test_ordena_por_prioridad_con_alta_primero(self):
        self.assertEqual(
            self._consecutivos(orden="prioridad"),
            [self.urgente.consecutivo, self.reciente.consecutivo, self.antiguo.consecutivo],
        )

    def test_ordena_por_la_fecha_requerida_mas_proxima(self):
        self.assertEqual(
            self._consecutivos(orden="requerida"),
            [self.urgente.consecutivo, self.reciente.consecutivo, self.antiguo.consecutivo],
        )

    def test_ordena_de_lo_mas_antiguo_a_lo_mas_reciente(self):
        self.assertEqual(
            self._consecutivos(orden="antiguos"),
            [self.antiguo.consecutivo, self.urgente.consecutivo, self.reciente.consecutivo],
        )

    def test_el_formulario_conserva_los_filtros_elegidos(self):
        respuesta = self.client.get(self.url, {"area": self.logistica.pk})
        self.assertContains(respuesta, f'<option value="{self.logistica.pk}" selected>')
        self.assertContains(respuesta, "1 resultado con los filtros aplicados")

    def test_la_paginacion_conserva_los_filtros(self):
        for _ in range(26):
            self._radicar(self.logistica, self.alta, timezone.localdate(), 5)
        respuesta = self.client.get(self.url, {"area": self.logistica.pk})
        self.assertContains(respuesta, f"?page=2&area={self.logistica.pk}")

    # --- Flujo alterno: datos que no permiten filtrar ---

    def test_sin_coincidencias_muestra_un_aviso_y_no_falla(self):
        otra_area = Area.objects.create(nombre="Sistemas")
        respuesta = self.client.get(self.url, {"area": otra_area.pk})
        self.assertEqual(list(respuesta.context["requerimientos"]), [])
        self.assertContains(respuesta, "Ningún requerimiento coincide con los filtros")

    def test_un_valor_invalido_se_informa_y_no_vacia_la_bandeja(self):
        respuesta = self.client.get(self.url, {"area": "99999", "prioridad": self.alta.pk})
        self.assertContains(respuesta, "Algunos filtros no se aplicaron")
        # El área inválida se ignora; la prioridad, que sí es válida, se aplica.
        consecutivos = [r.consecutivo for r in respuesta.context["requerimientos"]]
        self.assertEqual(consecutivos, [self.urgente.consecutivo])

    def test_una_fecha_mal_escrita_no_rompe_la_bandeja(self):
        respuesta = self.client.get(self.url, {"desde": "no-es-fecha"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.context["requerimientos"]), 3)
        self.assertContains(respuesta, "Algunos filtros no se aplicaron")

    def test_un_rango_invertido_se_rechaza_y_no_se_aplica(self):
        hoy = timezone.localdate()
        respuesta = self.client.get(
            self.url, {"desde": hoy.isoformat(), "hasta": (hoy - timedelta(days=30)).isoformat()}
        )
        self.assertContains(respuesta, "no puede ser posterior")
        self.assertEqual(len(respuesta.context["requerimientos"]), 3)

    def test_un_orden_desconocido_cae_en_el_orden_por_defecto(self):
        self.assertEqual(
            self._consecutivos(orden="inventado"),
            [self.reciente.consecutivo, self.urgente.consecutivo, self.antiguo.consecutivo],
        )

    def test_un_solicitante_no_puede_filtrar_la_bandeja(self):
        otro = Client()
        otro.force_login(crear_usuario("luis.mesa", "Luis", "Mesa", perfiles.SOLICITANTE))
        self.assertEqual(otro.get(self.url, {"area": self.logistica.pk}).status_code, 403)


@override_settings(COMPRAS_EMAILS=["compras@coinogas.com"])
class ProveedoresSugeridosTests(VistaTestCase):
    """HU-13: el solicitante sugiere hasta tres proveedores con su teléfono.

    Caso de prueba CP-S2-06 de la Wiki.
    """

    def setUp(self):
        super().setUp()
        self.usuario.email = "ana.gomez@coinogas.com"
        self.usuario.save()
        self.area = Area.objects.create(nombre="Mantenimiento")
        self.centro = CentroCosto.objects.create(codigo="CC-100", nombre="Planta Medellín")
        self.prioridad = Prioridad.objects.create(nombre=Prioridad.ALTA, orden=1)
        self.url = reverse("requerimientos:crear")

    def _datos(self, **proveedores):
        return {
            "solicitante": "Ana Gómez",
            "area": self.area.pk,
            "centro_costo": self.centro.pk,
            "justificacion": "Reposición de repuestos de la línea 2.",
            "prioridad": self.prioridad.pk,
            "fecha_requerida": (date.today() + timedelta(days=10)).isoformat(),
            **datos_items(),
            **proveedores,
        }

    def _radicar(self, **proveedores):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self.url, self._datos(**proveedores))

    # --- Happy path ---

    def test_el_formulario_ofrece_tres_filas_de_proveedor(self):
        respuesta = self.client.get(self.url)
        for posicion in (1, 2, 3):
            self.assertContains(respuesta, f'name="proveedor_{posicion}_telefono"')
        self.assertNotContains(respuesta, 'name="proveedor_4_nombre"')

    def test_radicar_guarda_los_proveedores_con_su_telefono(self):
        respuesta = self._radicar(
            proveedor_1_nombre="Ferretería El Tornillo",
            proveedor_1_telefono="604 444 1234",
            proveedor_1_observaciones="Preguntar por Marta",
            proveedor_2_nombre="Hidráulicos del Valle",
            proveedor_2_telefono="+57 300 123 4567",
        )
        requerimiento = Requerimiento.objects.get()
        self.assertRedirects(
            respuesta, reverse("requerimientos:confirmacion", args=[requerimiento.consecutivo])
        )
        proveedores = list(requerimiento.proveedores_sugeridos.values_list("orden", "nombre"))
        self.assertEqual(proveedores, [(1, "Ferretería El Tornillo"), (2, "Hidráulicos del Valle")])
        self.assertEqual(
            requerimiento.proveedores_sugeridos.get(orden=1).observaciones, "Preguntar por Marta"
        )

    def test_sugerir_proveedores_es_opcional(self):
        self._radicar()
        requerimiento = Requerimiento.objects.get()
        self.assertFalse(requerimiento.proveedores_sugeridos.exists())

    def test_las_filas_se_compactan_si_se_salta_una(self):
        self._radicar(proveedor_3_nombre="Solo en la tercera", proveedor_3_telefono="3001234567")
        proveedor = ProveedorSugerido.objects.get()
        self.assertEqual(proveedor.orden, 1)

    def test_la_ficha_de_compras_muestra_los_proveedores(self):
        self._radicar(
            proveedor_1_nombre="Ferretería El Tornillo", proveedor_1_telefono="6044441234"
        )
        analista = Client()
        analista.force_login(crear_usuario("compras", "Carla", "Ruiz", perfiles.ANALISTA))
        consecutivo = Requerimiento.objects.get().consecutivo
        respuesta = analista.get(reverse("requerimientos:ficha", args=[consecutivo]))
        self.assertContains(respuesta, "Ferretería El Tornillo")
        self.assertContains(respuesta, 'href="tel:6044441234"')

    def test_el_correo_a_compras_incluye_los_proveedores(self):
        self._radicar(
            proveedor_1_nombre="Ferretería El Tornillo", proveedor_1_telefono="6044441234"
        )
        aviso = next(m for m in mail.outbox if "compras@coinogas.com" in m.to)
        self.assertIn("Ferretería El Tornillo - Tel. 6044441234", aviso.body)

    def test_el_borrador_conserva_los_proveedores(self):
        datos = {
            "solicitante": "Ana Gómez",
            "proveedor_1_nombre": "Ferretería El Tornillo",
            "proveedor_1_telefono": "6044441234",
        }
        self.client.post(reverse("requerimientos:guardar_borrador"), datos)
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, 'value="Ferretería El Tornillo"')

    # --- Flujo alterno: datos incompletos o inválidos ---

    def test_un_proveedor_sin_telefono_bloquea_la_radicacion(self):
        respuesta = self._radicar(proveedor_1_nombre="Ferretería El Tornillo")
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Requerimiento.objects.exists())
        self.assertContains(respuesta, "Sin teléfono, compras no puede pedir la cotización.")
        self.assertContains(respuesta, "Proveedores sugeridos</li>")

    def test_un_telefono_sin_nombre_bloquea_la_radicacion(self):
        respuesta = self._radicar(proveedor_2_telefono="6044441234")
        self.assertFalse(Requerimiento.objects.exists())
        self.assertContains(respuesta, "Escribe el nombre del proveedor")

    def test_un_telefono_con_letras_o_muy_corto_es_invalido(self):
        for telefono in ("llamar a Marta", "12345", "1" * 16):
            with self.subTest(telefono=telefono):
                respuesta = self._radicar(
                    proveedor_1_nombre="Ferretería El Tornillo", proveedor_1_telefono=telefono
                )
                self.assertContains(respuesta, "Escribe un teléfono válido")
        self.assertFalse(Requerimiento.objects.exists())

    def test_un_error_en_proveedores_conserva_lo_diligenciado(self):
        respuesta = self._radicar(proveedor_1_nombre="Ferretería El Tornillo")
        self.assertContains(respuesta, 'value="Ferretería El Tornillo"')
        self.assertContains(respuesta, "Reposición de repuestos de la línea 2.")

    def test_no_se_aceptan_mas_de_tres_proveedores(self):
        self._radicar(proveedor_4_nombre="Cuarto proveedor", proveedor_4_telefono="6044441234")
        requerimiento = Requerimiento.objects.get()
        self.assertFalse(requerimiento.proveedores_sugeridos.exists())

    def test_el_modelo_no_admite_una_posicion_fuera_de_rango(self):
        requerimiento = Requerimiento.objects.create(
            solicitante="Ana Gómez",
            area=self.area,
            centro_costo=self.centro,
            justificacion="Prueba.",
            prioridad=self.prioridad,
            fecha_requerida=date.today() + timedelta(days=5),
        )
        proveedor = ProveedorSugerido(
            requerimiento=requerimiento, orden=4, nombre="X", telefono="6044441234"
        )
        with self.assertRaises(ValidationError):
            proveedor.full_clean()


@override_settings(COMPRAS_EMAILS=["compras@coinogas.com"])
class ProductosSustitutosTests(VistaTestCase):
    """HU-14: el solicitante indica si existen productos o servicios sustitutos.

    Caso de prueba CP-S2-07 de la Wiki.
    """

    def setUp(self):
        super().setUp()
        self.usuario.email = "ana.gomez@coinogas.com"
        self.usuario.save()
        self.area = Area.objects.create(nombre="Mantenimiento")
        self.centro = CentroCosto.objects.create(codigo="CC-100", nombre="Planta Medellín")
        self.prioridad = Prioridad.objects.create(nombre=Prioridad.MEDIA, orden=2)
        self.url = reverse("requerimientos:crear")

    def _datos(self, **extra):
        return {
            "solicitante": "Ana Gómez",
            "area": self.area.pk,
            "centro_costo": self.centro.pk,
            "justificacion": "Cambio de manómetros de la línea 2.",
            "prioridad": self.prioridad.pk,
            "fecha_requerida": (date.today() + timedelta(days=10)).isoformat(),
            **datos_items("Manómetro de glicerina 0-100 psi"),
            **extra,
        }

    def _radicar(self, **extra):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self.url, self._datos(**extra))

    # --- Happy path ---

    def test_el_formulario_pregunta_si_hay_sustitutos(self):
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, 'name="hay_sustitutos"')
        self.assertContains(respuesta, 'name="sustitutos"')

    def test_por_defecto_no_hay_sustitutos(self):
        self._radicar()
        requerimiento = Requerimiento.objects.get()
        self.assertFalse(requerimiento.hay_sustitutos)
        self.assertEqual(requerimiento.sustitutos, "")

    def test_radicar_con_sustitutos_guarda_cuales(self):
        self._radicar(hay_sustitutos="on", sustitutos="Manómetro WIKA 213.53 o equivalente.")
        requerimiento = Requerimiento.objects.get()
        self.assertTrue(requerimiento.hay_sustitutos)
        self.assertEqual(requerimiento.sustitutos, "Manómetro WIKA 213.53 o equivalente.")

    def test_la_ficha_y_el_correo_muestran_los_sustitutos(self):
        self._radicar(hay_sustitutos="on", sustitutos="Manómetro WIKA 213.53 o equivalente.")
        aviso = next(m for m in mail.outbox if "compras@coinogas.com" in m.to)
        self.assertIn("Manómetro WIKA 213.53 o equivalente.", aviso.body)

        analista = Client()
        analista.force_login(crear_usuario("compras", "Carla", "Ruiz", perfiles.ANALISTA))
        consecutivo = Requerimiento.objects.get().consecutivo
        respuesta = analista.get(reverse("requerimientos:ficha", args=[consecutivo]))
        self.assertContains(respuesta, "Manómetro WIKA 213.53 o equivalente.")

    def test_la_ficha_aclara_cuando_no_hay_sustitutos(self):
        self._radicar()
        analista = Client()
        analista.force_login(crear_usuario("compras", "Carla", "Ruiz", perfiles.ANALISTA))
        consecutivo = Requerimiento.objects.get().consecutivo
        respuesta = analista.get(reverse("requerimientos:ficha", args=[consecutivo]))
        self.assertContains(respuesta, "El solicitante indicó que no hay sustitutos.")

    def test_el_borrador_conserva_la_respuesta(self):
        self.client.post(
            reverse("requerimientos:guardar_borrador"),
            {"hay_sustitutos": "on", "sustitutos": "Alquiler del equipo"},
        )
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "Alquiler del equipo")
        self.assertTrue(respuesta.context["form"]["hay_sustitutos"].value())

    # --- Flujo alterno ---

    def test_marcar_que_hay_sustitutos_sin_decir_cuales_bloquea_la_radicacion(self):
        respuesta = self._radicar(hay_sustitutos="on", sustitutos="   ")
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Requerimiento.objects.exists())
        self.assertContains(respuesta, "Indicaste que hay sustitutos: escribe cuáles")
        self.assertContains(respuesta, "Productos o servicios sustitutos</li>")

    def test_si_responde_que_no_se_descarta_lo_escrito(self):
        self._radicar(sustitutos="Algo que escribió y luego desmarcó")
        requerimiento = Requerimiento.objects.get()
        self.assertFalse(requerimiento.hay_sustitutos)
        self.assertEqual(requerimiento.sustitutos, "")

    def test_el_modelo_tambien_exige_la_descripcion(self):
        requerimiento = Requerimiento(
            solicitante="Ana Gómez",
            area=self.area,
            centro_costo=self.centro,
            justificacion="Prueba.",
            prioridad=self.prioridad,
            fecha_requerida=date.today() + timedelta(days=5),
            hay_sustitutos=True,
        )
        with self.assertRaises(ValidationError) as contexto:
            requerimiento.full_clean()
        self.assertIn("sustitutos", contexto.exception.message_dict)


def crear_requerimiento(creado_por=None, **overrides):
    """Requerimiento mínimo y válido, para las pruebas de estados y adjuntos.

    Crea los catálogos que necesita si todavía no existen, de modo que cada
    prueba pida solo lo que le importa.
    """
    area, _ = Area.objects.get_or_create(nombre="Mantenimiento")
    centro_costo, _ = CentroCosto.objects.get_or_create(
        codigo="CC-100", defaults={"nombre": "Planta Medellín"}
    )
    prioridad, _ = Prioridad.objects.get_or_create(nombre=Prioridad.MEDIA, defaults={"orden": 2})
    datos = {
        "solicitante": "Ana Gómez",
        "area": area,
        "centro_costo": centro_costo,
        "justificacion": "Reposición de instrumentación de planta.",
        "prioridad": prioridad,
        "fecha_requerida": date.today() + timedelta(days=10),
        "creado_por": creado_por,
    }
    datos.update(overrides)
    return Requerimiento.objects.create(**datos)


class EsquemaEstadoTests(TestCase):
    """HU-23: el requerimiento tiene estado y su bitácora de cambios."""

    def test_todo_requerimiento_nace_radicado(self):
        self.assertEqual(crear_requerimiento().estado, EstadoRequerimiento.RADICADO)

    def test_son_los_cinco_estados_del_prototipo(self):
        self.assertEqual(
            [etiqueta for _, etiqueta in EstadoRequerimiento.choices],
            ["Radicado", "En revisión", "Devuelto", "En cotización", "Cerrado"],
        )

    def test_el_estado_no_se_edita_desde_el_formulario_de_radicacion(self):
        # Solo cambia por transiciones que dejan rastro: si estuviera en el
        # formulario, el solicitante podría radicar algo ya "cerrado".
        self.assertNotIn("estado", RequerimientoForm().fields)

    def test_la_bitacora_se_lee_en_orden_cronologico(self):
        requerimiento = crear_requerimiento()
        primero = CambioEstado.objects.create(
            requerimiento=requerimiento,
            estado_anterior=EstadoRequerimiento.RADICADO,
            estado_nuevo=EstadoRequerimiento.EN_REVISION,
        )
        segundo = CambioEstado.objects.create(
            requerimiento=requerimiento,
            estado_anterior=EstadoRequerimiento.EN_REVISION,
            estado_nuevo=EstadoRequerimiento.EN_COTIZACION,
        )
        self.assertEqual(list(requerimiento.cambios_estado.all()), [primero, segundo])

    def test_un_cambio_se_describe_con_su_consecutivo_y_la_transicion(self):
        requerimiento = crear_requerimiento()
        cambio = CambioEstado.objects.create(
            requerimiento=requerimiento,
            estado_anterior=EstadoRequerimiento.RADICADO,
            estado_nuevo=EstadoRequerimiento.DEVUELTO,
        )
        self.assertEqual(str(cambio), f"{requerimiento.consecutivo}: Radicado → Devuelto")

    def test_la_bitacora_sobrevive_a_la_baja_de_la_cuenta(self):
        cuenta = crear_usuario("daryi.silva", perfil=perfiles.ANALISTA)
        cambio = CambioEstado.objects.create(
            requerimiento=crear_requerimiento(),
            estado_anterior=EstadoRequerimiento.RADICADO,
            estado_nuevo=EstadoRequerimiento.EN_REVISION,
            usuario=cuenta,
        )
        cuenta.delete()
        cambio.refresh_from_db()
        self.assertIsNone(cambio.usuario)


class EsquemaAdjuntoTests(TestCase):
    """HU-11: el requerimiento admite adjuntos."""

    def test_la_ruta_agrupa_por_consecutivo_con_nombre_aleatorio(self):
        requerimiento = crear_requerimiento()
        adjunto = Adjunto(requerimiento=requerimiento)

        ruta = ruta_adjunto(adjunto, "Ficha Técnica (v2).PDF")

        self.assertTrue(ruta.startswith(f"adjuntos/{requerimiento.consecutivo}/"))
        # La extensión se conserva, en minúsculas; el nombre del usuario no.
        self.assertTrue(ruta.endswith(".pdf"))
        self.assertNotIn("Ficha", ruta)

    def test_dos_archivos_con_el_mismo_nombre_no_chocan(self):
        adjunto = Adjunto(requerimiento=crear_requerimiento())
        self.assertNotEqual(ruta_adjunto(adjunto, "foto.jpg"), ruta_adjunto(adjunto, "foto.jpg"))

    def test_un_adjunto_se_muestra_con_su_nombre_original(self):
        adjunto = Adjunto(nombre_original="cotizacion-proveedor.pdf")
        self.assertEqual(str(adjunto), "cotizacion-proveedor.pdf")
