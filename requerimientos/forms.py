from django import forms
from django.utils import timezone

from .models import JUSTIFICACION_MAX_LENGTH, Prioridad, Requerimiento


class RequerimientoForm(forms.ModelForm):
    class Meta:
        model = Requerimiento
        # fecha_solicitud queda fuera: no es editable por el usuario (HU-02).
        fields = [
            "solicitante",
            "area",
            "centro_costo",
            "justificacion",
            "prioridad",
            "fecha_requerida",
        ]
        widgets = {
            "solicitante": forms.TextInput(attrs={"class": "form-control"}),
            "area": forms.Select(attrs={"class": "form-select"}),
            "centro_costo": forms.Select(attrs={"class": "form-select"}),
            "justificacion": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "maxlength": JUSTIFICACION_MAX_LENGTH,
                    "id": "id_justificacion",
                }
            ),
            # HU-04: lista cerrada, el solicitante no escribe la prioridad libremente.
            "prioridad": forms.Select(attrs={"class": "form-select"}),
            # HU-05: selector de fecha nativo del navegador.
            "fecha_requerida": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["justificacion"].required = True
        self.fields["prioridad"].required = True
        self.fields["fecha_requerida"].required = True

        # HU-04: valor por defecto en Media al crear un requerimiento nuevo.
        if not self.instance.pk and not self.is_bound:
            media = Prioridad.objects.filter(nombre=Prioridad.MEDIA).first()
            if media:
                self.fields["prioridad"].initial = media.pk

    def clean_justificacion(self):
        texto = self.cleaned_data.get("justificacion", "")
        if not texto.strip():
            raise forms.ValidationError("La justificación no puede quedar vacía.")
        return texto

    def clean_fecha_requerida(self):
        fecha = self.cleaned_data.get("fecha_requerida")
        fecha_base = self.instance.fecha_solicitud or timezone.localdate()
        if fecha and fecha < fecha_base:
            raise forms.ValidationError(
                "La fecha requerida no puede ser anterior a la fecha de solicitud."
            )
        return fecha
