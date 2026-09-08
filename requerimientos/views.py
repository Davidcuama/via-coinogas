from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, DetailView

from . import borradores
from .forms import RequerimientoForm
from .models import Requerimiento


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
        return contexto

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        # HU-18: el borrador cumplió su función, el requerimiento ya quedó radicado.
        borradores.descartar(self.request.session)
        return respuesta

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
