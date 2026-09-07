from django.contrib import admin

from .models import Area, CentroCosto, Prioridad, Requerimiento


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


@admin.register(Requerimiento)
class RequerimientoAdmin(admin.ModelAdmin):
    list_display = ("id", "solicitante", "area", "centro_costo", "prioridad", "fecha_solicitud")
    list_filter = ("area", "centro_costo", "prioridad")
    search_fields = ("solicitante", "justificacion")
    list_filter = ("area", "centro_costo")
    date_hierarchy = "fecha_solicitud"
    readonly_fields = ("fecha_solicitud",)
