from django import forms

from .models import JUSTIFICACION_MAX_LENGTH, Prioridad, Requerimiento


class RequerimientoForm(forms.ModelForm):
    class Meta:
        model = Requerimiento
        fields = ["solicitante", "area", "centro_costo", "justificacion", "prioridad"]
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
            "prioridad": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk and not self.is_bound:
            media = Prioridad.objects.filter(nombre=Prioridad.MEDIA).first()
            if media:
                self.fields["prioridad"].initial = media.pk

    def clean_justificacion(self):
        texto = self.cleaned_data.get("justificacion", "")
        if not texto.strip():
            raise forms.ValidationError("La justificación no puede quedar vacía.")
        return texto
