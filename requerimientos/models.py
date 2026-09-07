from django.core.exceptions import ValidationError
from django.db import models

JUSTIFICACION_MAX_LENGTH = 1000


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
        "Orden de despliegue", default=0,
        help_text="Controla el orden en que aparece la prioridad en el selector.",
    )

    class Meta:
        verbose_name = "Prioridad"
        verbose_name_plural = "Prioridades"
        ordering = ["orden"]

    def __str__(self):
        return self.nombre.title()


def _prioridad_media_pk():
    return Prioridad.objects.filter(nombre=Prioridad.MEDIA).values_list("pk", flat=True).first()


class Requerimiento(models.Model):
    solicitante = models.CharField("Nombre del solicitante", max_length=150)
    area = models.ForeignKey(
        Area, on_delete=models.PROTECT, related_name="requerimientos",
        verbose_name="Área o proyecto",
    )
    centro_costo = models.ForeignKey(
        CentroCosto, on_delete=models.PROTECT, related_name="requerimientos",
        verbose_name="Centro de costo",
    )
    # auto_now_add + editable=False: se registra sola y el usuario no puede tocarla.
    fecha_solicitud = models.DateField("Fecha de solicitud", auto_now_add=True, editable=False)

    # --- Justificación (HU-03) ---
    justificacion = models.TextField("Justificación", max_length=JUSTIFICACION_MAX_LENGTH)

    # --- Prioridad (HU-04) ---
    prioridad = models.ForeignKey(
        Prioridad, on_delete=models.PROTECT, related_name="requerimientos",
        verbose_name="Prioridad", db_index=True, default=_prioridad_media_pk,
    )

    class Meta:
        verbose_name = "Requerimiento"
        verbose_name_plural = "Requerimientos"
        ordering = ["-fecha_solicitud"]

    def __str__(self):
        return f"Requerimiento #{self.pk} - {self.solicitante}"

    def clean(self):
        super().clean()
        if self.justificacion is not None and not self.justificacion.strip():
            raise ValidationError({"justificacion": "La justificación no puede quedar vacía."})
