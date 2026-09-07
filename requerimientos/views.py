from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import CreateView

from .forms import RequerimientoForm
from .models import Requerimiento


class RequerimientoCreateView(CreateView):
    model = Requerimiento
    form_class = RequerimientoForm
    template_name = "requerimientos/requerimiento_form.html"
    success_url = reverse_lazy("requerimientos:crear")

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        messages.success(self.request, "Requerimiento radicado correctamente.")
        return respuesta
