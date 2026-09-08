from django.contrib import admin

from .models import Area, CentroCosto, Prioridad, Requerimiento, SecuenciaRadicacion


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ("nombre",)
    search_fields = ("nombre",)


@admin.register(CentroCosto)
class CentroCostoAdmin(admin.ModelAdmin):
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
