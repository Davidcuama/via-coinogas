# Casos de prueba funcionales · Sprint 1

Casos de prueba (CP) del sistema de radicación **VIA Compras**, redactados en
formato BDD. Cada CP es una situación de negocio, no un detalle de
implementación: describe lo que el solicitante o el área de compras espera que
ocurra, y por eso sigue siendo válido aunque cambie la tecnología por debajo.

Cada CP indica además la prueba automatizada que lo cubre, para que la ejecución
sea reproducible y no dependa de que alguien recuerde repetirla a mano.

**Cómo ejecutar la suite completa:**

```bash
python manage.py test
```

Sin PostgreSQL instalado:

```bash
DB_ENGINE=sqlite python manage.py test
```

---

## Módulo: radicación de requerimientos de compra

### CP-01 · Carga inicial del formulario en blanco (HU-01)

> **Dado** que un usuario con perfil de solicitante ha ingresado al sistema y
> abre la ruta de creación de requerimientos (`/requerimientos/nuevo/`),
> **cuando** la página termina de cargar,
> **entonces** todos los campos del formato ADM-F-22 aparecen vacíos, sin
> arrastrar nada de un requerimiento anterior, la tabla de ítems muestra una
> sola fila en blanco y la fecha de solicitud se registrará automáticamente con
> el día en curso al radicar.

**Precisión deliberada:** el único campo precargado es el nombre del
solicitante, que se propone desde la cuenta con la que se ingresó y sigue siendo
editable. No es información de un requerimiento anterior —que es lo que la
historia prohíbe arrastrar—, sino la identidad de quien está diligenciando.

**Cubierto por:** `BorradorRequerimientoTests.test_sin_borrador_el_formulario_abre_en_blanco_y_sin_aviso`,
`AutoriaRequerimientoTests.test_el_formulario_propone_el_nombre_de_la_cuenta`,
`RequerimientoModelTests.test_fecha_solicitud_se_asigna_automaticamente`.

---

### CP-02 · Validación de campos obligatorios al radicar (HU-15)

> **Dado** un formulario con campos obligatorios sin diligenciar (solicitante,
> área, centro de costo, justificación, prioridad, fecha requerida o los datos
> del ítem),
> **cuando** el usuario pulsa «Radicar requerimiento»,
> **entonces** el sistema bloquea el envío, no crea ningún registro, resalta
> cada campo faltante con su mensaje y conserva intacto lo que ya se había
> diligenciado.

**Nota de diseño:** la validación del navegador es solo retroalimentación
inmediata. La fuente de verdad es el servidor: una petición enviada sin pasar
por el formulario HTML se rechaza igual.

**Cubierto por:** `ValidacionCamposObligatoriosTests` (9 pruebas, incluida
`test_validacion_aplica_a_peticiones_directas_sin_navegador`),
`ItemDatosBasicosTests.test_formulario_de_item_exige_los_tres_campos`,
`RequerimientoVistaTests.test_radicar_sin_ningun_item_es_rechazado`.

---

### CP-03 · Guardado y reanudación de borradores (HU-18)

> **Dado** un requerimiento diligenciado a medias, al que todavía le faltan
> campos obligatorios,
> **cuando** el usuario pulsa «Guardar borrador» y más tarde vuelve a abrir el
> formulario,
> **entonces** el sistema recupera de la sesión lo que había escrito —encabezado
> e ítems—, muestra el aviso de borrador retomado con su fecha y ofrece
> continuar o descartarlo.

**Cubierto por:** `BorradorRequerimientoTests` (22 pruebas), entre ellas
`test_el_borrador_conserva_los_items` y
`test_el_borrador_es_privado_de_cada_solicitante`.

---

### CP-04 · Radicación exitosa y consecutivo (HU-16, HU-17)

> **Dado** un requerimiento con todos los campos obligatorios válidos y al menos
> un ítem completo,
> **cuando** el usuario confirma la radicación,
> **entonces** el encabezado y sus ítems se guardan en una sola transacción, se
> asigna un consecutivo único con formato `REQ-AAAA-NNNN`, se descarta el
> borrador, se avisa por correo al área de compras y el navegador queda en la
> pantalla de confirmación (patrón Post/Redirect/Get), de modo que recargar no
> duplica el requerimiento.

**Cubierto por:** `ConsecutivoRadicacionTests`, `ConsecutivoConcurrenciaTests`
(dos radicaciones simultáneas no repiten número), `ConfirmacionRadicacionTests`,
`NotificacionAreaComprasTests`, `TotalesTests.test_totales_se_calculan_al_radicar_desde_el_formulario`.

---

### CP-05 · Comportamiento en móvil y escritorio

> **Dado** un usuario que abre el sistema desde distintos anchos de pantalla,
> **cuando** recorre el formulario y la tabla de ítems,
> **entonces** la maquetación se adapta sin desbordamiento horizontal de la
> página: la tabla de ítems desplaza dentro de su propio contenedor y los datos
> del perfil se ocultan en la barra superior para dejar sitio a la navegación.

**Verificación manual (ejecutada a 375 px y a 1280 px):** sin scroll horizontal
de página en ninguna de las dos resoluciones; la tabla de ítems conserva su
scroll propio; el sello del formato baja a su propia línea en móvil.

**Cubierto por:** `IdentidadVisualTests.test_declara_el_viewport` comprueba la
etiqueta `meta viewport`, sin la cual el diseño responsivo no se activa en
celular. El resto de este CP es inspección visual: no se automatiza porque
verificar el renderizado real exige un navegador de verdad.

---

### CP-06 · Descarte del borrador (HU-18)

> **Dado** un formulario abierto con un borrador retomado,
> **cuando** el usuario pulsa «Descartar»,
> **entonces** la sesión se limpia por completo y el formulario se recarga en
> blanco, sin el aviso de borrador.

**Cubierto por:** `BorradorRequerimientoTests.test_descartar_borrador_deja_el_formulario_en_blanco`.

---

## Módulo: acceso y perfiles

### CP-07 · Página de inicio pública

> **Dado** un visitante sin sesión,
> **cuando** abre la raíz del sitio,
> **entonces** ve la presentación del sistema —qué reemplaza y qué hace cada
> perfil— y un acceso al ingreso; y si ya tenía sesión abierta, se le lleva
> directamente a su pantalla de trabajo sin pasar por la presentación.

**Cubierto por:** `PortadaTests` (4 pruebas).

---

### CP-08 · Ingreso y enrutamiento por perfil

> **Dado** un usuario con cuenta en el sistema,
> **cuando** ingresa con sus credenciales,
> **entonces** cae en la pantalla que le corresponde: el solicitante en el
> formulario de radicación, el analista de compras en la bandeja y el
> administrador en el panel de administración; si había intentado abrir una
> pantalla concreta, se le devuelve a ella.

**Cubierto por:** `IngresoTests` (8 pruebas), `PerfilesTests` (4 pruebas).

---

### CP-09 · Aislamiento de la información entre solicitantes

> **Dado** dos solicitantes distintos con requerimientos radicados,
> **cuando** cada uno consulta «Mis requerimientos» o intenta abrir la
> confirmación de un consecutivo ajeno,
> **entonces** cada quien ve únicamente lo suyo, y el área de compras ve todo.

**Por qué importa:** el consecutivo es adivinable (`REQ-2026-0001`), así que la
pantalla de confirmación no puede quedar abierta a cualquiera que tenga sesión.

**Cubierto por:** `AutoriaRequerimientoTests` (4 pruebas), `BandejaTests`
(5 pruebas), `AccesoSinSesionTests` (2 pruebas).

---

## Reporte de ejecución

| Fecha | Rama | Resultado |
|---|---|---|
| 2026-09-09 | `feature/portada-login-y-perfiles` | 146 pruebas · 145 OK · 1 omitida |

La prueba omitida es `ConsecutivoConcurrenciaTests`, que solo corre sobre
PostgreSQL porque necesita bloqueos de fila reales; en SQLite no hay concurrencia
que probar. En el pipeline de integración continua sí se ejecuta.

**Bugs encontrados y corregidos durante la ejecución de estos casos:**

1. Un comentario de plantilla de dos líneas se imprimía como texto en la
   página: los comentarios `{# #}` de Django son de una sola línea.
2. La bandeja mostraba «0 en total» habiendo filas, por una cadena de filtros
   mal encadenada (`|default:` seguido de `|length`).
3. Los totales salían sin separador de miles.

**Pendiente de automatizar:** la verificación visual del CP-05 en navegadores
distintos (Chrome, Edge, Firefox). Hoy se hace a mano; automatizarla exige una
herramienta de navegador dirigido, que no está en el alcance de este sprint.
