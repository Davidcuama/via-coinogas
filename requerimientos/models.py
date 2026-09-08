from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

JUSTIFICACION_MAX_LENGTH = 1000

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


class Requerimiento(models.Model):
    # --- Consecutivo de radicación (HU-16) ---
    # Se asigna en save() la primera vez que se guarda; el usuario nunca lo edita.
    consecutivo = models.CharField(
        "Consecutivo de radicación",
        max_length=CONSECUTIVO_MAX_LENGTH,
        unique=True,
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
    descripcion = models.TextField("Descripción")

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
