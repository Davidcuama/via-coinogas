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
from django.contrib.auth.views import LogoutView
from django.urls import include, path

from requerimientos.views import IngresoView, PortadaView

urlpatterns = [
    # La raíz es pública: presenta el sistema a quien no ha entrado y manda a
    # su pantalla a quien ya tiene sesión.
    path("", PortadaView.as_view(), name="portada"),
    path("ingresar/", IngresoView.as_view(), name="ingresar"),
    path("salir/", LogoutView.as_view(), name="salir"),
    path("admin/", admin.site.urls),
    path("requerimientos/", include("requerimientos.urls")),
]
