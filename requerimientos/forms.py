import re

from django import forms
from django.utils import timezone

from .models import (
    JUSTIFICACION_MAX_LENGTH,
    MAX_PROVEEDORES_SUGERIDOS,
    MENSAJE_SUSTITUTOS_OBLIGATORIOS,
    Area,
    Item,
    Prioridad,
    ProveedorSugerido,
    Requerimiento,
    UnidadMedida,
)

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
            # HU-14: opcionales; `sustitutos` solo se exige si se marcó que hay.
            "hay_sustitutos",
            "sustitutos",
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
            # HU-14: la casilla muestra u oculta la descripción en el navegador.
            "hay_sustitutos": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "sustitutos": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Ej. sirve también la referencia X de la marca Y, o un "
                    "servicio de alquiler en lugar de la compra.",
                }
            ),
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

    def clean(self):
        datos = super().clean()
        # HU-14: un "sí, hay sustitutos" sin decir cuáles no le sirve a compras.
        # Si responde que no, se descarta lo que hubiera escrito antes de
        # desmarcar la casilla, para no guardar una alternativa que ya negó.
        if datos.get("hay_sustitutos"):
            if not (datos.get("sustitutos") or "").strip():
                self.add_error("sustitutos", MENSAJE_SUSTITUTOS_OBLIGATORIOS)
        else:
            datos["sustitutos"] = ""
        return datos

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
            "especificaciones_tecnicas",
            "precio_referencia",
            "requiere_calibracion",
            "es_reembolsable",
        ]
        widgets = {
            # min=1 en el HTML acompaña al validador del modelo (HU-07).
            "cantidad": forms.NumberInput(
                attrs={
                    "class": "form-control item-cantidad",
                    "min": 1,
                    "step": 1,
                }
            ),
            "unidad_medida": forms.Select(attrs={"class": "form-select"}),
            "descripcion": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 2,
                    "placeholder": "Qué se necesita",
                }
            ),
            # HU-09: campo libre y amplio, no se recorta lo que escriba el usuario.
            "especificaciones_tecnicas": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Marca, modelo, referencia, rango, material, norma…",
                }
            ),
            # HU-10: el total no se digita, se calcula; aquí solo entra el precio.
            "precio_referencia": forms.NumberInput(
                attrs={
                    "class": "form-control item-precio",
                    "min": 0,
                    "step": "0.01",
                    "placeholder": "Opcional",
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
        significativos = (
            "cantidad",
            "descripcion",
            "especificaciones_tecnicas",
            "precio_referencia",
        )
        return any(campo in self.changed_data for campo in significativos)

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


def _fabrica_item_formset(extra=0):
    """Construye el formset de ítems con el número de filas extra indicado.

    `min_num=1` + `validate_min`: HU-06 exige al menos un ítem para radicar.
    `extra` se queda en 0 para el caso normal —se muestra exactamente la fila
    obligatoria y las demás las agrega el usuario con «Agregar ítem»— y solo
    crece al reabrir un borrador que traía varias filas (HU-18).
    """
    return forms.inlineformset_factory(
        Requerimiento,
        Item,
        form=ItemForm,
        formset=ItemBaseFormSet,
        extra=extra,
        min_num=1,
        validate_min=True,
        can_delete=True,
    )


ItemFormSet = _fabrica_item_formset()


def item_formset_desde_borrador(filas):
    """Formset de ítems precargado con las filas guardadas en un borrador (HU-18).

    `min_num=1` ya aporta la primera fila, así que solo se piden como extra las
    restantes. Sin filas guardadas queda idéntico al de un formulario en blanco.

    El formset se devuelve **sin enlazar**: un borrador está incompleto por
    definición y no debe abrirse mostrando errores de validación.
    """
    if not filas:
        return ItemFormSet()
    return _fabrica_item_formset(extra=len(filas) - 1)(initial=filas)


# HU-13: un teléfono colombiano real tiene entre 7 dígitos (fijo local) y 12
# (celular con indicativo +57); se deja margen hasta 15 por si el proveedor es
# extranjero. Se aceptan los separadores con que la gente lo escribe.
TELEFONO_CARACTERES_VALIDOS = re.compile(r"^[0-9+()\-\s.]+$")
TELEFONO_MIN_DIGITOS = 7
TELEFONO_MAX_DIGITOS = 15

CAMPOS_PROVEEDOR = ("nombre", "telefono", "observaciones")


def _campo_proveedor(posicion, campo):
    """Nombre del campo del formulario para el proveedor en esa posición."""
    return f"proveedor_{posicion}_{campo}"


class ProveedoresSugeridosForm(forms.Form):
    """Hasta tres proveedores sugeridos por el solicitante (HU-13).

    Se usa un formulario de posiciones fijas y no un formset porque son como
    mucho tres filas siempre visibles, igual que en el formato ADM-F-22. Todo
    es opcional; pero una fila que se empieza a llenar debe quedar completa
    (nombre y teléfono), porque un proveedor sin teléfono no le sirve a compras
    para pedir la cotización.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for posicion in range(1, MAX_PROVEEDORES_SUGERIDOS + 1):
            self.fields[_campo_proveedor(posicion, "nombre")] = forms.CharField(
                label=f"Proveedor {posicion}: nombre",
                max_length=ProveedorSugerido._meta.get_field("nombre").max_length,
                required=False,
                widget=forms.TextInput(
                    attrs={"class": "form-control", "placeholder": "Nombre o razón social"}
                ),
            )
            self.fields[_campo_proveedor(posicion, "telefono")] = forms.CharField(
                label=f"Proveedor {posicion}: teléfono",
                max_length=ProveedorSugerido._meta.get_field("telefono").max_length,
                required=False,
                widget=forms.TextInput(
                    attrs={
                        "class": "form-control",
                        "type": "tel",
                        "inputmode": "tel",
                        "placeholder": "Ej. 604 444 1234 o 300 123 4567",
                    }
                ),
            )
            self.fields[_campo_proveedor(posicion, "observaciones")] = forms.CharField(
                label=f"Proveedor {posicion}: observaciones",
                max_length=ProveedorSugerido._meta.get_field("observaciones").max_length,
                required=False,
                widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Opcional"}),
            )

    def full_clean(self):
        # Igual que el encabezado (HU-15): los campos con error se resaltan.
        super().full_clean()
        if not self.is_bound:
            return
        for nombre in self.errors:
            if nombre in self.fields:
                attrs = self.fields[nombre].widget.attrs
                attrs["class"] = f"{attrs.get('class', '')} is-invalid".strip()

    def filas(self):
        """Campos agrupados por posición, para pintarlos como una tabla."""
        return [
            {
                "posicion": posicion,
                **{campo: self[_campo_proveedor(posicion, campo)] for campo in CAMPOS_PROVEEDOR},
            }
            for posicion in range(1, MAX_PROVEEDORES_SUGERIDOS + 1)
        ]

    def clean(self):
        datos = super().clean()
        for posicion in range(1, MAX_PROVEEDORES_SUGERIDOS + 1):
            valores = {
                campo: (datos.get(_campo_proveedor(posicion, campo)) or "").strip()
                for campo in CAMPOS_PROVEEDOR
            }
            if not any(valores.values()):
                continue
            if not valores["nombre"]:
                self.add_error(
                    _campo_proveedor(posicion, "nombre"),
                    "Escribe el nombre del proveedor o deja la fila vacía.",
                )
            if not valores["telefono"]:
                self.add_error(
                    _campo_proveedor(posicion, "telefono"),
                    "Sin teléfono, compras no puede pedir la cotización.",
                )
            elif not self._telefono_valido(valores["telefono"]):
                self.add_error(
                    _campo_proveedor(posicion, "telefono"),
                    "Escribe un teléfono válido: solo números, espacios, +, - o paréntesis, "
                    f"entre {TELEFONO_MIN_DIGITOS} y {TELEFONO_MAX_DIGITOS} dígitos.",
                )
        return datos

    @staticmethod
    def _telefono_valido(telefono):
        if not TELEFONO_CARACTERES_VALIDOS.match(telefono):
            return False
        digitos = sum(caracter.isdigit() for caracter in telefono)
        return TELEFONO_MIN_DIGITOS <= digitos <= TELEFONO_MAX_DIGITOS

    def proveedores(self):
        """Proveedores diligenciados, en orden y sin filas vacías.

        Las filas se compactan: si el solicitante llenó la 1 y la 3, quedan
        guardados como 1 y 2, igual que la numeración de los ítems (HU-06).
        """
        resultado = []
        for posicion in range(1, MAX_PROVEEDORES_SUGERIDOS + 1):
            valores = {
                campo: (self.cleaned_data.get(_campo_proveedor(posicion, campo)) or "").strip()
                for campo in CAMPOS_PROVEEDOR
            }
            if any(valores.values()):
                resultado.append(valores)
        return resultado

    def guardar(self, requerimiento):
        """Crea los proveedores sugeridos del requerimiento recién radicado."""
        ProveedorSugerido.objects.bulk_create(
            ProveedorSugerido(requerimiento=requerimiento, orden=orden, **valores)
            for orden, valores in enumerate(self.proveedores(), start=1)
        )


# Nombres de todos los campos de proveedores, para el borrador (HU-18).
CAMPOS_PROVEEDORES_FORM = tuple(
    _campo_proveedor(posicion, campo)
    for posicion in range(1, MAX_PROVEEDORES_SUGERIDOS + 1)
    for campo in CAMPOS_PROVEEDOR
)


# HU-21: criterios de ordenamiento de la bandeja. La llave es lo que viaja en la
# URL (?orden=...) y el valor, la etiqueta del selector y el `order_by` que aplica.
# El último criterio de cada uno es el `pk`, para que el orden sea estable entre
# páginas cuando dos requerimientos empatan.
ORDEN_BANDEJA = {
    "recientes": ("Más recientes primero", ("-fecha_solicitud", "-pk")),
    "antiguos": ("Más antiguos primero", ("fecha_solicitud", "pk")),
    "requerida": ("Fecha requerida más próxima", ("fecha_requerida", "prioridad__orden", "pk")),
    "prioridad": ("Prioridad (Alta primero)", ("prioridad__orden", "fecha_requerida", "pk")),
}
ORDEN_BANDEJA_DEFECTO = "recientes"


class FiltroBandejaForm(forms.Form):
    """Filtros y ordenamiento de la bandeja del área de compras (HU-21).

    Viaja por GET para que una vista filtrada se pueda recargar, compartir o
    paginar sin perder los criterios. Todo es opcional: sin filtros, la bandeja
    muestra todo lo radicado. Un valor inválido (un área que no existe, una
    fecha mal escrita) se informa en el formulario y ese criterio simplemente
    no se aplica: el analista nunca se queda con la bandeja en blanco por un
    parámetro dañado en la URL.

    El filtro por estado entra cuando HU-23 cree el campo `estado` en el
    modelo; aquí basta con agregar el campo y su línea en `aplicar`.
    """

    area = forms.ModelChoiceField(
        label="Área o proyecto",
        queryset=Area.objects.all(),
        required=False,
        empty_label="Todas",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    prioridad = forms.ModelChoiceField(
        label="Prioridad",
        queryset=Prioridad.objects.all(),
        required=False,
        empty_label="Todas",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    desde = forms.DateField(
        label="Radicado desde",
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control form-control-sm", "type": "date"}),
    )
    hasta = forms.DateField(
        label="Radicado hasta",
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control form-control-sm", "type": "date"}),
    )
    orden = forms.ChoiceField(
        label="Ordenar por",
        required=False,
        choices=[(clave, etiqueta) for clave, (etiqueta, _) in ORDEN_BANDEJA.items()],
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )

    def clean(self):
        datos = super().clean()
        desde, hasta = datos.get("desde"), datos.get("hasta")
        if desde and hasta and desde > hasta:
            # Se descartan ambas fechas: no hay forma de saber cuál de las dos
            # quiso decir el analista, y aplicar solo una daría un resultado
            # que él no pidió.
            datos.pop("desde")
            datos.pop("hasta")
            raise forms.ValidationError(
                "La fecha «desde» no puede ser posterior a la fecha «hasta»."
            )
        return datos

    def criterios(self):
        """Criterios válidos, incluso si otros campos del formulario fallaron."""
        self.is_valid()
        return {campo: valor for campo, valor in self.cleaned_data.items() if valor}

    def hay_filtros(self):
        """``True`` si hay algún filtro aplicado (el orden no cuenta como filtro)."""
        return any(campo != "orden" for campo in self.criterios())

    def aplicar(self, consulta):
        """Filtra y ordena la consulta de la bandeja con los criterios válidos."""
        criterios = self.criterios()
        if "area" in criterios:
            consulta = consulta.filter(area=criterios["area"])
        if "prioridad" in criterios:
            consulta = consulta.filter(prioridad=criterios["prioridad"])
        if "desde" in criterios:
            consulta = consulta.filter(fecha_solicitud__gte=criterios["desde"])
        if "hasta" in criterios:
            consulta = consulta.filter(fecha_solicitud__lte=criterios["hasta"])
        orden = criterios.get("orden", ORDEN_BANDEJA_DEFECTO)
        return consulta.order_by(*ORDEN_BANDEJA[orden][1])
