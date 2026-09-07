from django.contrib import admin

from .models import Area, CentroCosto, Requerimiento


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ("nombre",)
    search_fields = ("nombre",)


@admin.register(CentroCosto)
class CentroCostoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre")
    search_fields = ("codigo", "nombre")


@admin.register(Requerimiento)
class RequerimientoAdmin(admin.ModelAdmin):
    list_display = ("id", "solicitante", "area", "centro_costo", "fecha_solicitud")
    search_fields = ("solicitante", "justificacion")
    list_filter = ("area", "centro_costo")
    date_hierarchy = "fecha_solicitud"
    readonly_fields = ("fecha_solicitud",)
