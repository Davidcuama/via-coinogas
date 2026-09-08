# VIA Coinogas

**Sistema de radicación digital de requerimientos de compra**

Proyecto Integrador 2 · Universidad EAFIT · Ingeniería de Sistemas

---

## El problema

Coinogas radica sus requerimientos de compra diligenciando a mano el formato **ADM-F-22 «Manifestación Requerimiento de Compra»** en Excel y enviándolo por correo. El área de compras vuelve a transcribir esa información a un archivo consolidado.

Ese proceso no deja trazabilidad, arrastra errores cuando alguien reutiliza un formato antiguo, y obliga a digitar dos veces la misma información.

## La solución

Una aplicación web que reemplaza el archivo Excel por un formulario conectado a una base de datos central, con validación de campos obligatorios, adjunto de fotografías y una bandeja centralizada para el área de compras. Sobre esa base se expone una capa analítica de solo lectura que alimenta un tablero de indicadores en Power BI.

---

## Documentación

Toda la documentación del proyecto está en la **[Wiki](../../wiki)**:

- [Generalidades del Proyecto](../../wiki/1-Generalidades-del-Proyecto)
- [Determinación de Necesidades](../../wiki/2-Determinacion-de-Necesidades)
- [Story Mapping y Backlog](../../wiki/3-Story-Mapping-y-Backlog)
- [Acuerdos con el cliente](../../wiki/Acuerdos-con-el-Cliente)
- [Calidad del Software](../../wiki/Calidad-del-Software) — estándar de nombramiento, análisis estático y estrategia de ramas
- [Glosario](../../wiki/Glosario)

El **backlog** vive en las [Issues](../../issues), etiquetadas por épica y prioridad, y organizadas en milestones por sprint.

---

## Stack técnico

| Capa | Tecnología |
|---|---|
| Backend | Django 5 (Python) |
| Base de datos | PostgreSQL |
| Frontend | Plantillas de Django + Bootstrap 5 |
| Imágenes | Pillow |
| Analítica | Vistas SQL de solo lectura + Microsoft Power BI |
| Despliegue | Docker |

---

## Equipo

| Integrante | Rol |
|---|---|
| David Cuadros | Product Owner |
| Juan Esteban Villada | Scrum Master · Backend |
| Juan Camilo Gómez | Backend · Analítica |
| Juan Pablo Posso | Frontend · Calidad |

**Cliente:** Coinogas — Sergio Andrés Quintero Albarracín

---

## Puesta en marcha local

```bash
python -m venv .venv && source .venv/bin/activate   # en Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                                # ajustar credenciales de PostgreSQL
pre-commit install                                  # activa Ruff antes de cada commit
python manage.py migrate
python manage.py cargar_catalogos
python manage.py runserver
```

Para correr las pruebas sin PostgreSQL: `DB_ENGINE=sqlite python manage.py test`.

## Calidad del código

| Herramienta | Para qué | Comando |
|---|---|---|
| Ruff (linter) | Errores, imports, seguridad y **estándar de nombramiento PEP 8** | `ruff check .` |
| Ruff (formatter) | Formato uniforme, compatible con Black | `ruff format .` |
| pre-commit | Ejecuta lo anterior automáticamente antes de cada commit | `pre-commit run --all-files` |
| GitHub Actions | Corre Ruff, pip-audit y las pruebas en cada PR | automático |

La configuración vive en `pyproject.toml` y la justificación en la [Wiki](../../wiki/Calidad-del-Software).

## Flujo de trabajo (GitHub Flow)

1. Cada historia de usuario es una issue con su etiqueta de épica, prioridad y estimación.
2. Se trabaja en una rama por historia: `feature/HU-XX-descripcion-corta`.
3. El pull request referencia la issue con `Closes #N` y requiere revisión de al menos un compañero.
4. Se integra a `main` solo con la revisión aprobada **y el pipeline de CI en verde**.

## Convención de commits

```
HU-XX: descripción breve en imperativo

Detalle opcional de qué se hizo y por qué.
```
