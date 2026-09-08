from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, DetailView

from . import borradores
from .forms import ItemFormSet, RequerimientoForm
from .models import Requerimiento
from .notificaciones import notificar_radicacion


class RequerimientoCreateView(CreateView):
    model = Requerimiento
    form_class = RequerimientoForm
    template_name = "requerimientos/requerimiento_form.html"

    def get_initial(self):
        # HU-18: si el solicitante dejó un borrador, el formulario se abre con lo
        # que alcanzó a diligenciar en lugar de en blanco.
        initial = super().get_initial()
        initial.update(borradores.valores(self.request.session))
        return initial

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        # HU-18: alimenta el aviso "retomaste un borrador" y su botón de descarte.
        contexto["borrador"] = borradores.resumen(self.request.session)
        # HU-06: la tabla de ítems viaja junto al encabezado en el mismo POST.
        if "items" not in contexto:
            datos = self.request.POST if self.request.method == "POST" else None
            contexto["items"] = ItemFormSet(datos)
        return contexto

    def form_valid(self, form):
        # HU-06: un encabezado válido todavía no basta; si los ítems no lo son,
        # se devuelve el formulario completo sin tocar la base de datos.
        items = ItemFormSet(self.request.POST)
        if not items.is_valid():
            return self.form_invalid(form, items)

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


class RequerimientoConfirmacionView(DetailView):
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


class GuardarBorradorView(View):
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


class DescartarBorradorView(View):
    """Descarta el borrador guardado y deja el formulario en blanco (HU-18)."""

    def post(self, request):
        if borradores.descartar(request.session):
            messages.info(request, "Borrador descartado.")
        return redirect("requerimientos:crear")
