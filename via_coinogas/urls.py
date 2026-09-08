"""
URL configuration for via_coinogas project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    # La raíz lleva al formulario: hoy es la única pantalla de entrada del
    # sistema. Redirección temporal a propósito, porque cuando exista la
    # bandeja (HU-20) el destino cambia según el rol.
    path(
        "",
        RedirectView.as_view(pattern_name="requerimientos:crear", permanent=False),
        name="inicio",
    ),
    path("admin/", admin.site.urls),
    path("requerimientos/", include("requerimientos.urls")),
]
