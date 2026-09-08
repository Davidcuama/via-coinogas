from django import forms
from django.utils import timezone

from .models import JUSTIFICACION_MAX_LENGTH, Item, Prioridad, Requerimiento, UnidadMedida

# HU-15: campos obligatorios del formato ADM-F-22 «Manifestación Requerimiento de
# Compra». El formato exige al pie que no quede ningún espacio sin diligenciar;
# esta regla traslada esa instrucción escrita a una validación que el sistema
# hace cumplir. Cuando el formulario incorpore ítems y especificaciones (HU-06 en
# adelante), se agregan aquí sus campos.
CAMPOS_OBLIGATORIOS = (
    "solicitante",  # Encabezado: nombre de quien solicita
    "area",  # Encabezado: área o proyecto
    "centro_costo",  # Encabezado: centro de costo
    "justificacion",  # Justificación del requerimiento
    "prioridad",  # Planeación de la recepción: prioridad
    "fecha_requerida",  # Planeación de la recepción: fecha requerida
)

MENSAJE_CAMPO_OBLIGATORIO = "Este campo es obligatorio."
MENSAJE_OPCION_OBLIGATORIA = "Selecciona una opción de la lista."


class RequerimientoForm(forms.ModelForm):
    """Formulario de radicación (HU-01 a HU-05, HU-15).

    La validación del servidor es la fuente de verdad: aunque el navegador
    también valide (atributo ``required`` + Bootstrap), una petición enviada
    directamente sin pasar por el formulario es rechazada igual.
    """

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

        # HU-15: todos los campos del formato son obligatorios, con un mensaje
        # propio que le dice al solicitante qué se espera en cada uno.
        for nombre in CAMPOS_OBLIGATORIOS:
            campo = self.fields[nombre]
            campo.required = True
            es_lista = isinstance(campo, forms.ModelChoiceField)
            mensaje = MENSAJE_OPCION_OBLIGATORIA if es_lista else MENSAJE_CAMPO_OBLIGATORIO
            campo.error_messages["required"] = mensaje
            if es_lista:
                campo.error_messages["invalid_choice"] = mensaje
                campo.empty_label = "Selecciona…"

        # HU-04: valor por defecto en Media al crear un requerimiento nuevo.
        if not self.instance.pk and not self.is_bound:
            media = Prioridad.objects.filter(nombre=Prioridad.MEDIA).first()
            if media:
                self.fields["prioridad"].initial = media.pk

    def full_clean(self):
        # HU-15: los campos con error se resaltan visualmente (Bootstrap `is-invalid`).
        super().full_clean()
        if not self.is_bound:
            return
        for nombre in self.errors:
            if nombre in self.fields:
                attrs = self.fields[nombre].widget.attrs
                attrs["class"] = f"{attrs.get('class', '')} is-invalid".strip()

    def campos_con_error(self):
        """Nombres legibles de los campos que fallaron, para el resumen de errores."""
        return [self.fields[n].label for n in self.errors if n in self.fields]

    def clean_solicitante(self):
        # Un nombre compuesto solo por espacios no cuenta como diligenciado.
        texto = self.cleaned_data.get("solicitante", "")
        if not texto.strip():
            raise forms.ValidationError(MENSAJE_CAMPO_OBLIGATORIO)
        return texto.strip()

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


class ItemForm(forms.ModelForm):
    """Una fila de la tabla de ítems (HU-06).

    Sin `required` en el HTML: una fila que el usuario agregó y dejó en blanco
    es legítima y el servidor la ignora, así que la validación del navegador
    (HU-15) no debe bloquear el envío por ella. Las filas diligenciadas sí se
    validan, pero eso lo decide el servidor.
    """

    use_required_attribute = False

    class Meta:
        model = Item
        # numero queda fuera: lo asigna el sistema, no el solicitante (HU-06).
        fields = [
            "cantidad",
            "unidad_medida",
            "descripcion",
            "requiere_calibracion",
            "es_reembolsable",
        ]
        widgets = {
            # min=1 en el HTML acompaña al validador del modelo (HU-07).
            "cantidad": forms.NumberInput(attrs={"class": "form-control", "min": 1, "step": 1}),
            "unidad_medida": forms.Select(attrs={"class": "form-select"}),
            "descripcion": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 2,
                    "placeholder": "Qué se necesita",
                }
            ),
            # HU-08: marcas opcionales, sin valor obligatorio.
            "requiere_calibracion": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "es_reembolsable": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # HU-07: "Unidad" es la medida más frecuente, se propone por defecto.
        if not self.instance.pk:
            unidad = UnidadMedida.objects.filter(codigo="UND").first()
            if unidad:
                self.fields["unidad_medida"].initial = unidad.pk

    def has_changed(self):
        """Una fila con solo la unidad preseleccionada sigue estando vacía.

        Sin esto, el valor por defecto de `unidad_medida` haría que Django
        considerara «diligenciada» cualquier fila que el usuario agregó y dejó
        en blanco, y le exigiría el resto de los campos.
        """
        if self.instance.pk:
            return super().has_changed()
        return any(campo in self.changed_data for campo in ("cantidad", "descripcion"))

    def clean_descripcion(self):
        texto = self.cleaned_data.get("descripcion", "")
        if not texto.strip():
            raise forms.ValidationError("La descripción no puede quedar vacía.")
        return texto


class ItemBaseFormSet(forms.BaseInlineFormSet):
    """Formset de ítems: numera las filas antes de guardarlas (HU-06).

    Se numeran en el orden en que quedaron en el formulario para que la
    inserción no choque con la restricción de unicidad; la numeración final la
    deja consecutiva `Requerimiento.renumerar_items()`.
    """

    def save(self, commit=True):
        vivos = [
            form for form in self.forms if not self._should_delete_form(form) and form.has_changed()
        ]
        for posicion, form in enumerate(vivos, start=1):
            form.instance.numero = posicion
        return super().save(commit=commit)


# min_num=1 + validate_min: HU-06 exige al menos un ítem para radicar.
ItemFormSet = forms.inlineformset_factory(
    Requerimiento,
    Item,
    form=ItemForm,
    formset=ItemBaseFormSet,
    # extra=0 + min_num=1: se muestra exactamente una fila obligatoria; las
    # demás las agrega el usuario con el botón "Agregar ítem".
    extra=0,
    min_num=1,
    validate_min=True,
    can_delete=True,
)
