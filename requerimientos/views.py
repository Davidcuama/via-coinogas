from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin, LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView

from . import borradores, perfiles
from .forms import ItemFormSet, RequerimientoForm, item_formset_desde_borrador
from .models import Requerimiento
from .notificaciones import notificar_radicacion


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
    """Bandeja del área de compras.

    Versión preliminar: lista lo radicado, de lo más reciente a lo más antiguo.
    Los filtros, el ordenamiento y la gestión de estados son HU-20 a HU-24 y no
    se adelantan aquí.
    """

    template_name = "requerimientos/bandeja.html"
    context_object_name = "requerimientos"
    paginate_by = 25
    perfiles_permitidos = (perfiles.ANALISTA, perfiles.ADMINISTRADOR)

    def get_queryset(self):
        return (
            Requerimiento.objects.select_related("area", "centro_costo", "prioridad")
            .prefetch_related("items")
            .order_by("-fecha_solicitud", "-pk")
        )


class MisRequerimientosView(LoginRequiredMixin, ListView):
    """Lo que ha radicado quien está en sesión."""

    template_name = "requerimientos/mis_requerimientos.html"
    context_object_name = "requerimientos"
    paginate_by = 25

    def get_queryset(self):
        return (
            Requerimiento.objects.filter(creado_por=self.request.user)
            .select_related("area", "prioridad")
            .prefetch_related("items")
            .order_by("-fecha_solicitud", "-pk")
        )


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
        return contexto

    def form_valid(self, form):
        # HU-06: un encabezado válido todavía no basta; si los ítems no lo son,
        # se devuelve el formulario completo sin tocar la base de datos.
        items = ItemFormSet(self.request.POST)
        if not items.is_valid():
            return self.form_invalid(form, items)

        form.instance.creado_por = self.request.user

        # Encabezado e ítems entran en una sola transacción: o entra todo, o nada.
        with transaction.atomic():
            respuesta = super().form_valid(form)
            items.instance = self.object
            items.save()
            self.object.renumerar_items()
            # HU-19: el aviso al área de compras se dispara solo si la transacción
            # llegó a confirmarse; si la radicación se deshace, no se avisa de un
            # requerimiento que no existe.
            requerimiento = self.object
            transaction.on_commit(lambda: notificar_radicacion(requerimiento))

        # HU-18: el borrador cumplió su función, el requerimiento ya quedó radicado.
        borradores.descartar(self.request.session)
        return respuesta

    def form_invalid(self, form, items=None):
        # HU-06: el formset se conserva tal como lo envió el usuario para que no
        # pierda las filas que ya había diligenciado.
        if items is None:
            items = ItemFormSet(self.request.POST)
        return self.render_to_response(self.get_context_data(form=form, items=items))

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
        consulta = super().get_queryset().prefetch_related("items__unidad_medida")
        # Un consecutivo es adivinable (REQ-2026-0001), así que la pantalla no
        # puede quedar abierta: cada quien ve lo suyo y compras lo ve todo.
        usuario = self.request.user
        if perfiles.perfiles_de(usuario) & {perfiles.ANALISTA, perfiles.ADMINISTRADOR}:
            return consulta
        return consulta.filter(creado_por=usuario)


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
