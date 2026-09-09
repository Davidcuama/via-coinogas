from django.shortcuts import render


def formulario_requerimiento(request):
    return render(request, "form_radicacion.html")
