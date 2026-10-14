from django.contrib import admin

from .models import (
    Adjunto,
    Area,
    CambioEstado,
    CentroCosto,
    Item,
    Prioridad,
    ProveedorSugerido,
    Requerimiento,
    SecuenciaRadicacion,
    UnidadMedida,
)


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ("nombre",)
    search_fields = ("nombre",)


@admin.register(CentroCosto)
class CentroCostoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre")
    search_fields = ("codigo", "nombre")


@admin.register(UnidadMedida)
class UnidadMedidaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre")
    search_fields = ("codigo", "nombre")


@admin.register(Prioridad)
class PrioridadAdmin(admin.ModelAdmin):
    list_display = ("nombre", "orden")
    ordering = ("orden",)


@admin.register(SecuenciaRadicacion)
class SecuenciaRadicacionAdmin(admin.ModelAdmin):
    list_display = ("anio", "ultimo_numero")
    readonly_fields = ("anio", "ultimo_numero")


class ItemInline(admin.TabularInline):
    """Los ítems se editan dentro de su requerimiento (HU-06)."""

    model = Item
    extra = 1
    fields = (
        "numero",
        "cantidad",
        "unidad_medida",
        "descripcion",
        "especificaciones_tecnicas",
        "precio_referencia",
        "total",
        "requiere_calibracion",
        "es_reembolsable",
    )
    readonly_fields = ("total",)


class ProveedorSugeridoInline(admin.TabularInline):
    """Proveedores que sugirió el solicitante (HU-13)."""

    model = ProveedorSugerido
    extra = 0
    max_num = 3
    fields = ("orden", "nombre", "telefono", "observaciones")


class AdjuntoInline(admin.TabularInline):
    """Adjuntos del requerimiento (HU-11), solo para consulta.

    Se suben desde el formulario de radicación, que es el que valida tipo,
    tamaño y contenido; el panel no los reemplaza para no saltarse esas reglas.
    """

    model = Adjunto
    extra = 0
    can_delete = True
    fields = ("nombre_original", "tipo", "tamano", "subido_por", "subido_en")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


class CambioEstadoInline(admin.TabularInline):
    """Bitácora de estados (HU-23), solo para consulta.

    El estado se cambia desde la ficha, que valida la transición y deja
    rastro; editar la bitácora a mano en el panel la volvería poco confiable.
    """

    model = CambioEstado
    extra = 0
    can_delete = False
    fields = ("fecha", "estado_anterior", "estado_nuevo", "usuario", "observacion")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Requerimiento)
class RequerimientoAdmin(admin.ModelAdmin):
    list_display = (
        "consecutivo",
        "estado",
        "solicitante",
        "area",
        "centro_costo",
        "prioridad",
        "fecha_solicitud",
        "fecha_requerida",
        "total_estimado",
    )
    list_filter = ("estado", "prioridad", "area", "centro_costo")
    search_fields = ("consecutivo", "solicitante", "justificacion")
    date_hierarchy = "fecha_solicitud"
    readonly_fields = ("consecutivo", "estado", "fecha_solicitud")
    inlines = [ItemInline, ProveedorSugeridoInline, AdjuntoInline, CambioEstadoInline]
