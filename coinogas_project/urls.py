from django.contrib import admin
from django.urls import path
from core.views import formulario_requerimiento

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', formulario_requerimiento, name='formulario_en_blanco'),
]