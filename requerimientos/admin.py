from django.contrib import admin

from .models import (
    Area,
    CentroCosto,
    Item,
    Prioridad,
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
        "requiere_calibracion",
        "es_reembolsable",
    )


@admin.register(Requerimiento)
class RequerimientoAdmin(admin.ModelAdmin):
    list_display = (
        "consecutivo",
        "solicitante",
        "area",
        "centro_costo",
        "prioridad",
        "fecha_solicitud",
        "fecha_requerida",
    )
    list_filter = ("prioridad", "area", "centro_costo")
    search_fields = ("consecutivo", "solicitante", "justificacion")
    date_hierarchy = "fecha_solicitud"
    readonly_fields = ("consecutivo", "fecha_solicitud")
    inlines = [ItemInline]
