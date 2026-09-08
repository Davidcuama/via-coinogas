from django.urls import reverse
from django.views.generic import CreateView, DetailView

from .forms import RequerimientoForm
from .models import Requerimiento


class RequerimientoCreateView(CreateView):
    model = Requerimiento
    form_class = RequerimientoForm
    template_name = "requerimientos/requerimiento_form.html"

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
