# Manual de Usuario — Sistema VIA Coinogas

> **Guía Oficial de Operación para Solicitantes y Analistas de Compras**  
> **Sistema Digital de Requerimientos de Compra (Reemplazo del Formato ADM-F-22)**  
> **Coinogas S.A. E.S.P. — Transportando Bienestar**  
> **Versión del Sistema:** 1.0 (Entrega Final - Sprint 3)

---

## Portada y Propósito del Manual

El presente manual tiene como objetivo brindar a todos los colaboradores de **Coinogas S.A. E.S.P.** una guía clara, visual y paso a paso para el uso de la plataforma web **VIA Coinogas**. 

Este sistema reemplaza de manera definitiva el diligenciamiento manual del formato Excel *«ADM-F-22: Requerimiento de Compra de Bienes y Servicios»*, centralizando todas las solicitudes en una base de datos segura, agilizando los tiempos de cotización y permitiendo hacer seguimiento en tiempo real al estado de cada pedido.

---

## Índice General

1. [Primeros Pasos e Ingreso al Sistema](#1-primeros-pasos-e-ingreso-al-sistema)
2. [Módulo del Solicitante](#2-módulo-del-solicitante)
   - [2.1 Cómo radicar un nuevo requerimiento de compra](#21-cómo-radicar-un-nuevo-requerimiento-de-compra)
   - [2.2 Cómo adjuntar fotografías y fichas técnicas](#22-cómo-adjuntar-fotografías-y-fichas-técnicas)
   - [2.3 Guardar y reanudar borradores](#23-guardar-y-reanudar-borradores)
   - [2.4 Consulta y seguimiento en «Mis requerimientos»](#24-consulta-y-seguimiento-en-mis-requerimientos)
   - [2.5 Cómo corregir y reenviar un requerimiento devuelto](#25-cómo-corregir-y-reenviar-un-requerimiento-devuelto)
3. [Módulo del Área de Compras](#3-módulo-del-área-de-compras)
   - [3.1 Gestión de la bandeja de entrada y filtros](#31-gestión-de-la-bandeja-de-entrada-y-filtros)
   - [3.2 Consulta de la ficha completa del requerimiento](#32-consulta-de-la-ficha-completa-del-requerimiento)
   - [3.3 Cambio de estado de un requerimiento](#33-cambio-de-estado-de-un-requerimiento)
   - [3.4 Devolución al solicitante con observaciones](#34-devolución-al-solicitante-con-observaciones)
4. [Módulo de Analítica y Tablero de Indicadores](#4-módulo-de-analítica-y-tablero-de-indicadores)
   - [4.1 Consulta de indicadores en la aplicación web](#41-consulta-de-indicadores-en-la-aplicación-web)
   - [4.2 Indicador de Tiempo Promedio de Atención](#42-indicador-de-tiempo-promedio-de-atención)
   - [4.3 Indicador de Tasa de Devoluciones](#43-indicador-de-tasa-de-devoluciones)
   - [4.4 Conexión con Power BI Desktop](#44-conexión-con-power-bi-desktop)
5. [Preguntas Frecuentes (FAQ)](#5-preguntas-frecuentes-faq)
6. [Canales de Soporte y Contacto](#6-canales-de-soporte-y-contacto)

---

## 1. Primeros Pasos e Ingreso al Sistema

Para acceder a VIA Coinogas:
1. Abra su navegador web (Google Chrome, Microsoft Edge o Safari en móvil) e ingrese a la dirección corporativa: `https://compras.coinogas.com/` (o dirección local suministrada por el área de TI).
2. En la pantalla de bienvenida, haga clic en el botón **«Ingresar»**.
3. Ingrese su usuario corporativo y contraseña asignada.

![Pantalla de inicio de sesión de VIA Coinogas](captura-01-login.png)

Una vez autenticado:
* Los **Solicitantes** serán dirigidos directamente al formulario de radicación de requerimientos.
* Los **Analistas de Compras** ingresarán directamente a su bandeja de gestión de solicitudes.

---

## 2. Módulo del Solicitante

### 2.1 Cómo radicar un nuevo requerimiento de compra
Para solicitar materiales, repuestos o servicios:

1. Haga clic en **«Radicar»** en la barra superior.
2. Complete la sección de **Encabezado**:
   * **Nombre del solicitante:** Se completa automáticamente con su nombre, pero puede modificarlo si radica por un compañero.
   * **Área o proyecto:** Seleccione la gerencia o proyecto al que pertenece la necesidad.
   * **Centro de costo:** Escoja el código presupuestal correspondiente (ej. *CC-100 Planta Medellín*).
   * **Prioridad:** Seleccione *Alta*, *Media* o *Baja*. Recuerde que la prioridad *Alta* debe estar debidamente sustentada en la justificación.
   * **Fecha requerida de recepción:** Indique la fecha límite en la que requiere el bien o servicio en sede o campo (no puede ser anterior a la fecha de hoy).
   * **Justificación:** Explique de manera clara y precisa la necesidad operativa (motivo del cambio, reposición, falla técnica o auditoría).

![Sección de encabezado y justificación del requerimiento](captura-02-encabezado.png)

3. Ingrese los **Artículos o Servicios Solicitados (Ítems)**:
   * Por cada artículo, indique la **Cantidad**, **Unidad de medida** (Unidad, Metro, Galón, Caja, Servicio, etc.) y una **Descripción detallada**.
   * Si conoce un valor estimado de mercado, complete el **Precio unitario de referencia**. El sistema calculará el total estimado automáticamente.
   * Active las casillas especiales si aplica: *¿Requiere calibración?* (para instrumentos que exigen certificado de metrología) o *¿Es reembolsable?*.
   * Para solicitar más artículos en el mismo requerimiento, haga clic en **«+ Agregar otro ítem»**.

![Tabla dinámica de artículos con cálculo de totales](captura-03-items.png)

4. **Alternativas y Proveedores sugeridos:**
   * Indique si existen productos sustitutos que puedan servir en caso de no hallar la marca original.
   * Si conoce empresas o contactos donde se pueda cotizar el artículo, agregue hasta 3 proveedores sugeridos con su nombre y teléfono.

5. **Envío y confirmación:**
   * Haga clic en **«Radicar requerimiento»**.
   * Se abrirá un aviso de confirmación con el resumen de lo diligenciado para verificar que no haya errores. Confirme el envío.
   * El sistema le mostrará la pantalla de confirmación con su **Consecutivo de Radicación único** (ejemplo: `REQ-2026-0042`).

![Pantalla de confirmación con consecutivo asignado](captura-04-confirmacion.png)

---

### 2.2 Cómo adjuntar fotografías y fichas técnicas
VIA Coinogas permite adjuntar fotos de la placa de los equipos o fichas en PDF para evitar cotizaciones equivocadas:

1. En la parte inferior del formulario de radicación, localice la sección **«Documentos y fotos de soporte»**.
2. **Desde el computador:** Arrastre los archivos o haga clic en «Seleccionar archivos». Puede subir hasta 5 archivos (máximo 10 MB cada uno) en formatos PDF, JPG, PNG o Excel.
3. **Desde el celular:** Pulse el botón verde **«Tomar foto con la cámara»**. La cámara del teléfono se abrirá directamente para capturar el repuesto en campo o almacén.
4. Antes de enviar, verá las miniaturas de sus imágenes cargadas. Si se equivocó en una foto, haga clic en la «X» para removerla.

![Carga de adjuntos y toma de fotografía desde teléfono móvil](captura-05-adjuntos.png)

---

### 2.3 Guardar y reanudar borradores
Si empezó a llenar un requerimiento pero le falta verificar un número de parte o medida:

1. Haga clic en **«Guardar borrador»** en la parte inferior del formulario.
2. Podrá cerrar la ventana o apagar el equipo tranquilamente.
3. Al volver a ingresar a «Radicar», la plataforma le informará con un banner azul: *«Retomaste un borrador guardado»*, recuperando todos los textos, ítems y proveedores que había ingresado.
4. Si ya no necesita esa solicitud, pulse **«Descartar borrador»** para reiniciar en blanco.

![Aviso de borrador recuperado en el formulario](captura-06-borrador.png)

---

### 2.4 Consulta y seguimiento en «Mis requerimientos»
Para conocer en qué etapa va cada uno de sus pedidos:

1. En el menú superior, haga clic en **«Mis requerimientos»**.
2. Visualizará una tabla con el consecutivo, fecha, área, total de ítems y el **estado actual**:
   * <span style="background:#e7f0f8; color:#005a90; padding:2px 8px; border-radius:4px; font-weight:600;">Radicado</span>: Su solicitud fue recibida por compras.
   * <span style="background:#eae8f7; color:#54479b; padding:2px 8px; border-radius:4px; font-weight:600;">En revisión</span>: Un analista está validando las especificaciones.
   * <span style="background:#e8f6ec; color:#b85a18; padding:2px 8px; border-radius:4px; font-weight:600;">En cotización</span>: El requerimiento se encuentra formalmente con proveedores.
   * <span style="background:#e4f3ef; color:#009838; padding:2px 8px; border-radius:4px; font-weight:600;">Cerrado</span>: La compra fue culminada o se generó la orden de compra.
   * <span style="background:#fbedeb; color:#c43d2e; padding:2px 8px; border-radius:4px; font-weight:600;">Devuelto</span>: Requiere corrección o datos adicionales de su parte.
3. Puede buscar requerimientos antiguos digitando el número de consecutivo o palabras clave de lo solicitado en la barra de búsqueda.

![Listado de mis requerimientos con buscador y estados](captura-07-mis-requerimientos.png)

---

### 2.5 Cómo corregir y reenviar un requerimiento devuelto
Cuando el área de compras devuelva una solicitud por falta de información:

1. Recibirá un correo electrónico de notificación y verá una tarjeta roja destacada al ingresar a «Mis requerimientos».
2. Haga clic en el botón **«Corregir requerimiento»**.
3. En la parte superior observará claramente la **Observación del analista de compras** (ej. *«Falta indicar el diámetro de la brida y la norma ANSI»*).
4. Realice los cambios necesarios en las descripciones, adjunte nuevos documentos o fotos si corresponde.
5. Ingrese una breve respuesta explicando el cambio (ej. *«Se actualiza diámetro a 4 pulgadas norma ANSI 300»*) y pulse **«Reenviar requerimiento»**.
6. Su solicitud volverá a estado *Radicado* conservando el mismo consecutivo para ser atendida prioritariamente.

![Pantalla de corrección de requerimiento devuelto con observación destacada](captura-08-correccion.png)

---

## 3. Módulo del Área de Compras

> *Acceso exclusivo para usuarios con perfil Analista de compras o Administrador.*

### 3.1 Gestión de la bandeja de entrada y filtros
La bandeja (`/requerimientos/bandeja/`) es el centro de operaciones donde compras gestiona todas las solicitudes de la empresa:

1. **Filtros rápidos:** Filtre por **Estado** (ej. ver solo lo *Radicado* pendiente), **Área solicitante**, **Prioridad** (*Alta*, *Media*, *Baja*) o rango de fechas de radicación.
2. **Criterios de orden:** Ordene por *Fecha de radicación* (de más reciente a más antigua) o por *Fecha requerida* (para atender lo urgente primero).
3. Para limpiar los filtros y ver la lista completa, pulse el botón **«Limpiar»**.

![Bandeja de compras con filtros de área, prioridad y estado](captura-09-bandeja.png)

---

### 3.2 Consulta de la ficha completa del requerimiento
Al hacer clic en el consecutivo de cualquier requerimiento en la bandeja, se despliega la **Ficha Completa**:
* **Datos generales y justificación:** Solicitante, área, centro de costo y fechas.
* **Detalle técnico de artículos:** Tabla completa con descripciones, códigos, marcas de calibración y precios de referencia.
* **Proveedores sugeridos:** Información de contacto propuesta por el solicitante.
* **Visor de adjuntos:** Acceso seguro para visualizar fotografías y descargar fichas técnicas en PDF.
* **Bitácora histórica:** Registro cronológico de todas las etapas por las que ha pasado el requerimiento, indicando fecha exacta, hora y analista responsable.

![Ficha técnica completa del requerimiento y bitácora de eventos](captura-10-ficha.png)

---

### 3.3 Cambio de estado de un requerimiento
Desde la ficha técnica, el analista actualiza el progreso de la compra:
1. En el recuadro **«Cambiar estado»**, seleccione la fase siguiente según el flujo permitido:
   * De *Radicado* $\rightarrow$ *En revisión*
   * De *En revisión* $\rightarrow$ *En cotización*
   * De *En cotización* $\rightarrow$ *Cerrado* (al emitir la orden de compra)
2. Ingrese una observación opcional si desea dejar constancia en la bitácora (ej. *«Enviado a cotizar con 3 proveedores»*).
3. Haga clic en **«Guardar cambio»**. El estado se actualizará de inmediato para todo el equipo.

![Formulario de transición de estado en la ficha técnica](captura-11-cambio-estado.png)

---

### 3.4 Devolución al solicitante con observaciones
Si el requerimiento carece de información suficiente:
1. En la ficha técnica, despliegue la sección **«Devolver requerimiento al solicitante»**.
2. Redacte la **Observación detallada** explicando con precisión qué debe corregirse (mínimo 10 caracteres).
3. Haga clic en **«Devolver requerimiento»**.
4. El sistema notificará de inmediato al solicitante y bloqueará la gestión en compras hasta que regrese corregido.

![Sección de devolución con observación obligatoria](captura-12-devolver.png)

---

## 4. Módulo de Analítica y Tablero de Indicadores

> *Disponible para Analistas de Compras y Jefaturas en el enlace superior «Indicadores».*

VIA Coinogas dispone de una capa de analítica avanzada que calcula indicadores clave de rendimiento (KPIs) directamente desde vistas SQL de solo lectura, garantizando que el análisis de datos no altere la operación transaccional.

![Pantalla de indicadores de gestión de VIA Coinogas](captura-13-tablero-web.png)

### 4.1 Consulta de indicadores en la aplicación web
Al hacer clic en **«Indicadores»** en la barra superior (`/requerimientos/indicadores/`), el jefe o analista accede a dos métricas fundamentales:

### 4.2 Indicador de Tiempo Promedio de Atención (HU-31)
* **¿Qué mide?** El tiempo transcurrido en días calendario desde que el solicitante radica la solicitud hasta que compras la marca como *Cerrado*.
* **Tarjetas KPI:**
  * **Promedio global en días:** Tiempo medio que tarda una compra en Coinogas.
  * **Récord más rápido / más lento:** Mínimo y máximo de días registrados.
  * **Conteo de cerrados vs. abiertos:** Solicitudes finalizadas frente al volumen activo.
* **Gráficas de desglose:**
  * **Por área:** Barras proporcionales ordenadas de la más lenta a la más rápida, permitiendo identificar cuellos de botella en áreas específicas.
  * **Por mes de cierre:** Seguimiento histórico mensual para evidenciar mejoras operativas.

### 4.3 Indicador de Tasa de Devoluciones (HU-32)
* **¿Qué mide?** El porcentaje de requerimientos devueltos por errores o información incompleta:
  $$\text{Tasa de Devolución} = \left(\frac{\text{Requerimientos devueltos al menos una vez}}{\text{Total de requerimientos radicados}}\right) \times 100$$
* **Tarjetas KPI:**
  * **Tasa global (%):** Nivel de reproceso en las solicitudes.
  * **Requerimientos devueltos:** Cantidad de solicitudes devueltas.
  * **Flujo limpio:** Requerimientos que fluyeron sin devoluciones desde su radicación.
* **Gráficas de desglose:**
  * **Por área:** Muestra qué departamentos presentan mayor tasa de devolución para dirigir capacitaciones en especificaciones técnicas.
  * **Por mes de radicación:** Permite validar si la digitalización redujo los errores de diligenciamiento en el tiempo.

### 4.4 Conexión con Power BI Desktop (HU-30)
Para análisis gerenciales o reportes de dirección ejecutiva:
1. El equipo puede ejecutar el comando:
   ```bash
   python manage.py exportar_analitica
   ```
2. El sistema vuelca los datos en archivos CSV codificados en `UTF-8 con BOM` bajo la carpeta `analitica/`:
   * `analitica_requerimientos.csv`
   * `analitica_items.csv`
   * `analitica_tiempo_atencion.csv`
   * `analitica_tiempo_atencion_mensual.csv`
   * `analitica_devoluciones.csv`
   * `analitica_tasa_devolucion_mensual.csv`
3. Abra el archivo `analitica/tablero-indicadores.pbix` en **Power BI Desktop** y haga clic en **Actualizar** para regenerar todas las gráficas interactivas.

![Visualización del reporte en Power BI Desktop](captura-14-powerbi.png)

---

## 5. Preguntas Frecuentes (FAQ)

### ¿Qué hago si me equivoqué en un requerimiento que ya radiqué?
Una vez radicado, el requerimiento no puede ser editado directamente para proteger la trazabilidad. Comuníquese con el área de compras para que el analista lo devuelva con una nota; una vez en estado *Devuelto*, podrá modificar cualquier campo o ítem y reenviarlo.

### ¿Puedo radicar un requerimiento si no conozco el precio de referencia?
Sí. El precio unitario de referencia es opcional. Si no lo conoce, déjelo en blanco; el sistema marcará el requerimiento con un total parcial y el analista de compras obtendrá el valor oficial durante la etapa de cotización.

### ¿Por qué el sistema rechaza mi fecha requerida de entrega?
Por regla de negocio, la fecha requerida de recepción no puede ser anterior a la fecha actual de solicitud. Asegúrese de ingresar una fecha futura con margen prudente para cotizar y transportar los bienes.

### ¿Cuántas fotografías puedo adjuntar y de qué tamaño?
Puede adjuntar hasta **5 archivos** por requerimiento (fotografías en JPG/PNG, fichas en PDF o cotizaciones en Excel), con un tamaño máximo de **10 MB por archivo**.

### ¿Qué significa el consecutivo REQ-2026-0015?
Es el número único oficial de su solicitud ante Coinogas. El primer segmento indica el tipo de documento (`REQ`), el segundo el año calendario (`2026`) y el tercero un contador secuencial protegido contra duplicados.

---

## 6. Canales de Soporte y Contacto

Si presenta dudas sobre especificaciones de compra o fallas en el acceso al aplicativo:

* **Mesa de Ayuda de TI (Soporte Técnico de la Plataforma):**
  * Correo: `soporte.ti@coinogas.com`
  * Extensión interna: `1020`
* **Área de Compras y Suministros (Dudas de Cotización y Catálogos):**
  * Correo: `compras@coinogas.com`
  * Horario de atención: Lunes a viernes de 7:30 a.m. a 5:30 p.m.
* **Sede Principal Coinogas:** Yopal, Casanare, Colombia.
