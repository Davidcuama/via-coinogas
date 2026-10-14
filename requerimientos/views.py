from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin, LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView

from . import adjuntos as reglas_adjuntos
from . import borradores, perfiles
from .forms import (
    AdjuntosForm,
    CambioEstadoForm,
    FiltroBandejaForm,
    ItemFormSet,
    ProveedoresSugeridosForm,
    RequerimientoForm,
    item_formset_desde_borrador,
)
from .models import Adjunto, Requerimiento, TransicionNoPermitidaError
from .notificaciones import notificar_confirmacion_solicitante, notificar_radicacion


class PortadaView(TemplateView):
    """Página de inicio pública.

    Es la cara del sistema para quien todavía no ha entrado: explica qué
    reemplaza (el formato ADM-F-22 en Excel) y qué hace cada perfil. Quien ya
    tiene sesión no la necesita, así que se le manda directo a su pantalla.
    """

    template_name = "requerimientos/portada.html"

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(perfiles.destino_tras_ingresar(request.user))
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["perfiles"] = [
            (nombre, perfiles.DESCRIPCIONES[nombre]) for nombre in perfiles.PERFILES
        ]
        return contexto


class IngresoView(LoginView):
    """Ingreso al sistema (pantalla de sesión)."""

    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        # `next` manda: si alguien llegó aquí porque intentó abrir una pantalla
        # concreta, se le devuelve a ella. Si no, cada perfil cae donde trabaja.
        destino = self.get_redirect_url()
        return destino or reverse(perfiles.destino_tras_ingresar(self.request.user))


class PerfilRequeridoMixin(AccessMixin):
    """Restringe una vista a ciertos perfiles.

    A quien no ha entrado se le manda al ingreso; a quien entró pero no tiene el
    perfil se le responde 403, porque mandarlo al login otra vez solo lo haría
    dar vueltas sin entender por qué.
    """

    perfiles_permitidos = ()

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not perfiles.perfiles_de(request.user) & set(self.perfiles_permitidos):
            raise PermissionDenied("Tu perfil no tiene acceso a esta pantalla.")
        return super().dispatch(request, *args, **kwargs)


class BandejaView(PerfilRequeridoMixin, ListView):
    """Bandeja del área de compras (HU-20, HU-21).

    Lista lo radicado y deja filtrarlo por área, prioridad y rango de fechas de
    radicación, y ordenarlo por fecha de radicación, fecha requerida o
    prioridad, para que el analista decida qué atender primero. Sin filtros
    muestra todo, de lo más reciente a lo más antiguo.
    """

    template_name = "requerimientos/bandeja.html"
    context_object_name = "requerimientos"
    paginate_by = 25
    perfiles_permitidos = (perfiles.ANALISTA, perfiles.ADMINISTRADOR)

    def get_filtros(self):
        if not hasattr(self, "_filtros"):
            self._filtros = FiltroBandejaForm(self.request.GET)
        return self._filtros

    def get_queryset(self):
        consulta = Requerimiento.objects.select_related(
            "area", "centro_costo", "prioridad"
        ).prefetch_related("items")
        return self.get_filtros().aplicar(consulta)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        filtros = self.get_filtros()
        contexto["filtros"] = filtros
        contexto["hay_filtros"] = filtros.hay_filtros()
        # Los filtros viajan en cada enlace de paginación: sin esto, pasar a la
        # página 2 devolvería la bandeja completa sin filtrar.
        parametros = self.request.GET.copy()
        parametros.pop("page", None)
        contexto["parametros_filtro"] = parametros.urlencode()
        return contexto


class MisRequerimientosView(LoginRequiredMixin, ListView):
    """Lo que ha radicado quien está en sesión (HU-25).

    El listado por sí solo no alcanza: quien lleva varias radicaciones necesita
    llegar a una en concreto para hacerle seguimiento, y si no puede, acaba
    llamando al área de compras —que es justo lo que la historia quiere evitar—.
    De ahí la búsqueda sobre lo propio.

    La columna de estado del requerimiento entra con HU-23, que es la que crea
    ese campo en el modelo.
    """

    template_name = "requerimientos/mis_requerimientos.html"
    context_object_name = "requerimientos"
    paginate_by = 25

    def busqueda(self):
        """Texto buscado, sin espacios sobrantes."""
        return self.request.GET.get("q", "").strip()

    def get_queryset(self):
        propios = (
            Requerimiento.objects.filter(creado_por=self.request.user)
            .select_related("area", "prioridad")
            .prefetch_related("items")
            .order_by("-fecha_solicitud", "-pk")
        )

        texto = self.busqueda()
        if not texto:
            return propios

        # Se busca por lo que el solicitante recuerda: el consecutivo que le
        # quedó, o qué fue lo que pidió. `distinct` porque el cruce con los
        # ítems repetiría el requerimiento una vez por cada ítem que coincida.
        return propios.filter(
            Q(consecutivo__icontains=texto) | Q(items__descripcion__icontains=texto)
        ).distinct()

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["busqueda"] = self.busqueda()
        # Conserva la búsqueda al cambiar de página: sin esto, pasar a la
        # página 2 devolvería el listado completo sin filtrar.
        parametros = self.request.GET.copy()
        parametros.pop("page", None)
        contexto["parametros_filtro"] = parametros.urlencode()
        return contexto


class RequerimientoCreateView(LoginRequiredMixin, CreateView):
    model = Requerimiento
    form_class = RequerimientoForm
    template_name = "requerimientos/requerimiento_form.html"

    def get_initial(self):
        # HU-18: si el solicitante dejó un borrador, el formulario se abre con lo
        # que alcanzó a diligenciar en lugar de en blanco.
        initial = super().get_initial()
        # El nombre de quien radica se propone desde la cuenta; sigue siendo
        # editable porque a veces se radica a nombre de un compañero.
        nombre = self.request.user.get_full_name() or self.request.user.get_username()
        initial.setdefault("solicitante", nombre)
        initial.update(borradores.valores(self.request.session))
        return initial

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        # HU-18: alimenta el aviso "retomaste un borrador" y su botón de descarte.
        contexto["borrador"] = borradores.resumen(self.request.session)
        # HU-06: la tabla de ítems viaja junto al encabezado en el mismo POST.
        if "items" not in contexto:
            if self.request.method == "POST":
                contexto["items"] = ItemFormSet(self.request.POST)
            else:
                # HU-18: al reabrir el formulario, la tabla vuelve con las filas
                # que traía el borrador.
                contexto["items"] = item_formset_desde_borrador(
                    borradores.items(self.request.session)
                )
        # HU-13: proveedores sugeridos, también en el mismo POST.
        if "proveedores" not in contexto:
            if self.request.method == "POST":
                contexto["proveedores"] = ProveedoresSugeridosForm(self.request.POST)
            else:
                contexto["proveedores"] = ProveedoresSugeridosForm(
                    initial=borradores.valores(self.request.session)
                )
        # HU-11: fotos y documentos de soporte.
        if "adjuntos" not in contexto:
            contexto["adjuntos"] = AdjuntosForm()
        # Los mismos límites que aplica el servidor, para que el navegador avise
        # antes de enviar. Viajan como JSON (json_script), no pegados en el script.
        contexto["limite_adjuntos"] = {
            "maximo": reglas_adjuntos.MAX_ADJUNTOS,
            "tamano": reglas_adjuntos.TAMANO_MAXIMO,
            "extensiones": list(reglas_adjuntos.EXTENSIONES),
        }
        # Si el formulario vuelve con errores, el navegador ya vació el selector
        # de archivos (no puede rellenarlo, por seguridad). Se avisa para que el
        # solicitante no crea que sus adjuntos siguen ahí.
        contexto["archivos_descartados"] = self.request.method == "POST" and bool(
            self.request.FILES.getlist("archivos")
        )
        return contexto

    def form_valid(self, form):
        # HU-06: un encabezado válido todavía no basta; si los ítems no lo son,
        # se devuelve el formulario completo sin tocar la base de datos.
        items = ItemFormSet(self.request.POST)
        proveedores = ProveedoresSugeridosForm(self.request.POST)
        adjuntos = AdjuntosForm(self.request.POST, self.request.FILES)
        # Se validan todos antes de decidir, para mostrar todos los errores de
        # una vez y no uno por cada intento de radicar.
        items_validos = items.is_valid()
        proveedores_validos = proveedores.is_valid()
        adjuntos_validos = adjuntos.is_valid()
        if not (items_validos and proveedores_validos and adjuntos_validos):
            return self.form_invalid(form, items, proveedores, adjuntos)

        form.instance.creado_por = self.request.user

        # Encabezado e ítems entran en una sola transacción: o entra todo, o nada.
        with transaction.atomic():
            respuesta = super().form_valid(form)
            items.instance = self.object
            items.save()
            self.object.renumerar_items()
            # HU-13: los proveedores sugeridos entran en la misma transacción.
            proveedores.guardar(self.object)
            # HU-11: y los adjuntos. Si la transacción se deshiciera, el archivo
            # ya escrito en disco quedaría sin registro que lo apunte; es un
            # caso raro y no deja datos inconsistentes, solo un archivo de más.
            reglas_adjuntos.guardar(self.object, adjuntos.adjuntos_validos(), self.request.user)
            # HU-19 + HU-35: los avisos se disparan solo si la transacción llegó a
            # confirmarse; si la radicación se deshace, no se avisa de un
            # requerimiento que no existe.
            requerimiento = self.object
            transaction.on_commit(lambda: notificar_radicacion(requerimiento))
            transaction.on_commit(lambda: notificar_confirmacion_solicitante(requerimiento))

        # HU-18: el borrador cumplió su función, el requerimiento ya quedó radicado.
        borradores.descartar(self.request.session)
        return respuesta

    def form_invalid(self, form, items=None, proveedores=None, adjuntos=None):
        # HU-06: el formset se conserva tal como lo envió el usuario para que no
        # pierda las filas que ya había diligenciado. Igual los proveedores (HU-13).
        if items is None:
            items = ItemFormSet(self.request.POST)
        if proveedores is None:
            proveedores = ProveedoresSugeridosForm(self.request.POST)
            proveedores.is_valid()
        # HU-11: se valida igual, para que los errores de los archivos aparezcan
        # junto con los del encabezado y no en un segundo intento.
        if adjuntos is None:
            adjuntos = AdjuntosForm(self.request.POST, self.request.FILES)
            adjuntos.is_valid()
        return self.render_to_response(
            self.get_context_data(
                form=form, items=items, proveedores=proveedores, adjuntos=adjuntos
            )
        )

    def get_success_url(self):
        # HU-17: patrón Post/Redirect/Get. Tras radicar se redirige a la pantalla
        # de confirmación, de modo que recargar la página no reenvía el formulario
        # ni genera un requerimiento duplicado.
        return reverse("requerimientos:confirmacion", args=[self.object.consecutivo])


class RequerimientoConfirmacionView(LoginRequiredMixin, DetailView):
    """Pantalla de confirmación de radicación (HU-17).

    Muestra el consecutivo asignado (HU-16) de forma destacada y un resumen del
    requerimiento. Se identifica por el consecutivo, que es lo que el solicitante
    va a usar para referirse a su solicitud.
    """

    model = Requerimiento
    template_name = "requerimientos/requerimiento_confirmacion.html"
    context_object_name = "requerimiento"
    slug_field = "consecutivo"
    slug_url_kwarg = "consecutivo"

    def get_queryset(self):
        # HU-17: el resumen recorre los ítems y su unidad de medida; se traen de
        # una vez para no disparar una consulta por fila.
        consulta = super().get_queryset().prefetch_related("items__unidad_medida", "adjuntos")
        # Un consecutivo es adivinable (REQ-2026-0001), así que la pantalla no
        # puede quedar abierta: cada quien ve lo suyo y compras lo ve todo.
        usuario = self.request.user
        if perfiles.perfiles_de(usuario) & {perfiles.ANALISTA, perfiles.ADMINISTRADOR}:
            return consulta
        return consulta.filter(creado_por=usuario)


class FichaRequerimientoView(PerfilRequeridoMixin, DetailView):
    """Ficha completa del requerimiento para el area de compras (HU-22)."""

    model = Requerimiento
    template_name = "requerimientos/requerimiento_ficha.html"
    context_object_name = "requerimiento"
    slug_field = "consecutivo"
    slug_url_kwarg = "consecutivo"
    perfiles_permitidos = (perfiles.ANALISTA, perfiles.ADMINISTRADOR)

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("area", "centro_costo", "prioridad", "creado_por")
            .prefetch_related(
                "items__unidad_medida",
                "proveedores_sugeridos",
                "adjuntos",
                "cambios_estado__usuario",
            )
        )

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        # HU-23: el cambio de estado se hace desde la propia ficha, que es
        # donde el analista tiene todo para decidir.
        contexto["cambio_estado"] = CambioEstadoForm(requerimiento=self.object)
        return contexto


class CambiarEstadoView(PerfilRequeridoMixin, View):
    """Cambia el estado de un requerimiento desde su ficha (HU-23).

    Solo por POST: un cambio de estado no puede dispararse con un enlace que
    alguien abra sin querer. Vuelve siempre a la ficha, con el resultado como
    aviso, para que el analista vea el estado nuevo y la bitácora actualizada.
    """

    perfiles_permitidos = (perfiles.ANALISTA, perfiles.ADMINISTRADOR)

    def post(self, request, consecutivo):
        requerimiento = get_object_or_404(Requerimiento, consecutivo=consecutivo)
        formulario = CambioEstadoForm(request.POST, requerimiento=requerimiento)
        ficha = redirect("requerimientos:ficha", consecutivo=consecutivo)

        if not formulario.is_valid():
            # Casi siempre es una ficha abierta hace rato: otro analista ya movió
            # el requerimiento y el botón que se pulsó ya no aplica.
            messages.error(
                request,
                "Ese cambio ya no aplica al estado actual del requerimiento. "
                "Revisa la ficha actualizada.",
            )
            return ficha

        try:
            requerimiento.cambiar_estado(
                formulario.cleaned_data["estado"],
                request.user,
                formulario.cleaned_data["observacion"],
            )
        except TransicionNoPermitidaError as error:
            messages.error(request, error.messages[0])
            return ficha

        messages.success(
            request,
            f"{requerimiento.consecutivo} pasó a «{requerimiento.get_estado_display()}».",
        )
        return ficha


class DescargarAdjuntoView(LoginRequiredMixin, View):
    """Entrega un adjunto a quien tiene derecho a verlo (HU-11).

    Los archivos no se publican en una ruta estática: el consecutivo que va en
    su ruta es adivinable, así que cualquiera con sesión podría recorrerlos.
    Pasan por aquí, que revisa que sea de quien radicó o del área de compras.

    A quien no tiene permiso se le responde 404 y no 403: decirle que no puede
    verlo ya le confirma que existe.
    """

    def get(self, request, pk):
        adjunto = get_object_or_404(Adjunto.objects.select_related("requerimiento"), pk=pk)
        if not reglas_adjuntos.puede_ver(request.user, adjunto):
            raise Http404("Adjunto no encontrado.")
        try:
            archivo = adjunto.archivo.open("rb")
        except FileNotFoundError as error:
            raise Http404("El archivo ya no está disponible.") from error
        # Las fotos y los PDF se abren en una pestaña; lo demás se descarga.
        return FileResponse(
            archivo,
            as_attachment=not reglas_adjuntos.se_ve_en_el_navegador(adjunto),
            filename=adjunto.nombre_original,
        )


class GuardarBorradorView(LoginRequiredMixin, View):
    """Guarda el borrador del formulario (HU-18).

    A diferencia de la radicación, aquí no se valida nada: el borrador existe
    precisamente para conservar lo diligenciado cuando todavía falta información
    (HU-15 solo aplica al radicar).
    """

    def post(self, request):
        if borradores.esta_en_blanco(request.POST):
            messages.warning(request, "No hay nada que guardar: el formulario está en blanco.")
        else:
            borradores.guardar(request.session, request.POST)
            messages.success(
                request,
                "Borrador guardado. Puedes cerrar esta página y retomarlo más tarde.",
            )
        return redirect("requerimientos:crear")


class DescartarBorradorView(LoginRequiredMixin, View):
    """Descarta el borrador guardado y deja el formulario en blanco (HU-18)."""

    def post(self, request):
        if borradores.descartar(request.session):
            messages.info(request, "Borrador descartado.")
        return redirect("requerimientos:crear")
