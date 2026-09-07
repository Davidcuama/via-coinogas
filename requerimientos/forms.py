from django import forms

from .models import Requerimiento


class RequerimientoForm(forms.ModelForm):
    class Meta:
        model = Requerimiento
        fields = ["solicitante", "area", "centro_costo"]
        widgets = {
            "solicitante": forms.TextInput(attrs={"class": "form-control"}),
            "area": forms.Select(attrs={"class": "form-select"}),
            "centro_costo": forms.Select(attrs={"class": "form-select"}),
        }
