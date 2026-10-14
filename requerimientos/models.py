import uuid
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone

JUSTIFICACION_MAX_LENGTH = 1000

# HU-13: el solicitante sugiere como máximo tres proveedores. No hay un maestro
# de proveedores (acuerdo n.º 3 con el cliente): compras los valida al iniciar
# el contacto formal, así que aquí se guardan como texto libre.
MAX_PROVEEDORES_SUGERIDOS = 3

MENSAJE_SUSTITUTOS_OBLIGATORIOS = (
    "Indicaste que hay sustitutos: escribe cuáles para que compras los tenga en cuenta."
)

# HU-16: formato del consecutivo de radicación -> REQ-<año>-<número de 4 dígitos>.
# El número reinicia cada año; el año garantiza que nunca se repita entre periodos.
CONSECUTIVO_PREFIJO = "REQ"
CONSECUTIVO_DIGITOS = 4
CONSECUTIVO_MAX_LENGTH = len(CONSECUTIVO_PREFIJO) + 1 + 4 + 1 + CONSECUTIVO_DIGITOS  # REQ-2026-0001


class Area(models.Model):
    """Catálogo de áreas o proyectos (HU-02)."""

    nombre = models.CharField("Área o proyecto", max_length=100, unique=True)

    class Meta:
        verbose_name = "Área"
        verbose_name_plural = "Áreas"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class CentroCosto(models.Model):
    """Catálogo de centros de costo (HU-02)."""

    codigo = models.CharField("Código", max_length=20, unique=True)
    nombre = models.CharField("Nombre", max_length=100)

    class Meta:
        verbose_name = "Centro de costo"
        verbose_name_plural = "Centros de costo"
        ordering = ["codigo"]

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


class UnidadMedida(models.Model):
    """Catálogo de unidades de medida de los ítems (HU-07)."""

    codigo = models.CharField("Código", max_length=10, unique=True)
    nombre = models.CharField("Nombre", max_length=50)

    class Meta:
        verbose_name = "Unidad de medida"
        verbose_name_plural = "Unidades de medida"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.codigo})"


class Prioridad(models.Model):
    """Catálogo cerrado de prioridades (HU-04): Alta, Media, Baja."""

    ALTA = "ALTA"
    MEDIA = "MEDIA"
    BAJA = "BAJA"

    nombre = models.CharField("Prioridad", max_length=20, unique=True)
    orden = models.PositiveSmallIntegerField(
        "Orden de despliegue",
        default=0,
        help_text="Controla el orden en que aparece la prioridad en el selector.",
    )

    class Meta:
        verbose_name = "Prioridad"
        verbose_name_plural = "Prioridades"
        ordering = ["orden"]

    def __str__(self):
        return self.nombre.title()


def _prioridad_media_pk():
    """Default callable: usa la prioridad Media si ya existe en el catálogo."""
    return Prioridad.objects.filter(nombre=Prioridad.MEDIA).values_list("pk", flat=True).first()


class SecuenciaRadicacion(models.Model):
    """Contador anual del consecutivo de radicación (HU-16).

    Hay una fila por año. Al radicar, la fila del año en curso se bloquea con
    ``SELECT ... FOR UPDATE`` dentro de una transacción, se incrementa y se libera.
    Así dos envíos simultáneos nunca reciben el mismo número: el segundo espera a
    que el primero termine y toma el siguiente valor.
    """

    anio = models.PositiveIntegerField("Año", unique=True)
    ultimo_numero = models.PositiveIntegerField("Último número asignado", default=0)

    class Meta:
        verbose_name = "Secuencia de radicación"
        verbose_name_plural = "Secuencias de radicación"
        ordering = ["-anio"]

    def __str__(self):
        return f"{self.anio}: {self.ultimo_numero}"

    @classmethod
    def siguiente_consecutivo(cls, anio=None):
        """Reserva y devuelve el siguiente consecutivo del año indicado.

        Debe llamarse dentro de una transacción (``transaction.atomic``) para
        que el bloqueo de fila tenga efecto.
        """
        if anio is None:
            anio = timezone.localdate().year
        secuencia, _ = cls.objects.select_for_update().get_or_create(anio=anio)
        secuencia.ultimo_numero += 1
        secuencia.save(update_fields=["ultimo_numero"])
        return f"{CONSECUTIVO_PREFIJO}-{anio}-{secuencia.ultimo_numero:0{CONSECUTIVO_DIGITOS}d}"


class EstadoRequerimiento(models.TextChoices):
    """Estados del requerimiento a lo largo de su atención (HU-23).

    Son los cinco del prototipo de interfaces del Sprint 0, que el cliente ya
    validó: así lo que ve en pantalla coincide con lo que se acordó.
    """

    RADICADO = "radicado", "Radicado"
    EN_REVISION = "revision", "En revisión"
    DEVUELTO = "devuelto", "Devuelto"
    EN_COTIZACION = "cotizacion", "En cotización"
    CERRADO = "cerrado", "Cerrado"


ESTADO_MAX_LENGTH = 20

# HU-23: a qué estado se puede pasar desde cada uno. El flujo normal del área
# de compras es revisar, cotizar y cerrar; se permite volver de cotización a
# revisión porque a veces la cotización destapa algo que hay que revisar de
# nuevo. Cerrado es definitivo. Las transiciones hacia y desde Devuelto llegan
# con la devolución (HU-24), que exige además una observación.
TRANSICIONES = {
    EstadoRequerimiento.RADICADO: (EstadoRequerimiento.EN_REVISION,),
    EstadoRequerimiento.EN_REVISION: (EstadoRequerimiento.EN_COTIZACION,),
    EstadoRequerimiento.EN_COTIZACION: (
        EstadoRequerimiento.EN_REVISION,
        EstadoRequerimiento.CERRADO,
    ),
    EstadoRequerimiento.DEVUELTO: (),
    EstadoRequerimiento.CERRADO: (),
}

OBSERVACION_MAX_LENGTH = 1000


class TransicionNoPermitidaError(ValidationError):
    """Se intentó pasar a un estado al que no se llega desde el actual (HU-23)."""


class Requerimiento(models.Model):
    # --- Consecutivo de radicación (HU-16) ---
    # Se asigna en save() la primera vez que se guarda; el usuario nunca lo edita.
    consecutivo = models.CharField(
        "Consecutivo de radicación",
        max_length=CONSECUTIVO_MAX_LENGTH,
        unique=True,
        editable=False,
    )

    # --- Autoría ---
    # Queda anulable porque los requerimientos radicados antes del ingreso con
    # cuenta no tienen a quién apuntar. `solicitante` sigue siendo el nombre que
    # va en el formato ADM-F-22 y se puede corregir a mano; esto es la cuenta
    # que lo radicó, que es lo que permite decir "mis requerimientos".
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requerimientos",
        verbose_name="Radicado por",
        editable=False,
    )

    # --- Encabezado (HU-02) ---
    solicitante = models.CharField("Nombre del solicitante", max_length=150)
    area = models.ForeignKey(
        Area,
        on_delete=models.PROTECT,
        related_name="requerimientos",
        verbose_name="Área o proyecto",
    )
    centro_costo = models.ForeignKey(
        CentroCosto,
        on_delete=models.PROTECT,
        related_name="requerimientos",
        verbose_name="Centro de costo",
    )
    # auto_now_add + editable=False: se registra sola y el usuario no puede tocarla.
    fecha_solicitud = models.DateField("Fecha de solicitud", auto_now_add=True, editable=False)

    # --- Justificación (HU-03) ---
    justificacion = models.TextField("Justificación", max_length=JUSTIFICACION_MAX_LENGTH)

    # --- Prioridad (HU-04) ---
    prioridad = models.ForeignKey(
        Prioridad,
        on_delete=models.PROTECT,
        related_name="requerimientos",
        verbose_name="Prioridad",
        db_index=True,
        default=_prioridad_media_pk,
    )

    # --- Fecha requerida de recepción (HU-05) ---
    fecha_requerida = models.DateField("Fecha requerida de recepción")

    # --- Alternativas o productos sustitutos (HU-14) ---
    # La sección del ADM-F-22 se responde con un sí o un no. Por defecto es "no":
    # lo excepcional es que el solicitante conozca una alternativa. Si responde
    # que sí, tiene que decir cuál; un "sí" sin detalle no le sirve a compras.
    hay_sustitutos = models.BooleanField(
        "¿Existen productos o servicios sustitutos?",
        default=False,
    )
    sustitutos = models.TextField(
        "Productos o servicios sustitutos",
        blank=True,
        help_text="Qué alternativa sirve y en qué condiciones (marca, referencia, etc.).",
    )

    # --- Estado de la atención (HU-23) ---
    # No es editable desde un formulario cualquiera: solo cambia por las
    # transiciones permitidas, que dejan rastro en CambioEstado. Indexado porque
    # la bandeja filtra por él.
    estado = models.CharField(
        "Estado",
        max_length=ESTADO_MAX_LENGTH,
        choices=EstadoRequerimiento.choices,
        default=EstadoRequerimiento.RADICADO,
        db_index=True,
        editable=False,
    )

    class Meta:
        verbose_name = "Requerimiento"
        verbose_name_plural = "Requerimientos"
        ordering = ["-fecha_solicitud"]

    def __str__(self):
        return f"{self.consecutivo or 'Sin radicar'} - {self.solicitante}"

    def save(self, *args, **kwargs):
        # HU-16: el consecutivo se genera una sola vez, de forma atómica.
        if self.consecutivo:
            return super().save(*args, **kwargs)
        with transaction.atomic():
            self.consecutivo = SecuenciaRadicacion.siguiente_consecutivo()
            return super().save(*args, **kwargs)

    @property
    def total_estimado(self):
        """Suma de los totales de los ítems (HU-10).

        Se calcula sobre la base de datos, no en memoria, para que no dependa
        de que los ítems estén cargados.
        """
        return self.items.aggregate(total=models.Sum("total"))["total"] or Decimal("0.00")

    @property
    def tiene_items_sin_precio(self):
        """True si algún ítem no tiene precio de referencia (HU-10).

        El total sigue siendo válido, pero es parcial: sirve para advertirlo.
        """
        return self.items.filter(precio_referencia__isnull=True).exists()

    def estados_siguientes(self):
        """Estados a los que se puede pasar desde el actual (HU-23)."""
        return TRANSICIONES.get(self.estado, ())

    def cambiar_estado(self, nuevo, usuario, observacion=""):
        """Pasa el requerimiento a `nuevo` y deja el cambio en la bitácora (HU-23).

        La transición se valida contra el estado que hay en la base de datos,
        no contra el que trae este objeto en memoria: si dos analistas tienen
        la ficha abierta y los dos actúan, el segundo cambio se rechaza en vez
        de pisar al primero sin que nadie lo note. La fila se bloquea mientras
        tanto, y estado y bitácora se guardan juntos o no se guarda ninguno.
        """
        with transaction.atomic():
            actual = Requerimiento.objects.select_for_update().get(pk=self.pk)
            if nuevo not in TRANSICIONES.get(actual.estado, ()):
                destino = (
                    EstadoRequerimiento(nuevo).label
                    if nuevo in EstadoRequerimiento.values
                    else nuevo
                )
                raise TransicionNoPermitidaError(
                    f"Un requerimiento en «{actual.get_estado_display()}» no puede pasar a "
                    f"«{destino}».",
                    code="transicion_no_permitida",
                )
            anterior = actual.estado
            Requerimiento.objects.filter(pk=self.pk).update(estado=nuevo)
            self.estado = nuevo
            return CambioEstado.objects.create(
                requerimiento=self,
                estado_anterior=anterior,
                estado_nuevo=nuevo,
                observacion=(observacion or "").strip(),
                usuario=usuario,
            )

    def renumerar_items(self):
        """Deja la numeración de los ítems consecutiva desde 1 (HU-06).

        Se llama después de guardar el formset: si el solicitante elimina un
        ítem intermedio, los siguientes se corren para que no queden huecos.

        La renumeración se hace en dos pasadas —primero a números por encima
        del máximo actual y luego a 1..N— para no chocar con la restricción de
        unicidad mientras los valores viejos y nuevos se solapan.
        """
        items = list(self.items.order_by("numero", "pk"))
        if not items:
            return

        desplazamiento = max(item.numero for item in items)
        for posicion, item in enumerate(items, start=1):
            item.numero = desplazamiento + posicion
        Item.objects.bulk_update(items, ["numero"])

        for posicion, item in enumerate(items, start=1):
            item.numero = posicion
        Item.objects.bulk_update(items, ["numero"])

    def clean(self):
        super().clean()
        errores = {}

        # HU-03: la justificación no puede ser solo espacios. La cadena vacía ya la
        # rechaza la validación de campo (blank=False); no se duplica el mensaje.
        if self.justificacion and not self.justificacion.strip():
            errores["justificacion"] = "La justificación no puede quedar vacía."

        # HU-05: la fecha requerida no puede ser anterior a la fecha de solicitud.
        # Si el requerimiento aún no se ha guardado, fecha_solicitud todavía no
        # existe, así que se compara contra la fecha de hoy (que es lo que
        # auto_now_add asignará al guardar).
        fecha_base = self.fecha_solicitud or timezone.localdate()
        if self.fecha_requerida and self.fecha_requerida < fecha_base:
            errores["fecha_requerida"] = (
                "La fecha requerida no puede ser anterior a la fecha de solicitud."
            )

        # HU-14: si dice que hay sustitutos, debe describirlos.
        if self.hay_sustitutos and not (self.sustitutos or "").strip():
            errores["sustitutos"] = MENSAJE_SUSTITUTOS_OBLIGATORIOS

        if errores:
            raise ValidationError(errores)


class Item(models.Model):
    """Artículo o servicio solicitado dentro de un requerimiento (HU-06).

    Un requerimiento agrupa varios ítems para que el solicitante no tenga que
    radicar una solicitud por cada artículo. Al borrarse el requerimiento se
    borran sus ítems: un ítem no tiene sentido por fuera de su solicitud.
    """

    requerimiento = models.ForeignKey(
        Requerimiento,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Requerimiento",
    )
    # Lo asigna el sistema (ver Requerimiento.renumerar_items), no el usuario.
    numero = models.PositiveIntegerField(
        "N.º",
        default=1,
        help_text="Consecutivo del ítem dentro del requerimiento.",
    )
    # HU-07: entero mayor que cero. PositiveIntegerField admite el 0, así que
    # el mínimo real lo impone el validador.
    cantidad = models.PositiveIntegerField(
        "Cantidad",
        validators=[MinValueValidator(1, "La cantidad debe ser mayor que cero.")],
    )
    unidad_medida = models.ForeignKey(
        UnidadMedida,
        on_delete=models.PROTECT,
        related_name="items",
        verbose_name="Unidad de medida",
    )
    # TextField y no CharField: las descripciones reales son largas y de varias
    # líneas, y no deben truncarse (HU-07).
    descripcion = models.TextField("Descripción")

    # --- Precio y total (HU-10) ---
    # Opcional: el solicitante no siempre conoce el precio; cuando falta, el
    # ítem aporta cero al total y el requerimiento queda marcado como parcial.
    precio_referencia = models.DecimalField(
        "Precio unitario de referencia",
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0, "El precio no puede ser negativo.")],
    )
    # Calculado, nunca digitado: lo recalcula save() en cada guardado.
    total = models.DecimalField(
        "Total del ítem",
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
        editable=False,
    )

    # --- Especificaciones técnicas (HU-09) ---
    # Opcional: hay ítems (servicios, transportes) que no tienen ficha técnica.
    # Cuando existe, se guarda íntegra y con sus saltos de línea, porque es lo
    # que evita que compras adivine cuál referencia pedir.
    especificaciones_tecnicas = models.TextField(
        "Especificaciones técnicas",
        blank=True,
        help_text="Marca, modelo, referencia, rango, material, norma aplicable, etc.",
    )

    # --- Marcas de tratamiento especial (HU-08) ---
    # Van por defecto en False: lo excepcional es el ítem que sí las lleva.
    requiere_calibracion = models.BooleanField(
        "¿Requiere calibración?",
        default=False,
        help_text="El ítem debe entregarse con certificado de calibración vigente.",
    )
    es_reembolsable = models.BooleanField(
        "¿Es reembolsable?",
        default=False,
        help_text="La compra se factura a un tercero o se reembolsa al solicitante.",
    )

    class Meta:
        verbose_name = "Ítem"
        verbose_name_plural = "Ítems"
        ordering = ["requerimiento", "numero"]
        constraints = [
            models.UniqueConstraint(
                fields=["requerimiento", "numero"],
                name="item_numero_unico_por_requerimiento",
            ),
        ]

    def __str__(self):
        return f"Ítem {self.numero} del requerimiento #{self.requerimiento_id}"

    def save(self, *args, **kwargs):
        # El total nunca lo digita el usuario: se recalcula en cada guardado.
        self.total = self.calcular_total()
        campos = kwargs.get("update_fields")
        if campos is not None and "total" not in campos:
            kwargs["update_fields"] = [*campos, "total"]
        super().save(*args, **kwargs)

    def calcular_total(self):
        """Total del ítem: la cantidad por el precio de referencia (HU-10)."""
        if self.precio_referencia is None or self.cantidad is None:
            return Decimal("0.00")
        return (self.precio_referencia * self.cantidad).quantize(Decimal("0.01"))

    def clean(self):
        super().clean()
        # HU-07: la descripción es obligatoria y no puede ser solo espacios.
        if self.descripcion is not None and not self.descripcion.strip():
            raise ValidationError({"descripcion": "La descripción no puede quedar vacía."})

        # HU-09: unas especificaciones con solo espacios equivalen a no tenerlas.
        if self.especificaciones_tecnicas and not self.especificaciones_tecnicas.strip():
            self.especificaciones_tecnicas = ""


class ProveedorSugerido(models.Model):
    """Proveedor que el solicitante sugiere para cotizar (HU-13).

    Es texto libre a propósito: no existe un maestro de proveedores y compras
    valida y da de alta al proveedor cuando inicia el contacto formal
    (acuerdo n.º 3 con el cliente). Un requerimiento admite hasta
    ``MAX_PROVEEDORES_SUGERIDOS``; sugerir es opcional.
    """

    requerimiento = models.ForeignKey(
        Requerimiento,
        on_delete=models.CASCADE,
        related_name="proveedores_sugeridos",
        verbose_name="Requerimiento",
    )
    orden = models.PositiveSmallIntegerField(
        "Orden",
        validators=[
            MinValueValidator(1),
            MaxValueValidator(MAX_PROVEEDORES_SUGERIDOS),
        ],
        help_text="Posición del proveedor en la lista del solicitante (1 a 3).",
    )
    nombre = models.CharField("Nombre o razón social", max_length=150)
    telefono = models.CharField("Teléfono de contacto", max_length=30)
    observaciones = models.CharField(
        "Observaciones",
        max_length=200,
        blank=True,
        help_text="Contacto, sede, por qué se sugiere, etc.",
    )

    class Meta:
        verbose_name = "Proveedor sugerido"
        verbose_name_plural = "Proveedores sugeridos"
        ordering = ["requerimiento", "orden"]
        constraints = [
            models.UniqueConstraint(
                fields=["requerimiento", "orden"],
                name="proveedor_orden_unico_por_requerimiento",
            ),
        ]

    def __str__(self):
        return f"{self.nombre} ({self.telefono})"


class CambioEstado(models.Model):
    """Bitácora de los cambios de estado de un requerimiento (HU-23, HU-24).

    Cada transición queda registrada con quién la hizo y cuándo. La observación
    es la que hace posible la devolución (HU-24): el analista dice qué falta y
    el solicitante lo lee en el sistema, sin recurrir al correo. Es opcional en
    los demás cambios.
    """

    requerimiento = models.ForeignKey(
        Requerimiento,
        on_delete=models.CASCADE,
        related_name="cambios_estado",
        verbose_name="Requerimiento",
    )
    estado_anterior = models.CharField(
        "Estado anterior",
        max_length=ESTADO_MAX_LENGTH,
        choices=EstadoRequerimiento.choices,
    )
    estado_nuevo = models.CharField(
        "Estado nuevo",
        max_length=ESTADO_MAX_LENGTH,
        choices=EstadoRequerimiento.choices,
    )
    observacion = models.TextField("Observación", blank=True)
    # SET_NULL: si se da de baja la cuenta, el cambio sigue en la bitácora.
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cambios_estado",
        verbose_name="Realizado por",
    )
    fecha = models.DateTimeField("Fecha", auto_now_add=True)

    class Meta:
        verbose_name = "Cambio de estado"
        verbose_name_plural = "Cambios de estado"
        # Cronológico: la bitácora se lee como la historia del requerimiento.
        ordering = ["fecha", "pk"]
        indexes = [models.Index(fields=["requerimiento", "fecha"])]

    def __str__(self):
        return (
            f"{self.requerimiento.consecutivo}: "
            f"{self.get_estado_anterior_display()} → {self.get_estado_nuevo_display()}"
        )


def ruta_adjunto(instancia, nombre):
    """Ruta donde se guarda un adjunto (HU-11).

    Los archivos de un requerimiento quedan juntos, bajo su consecutivo, y con
    un nombre aleatorio: el original lo escoge el usuario, puede chocar con el
    de otro adjunto o traer caracteres que el sistema de archivos no admite. Se
    conserva aparte, en `nombre_original`, para mostrarlo.
    """
    extension = Path(nombre).suffix.lower()
    return f"adjuntos/{instancia.requerimiento.consecutivo}/{uuid.uuid4().hex}{extension}"


class Adjunto(models.Model):
    """Fotografía o documento de soporte de un requerimiento (HU-11).

    Fichas técnicas, cotizaciones de referencia o la foto del artículo: lo que
    evita que compras tenga que adivinar qué se está pidiendo.
    """

    class Tipo(models.TextChoices):
        FOTO = "foto", "Fotografía"
        DOCUMENTO = "documento", "Documento"

    requerimiento = models.ForeignKey(
        Requerimiento,
        on_delete=models.CASCADE,
        related_name="adjuntos",
        verbose_name="Requerimiento",
    )
    archivo = models.FileField("Archivo", upload_to=ruta_adjunto, max_length=255)
    nombre_original = models.CharField("Nombre del archivo", max_length=255)
    tipo = models.CharField("Tipo", max_length=12, choices=Tipo.choices)
    tamano = models.PositiveIntegerField("Tamaño (bytes)")
    subido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adjuntos_subidos",
        verbose_name="Subido por",
    )
    subido_en = models.DateTimeField("Subido el", auto_now_add=True)

    class Meta:
        verbose_name = "Adjunto"
        verbose_name_plural = "Adjuntos"
        ordering = ["subido_en", "pk"]

    def __str__(self):
        return self.nombre_original

    @property
    def extension(self):
        """Extensión en mayúsculas (PDF, XLSX), para rotular los documentos."""
        return Path(self.nombre_original).suffix.lstrip(".").upper()


@receiver(post_delete, sender=Adjunto)
def borrar_archivo_del_adjunto(sender, instance, **kwargs):
    """Borra del disco el archivo de un adjunto eliminado (HU-11).

    Django borra la fila pero no el archivo, y con el tiempo el disco se llena
    de adjuntos que nada apunta. Se espera a que la transacción se confirme: si
    se deshiciera, la fila volvería y su archivo tiene que seguir ahí. También
    cubre el borrado en cascada de un requerimiento entero.
    """
    archivo = instance.archivo
    if archivo:
        transaction.on_commit(lambda: archivo.storage.delete(archivo.name))
