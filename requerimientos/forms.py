from django import forms

from .models import JUSTIFICACION_MAX_LENGTH, Requerimiento


class RequerimientoForm(forms.ModelForm):
    class Meta:
        model = Requerimiento
        fields = ["solicitante", "area", "centro_costo", "justificacion"]
        widgets = {
            "solicitante": forms.TextInput(attrs={"class": "form-control"}),
            "area": forms.Select(attrs={"class": "form-select"}),
            "centro_costo": forms.Select(attrs={"class": "form-select"}),
            "justificacion": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 5,
                "maxlength": JUSTIFICACION_MAX_LENGTH,
                "id": "id_justificacion",
            }),
        }

    def clean_justificacion(self):
        texto = self.cleaned_data.get("justificacion", "")
        if not texto.strip():
            raise forms.ValidationError("La justificación no puede quedar vacía.")
        return texto
