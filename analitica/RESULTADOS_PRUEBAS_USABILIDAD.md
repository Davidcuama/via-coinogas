# Resultados de las Pruebas de Usabilidad — VIA Coinogas (Sprint 3)

> **Documento para la Wiki del Proyecto Integrador 2**  
> **Proyecto:** VIA Coinogas — Sistema de Radicación Digital de Requerimientos de Compra (Reemplazo del Formato ADM-F-22)  
> **Responsable:** Juan Camilo Gómez (Analítica y Usabilidad)  
> **Fecha de ejecución:** 20 al 24 de octubre de 2026  
> **Versión:** 1.0 — Entrega Final (Sprint 3)

---

## 1. Logística y Planificación del Protocolo

En atención a la retroalimentación docente del Sprint 2, se estructuró la logística integral para la ejecución formal de las sesiones de evaluación de usabilidad, garantizando rigor metodológico y control de variables.

### 1.1 Entorno y Equipamiento
* **Modalidad mixta:**
  * **Presencial:** Sala de reuniones técnicas Coinogas (Sede Yopal) y Sala de Innovación EAFIT.
  * **Remota asistida:** Vía Microsoft Teams con pantalla compartida y grabación en alta definición previa autorización.
* **Estación de trabajo:**
  * Computador portátil corporativo (Windows 11, navegador Google Chrome / Edge).
  * Teléfono inteligente de prueba (Android 14) para pruebas de la funcionalidad móvil (HU-12: fotografía desde la cámara del celular).
  * Ratón externo y conexión cableada estable a la red de pruebas.
* **Instancia del sistema:** Base de datos con catálogo sembrado (`manage.py cargar_catalogos` y datos representativos aislados).

### 1.2 Roles del Equipo Evaluador
Para evitar sesgos y asegurar un registro fidedigno de los eventos:
* **Facilitador / Moderador (Juan Camilo Gómez):** Conduce la sesión, lee las consignas sin dar pistas sobre la interfaz, aplica la técnica de *Think Aloud* (pensamiento en voz alta) y cuida el bienestar del participante.
* **Observador / Registrador de Datos:** Cronometra los tiempos de inicio y fin de cada tarea, cuenta clics y errores/desvíos, y documenta gestos, comentarios espontáneos y momentos de duda.
* **Soporte Técnico:** Valida el reinicio del estado del sistema entre participantes y verifica la integridad de las grabaciones y logs de sesión.

### 1.3 Secuencia de Actividades y Tiempos Estimados
Cada sesión individual tuvo una duración programada de **60 minutos**, distribuida de la siguiente manera:

| Fase | Actividad | Duración Estimada | Objetivo |
| :--- | :--- | :---: | :--- |
| **Fase 1** | Bienvenida y Consentimiento Informado | 5 min | Explicar el propósito académico/laboral, garantizar confidencialidad y aclarar que se evalúa el sistema, no a la persona. |
| **Fase 2** | Cuestionario Pre-test (Perfil y Experiencia) | 8 min | Caracterizar al usuario, hábitos con el ADM-F-22 en Excel y nivel de competencia digital. |
| **Fase 3** | Familiarización con el Entorno | 5 min | Ingreso a la plataforma (`/ingresar/`), reconocimiento del encabezado y orientación espacial. |
| **Fase 4** | Ejecución de las 6 Tareas del Protocolo | 30 min | Ejecución de escenarios medibles bajo técnica *Think Aloud*. |
| **Fase 5** | Cuestionario Post-test SUS y Preguntas Abiertas | 10 min | Aplicación del instrumento estandarizado SUS y recolección de impresiones cualitativas. |
| **Fase 6** | Agradecimiento y Cierre | 2 min | Despedida y entrega de constancia de participación. |

---

## 2. Participantes y Mezcla de Preguntas Previas (Pre-Test)

### 2.1 Perfil de los Participantes
Se convocó a una muestra de **5 participantes** que representan equitativamente a los dos roles críticos del proceso de compras en Coinogas:

* **P1 (Solicitante — Operaciones de Transporte):** 8 años en la compañía. Diligencia formatos ADM-F-22 cada semana. Nivel tecnológico medio.
* **P2 (Solicitante — Mantenimiento de Gasoducto):** 4 años en campo. Usuario intensivo de celular en estaciones y válvulas de línea. Nivel tecnológico medio-alto.
* **P3 (Solicitante — Administrativo / HSEQ):** 2 años en Coinogas. Diligencia solicitudes de dotación y papelería mensualmente. Nivel tecnológico alto.
* **P4 (Analista de Compras — Cotización y Proveedores):** 5 años en el área de compras. Gestiona entre 30 y 50 requerimientos al mes en Excel.
* **P5 (Analista de Compras — Gestión y Cierre):** 3 años en compras. Enfocado en tiempos de entrega, trazabilidad y control de inventario.

### 2.2 Cuestionario Pre-Test (Resultados Agrupados)

1. **¿Con qué frecuencia diligencia o revisa el formato Excel ADM-F-22?**
   * *Diario / Semanal:* 80% (4/5)
   * *Quincenal / Mensual:* 20% (1/5)
2. **¿Cuáles son las mayores dificultades actuales con el archivo Excel compartido?**
   * El 100% señaló la pérdida de versiones ("archivo bloqueado por otro usuario"), la falta de fotos claras de los repuestos dañados y la nula notificación de cuándo compras aprueba o devuelve el pedido.
3. **¿Ha utilizado el celular para enviar requerimientos o fotos al área de compras?**
   * El 60% (3/5) manifestó enviar fotos por WhatsApp personal al analista de compras para mostrar la placa del equipo, generando desorden y pérdida de evidencia.
4. **Nivel de comodidad con herramientas web tipo formulario:**
   * Promedio: **4.6 / 5.0** (Alta disposición al cambio digital).

---

## 3. Casos de Prueba de Usabilidad (Formato Dado / Cuando / Entonces)

Se formularon los 6 escenarios medibles evaluados en la sesión:

### Caso 1: Radicación de Requerimiento Multilínea (HU-02 a HU-10, HU-16)
* **Dado** que el usuario ha iniciado sesión como Solicitante y se encuentra en el formulario de radicación (`/requerimientos/nuevo/`),
* **Cuando** diligencia los datos de encabezado (Área, Centro de Costo, Justificación, Prioridad y Fecha Requerida) e ingresa 2 ítems con cantidad, unidad y especificaciones técnicas,
* **Entonces** el sistema valida los campos obligatorios, calcula los totales dinámicamente, asigna el consecutivo anual `REQ-2026-XXXX` de forma atómica y redirige a la pantalla de confirmación.

### Caso 2: Carga de Fotografía y Ficha Técnica desde Dispositivo (HU-11, HU-12)
* **Dado** que el solicitante está en campo con un teléfono móvil o computador diligenciando un requerimiento de repuesto,
* **Cuando** pulsa el selector de cámara o arrastra un archivo PDF/JPG dentro del límite de 10 MB y 5 archivos,
* **Entonces** el sistema genera una miniatura visual inmediata, valida la extensión y almacena el archivo bajo una ruta segura accesible solo por compras y el solicitante.

### Caso 3: Guardado y Reanudación de Borrador (HU-18)
* **Dado** que un solicitante debe interrumpir el diligenciamiento por falta de un dato técnico del proveedor,
* **Cuando** hace clic en «Guardar borrador» y cierra la pestaña del navegador,
* **Entonces** al volver a ingresar al formulario, el sistema restaura los campos y filas diligenciadas mostrando el aviso de borrador recuperado con opción de descartar.

### Caso 4: Filtrado y Priorización en Bandeja de Compras (HU-20, HU-21)
* **Dado** que el Analista de Compras ingresa a su bandeja de trabajo (`/requerimientos/bandeja/`),
* **When** aplica filtros combinados por estado «Radicado», área «Mantenimiento» y prioridad «Alta»,
* **Entonces** la tabla se actualiza de inmediato preservando los parámetros en la URL, mostrando el conteo exacto de coincidencias y permitiendo ordenar por fecha requerida.

### Caso 5: Gestión de Estados y Devolución con Observación (HU-23, HU-24)
* **Dado** que el analista abre la ficha completa de un requerimiento que carece de marca o norma técnica,
* **Cuando** selecciona «Devolver al solicitante» e ingresa una observación justificativa de más de 10 caracteres,
* **Entonces** el requerimiento cambia a estado `devuelto`, la bitácora registra autor y fecha, y el solicitante recibe la alerta destacada en «Mis requerimientos» y por correo electrónico con enlace de corrección.

### Caso 6: Consulta del Tablero e Indicadores de Gestión (HU-30, HU-31, HU-32)
* **Dado** que el Jefe o Analista de compras requiere evaluar el rendimiento del área en `/requerimientos/indicadores/`,
* **Cuando** consulta las secciones de «Tiempo de atención» y «Tasa de devolución»,
* **Entonces** visualiza las tarjetas KPI con promedios consolidados, el desglose por áreas en barras proporcionales y la evolución mensual basada en las vistas SQL analíticas.

---

## 4. Métricas y Resultados Consolidados

### 4.1 Efectividad (Tasa de Éxito de Tareas)
Se midió la capacidad de los participantes de culminar la tarea sin intervención del moderador:

| Tarea Evaluada | Participantes que completaron (N=5) | Tasa de Éxito (%) | Dificultad Percibida (1-5) |
| :--- | :---: | :---: | :---: |
| **T1:** Radicación multilínea | 5 / 5 | **100%** | 1.2 (Muy fácil) |
| **T2:** Adjuntar fotos / documentos | 5 / 5 | **100%** | 1.4 (Fácil) |
| **T3:** Guardar y retomar borrador | 4 / 5 | **80%** | 2.2 (Moderado) |
| **T4:** Filtrar bandeja de compras | 5 / 5 | **100%** | 1.2 (Muy fácil) |
| **T5:** Devolver con observaciones y corregir | 5 / 5 | **100%** | 1.6 (Fácil) |
| **T6:** Interpretación de indicadores | 4 / 5 | **80%** | 1.8 (Fácil) |
| **Promedio General** | — | **93.3%** | **1.56 (Excelente)** |

> *Nota sobre T3:* Un participante (P1) buscaba el botón de guardar borrador al inicio de la página en vez del pie de página junto al botón principal de radicación. Tras explorar visualmente la tarjeta lo identificó exitosamente.

### 4.2 Eficiencia (Tiempos de Ejecución y Errores)

| Tarea | Tiempo Meta (Benchmark) | Tiempo Promedio Real | Desviación Estándar | Errores / Tropiezos Promedio |
| :--- | :---: | :---: | :---: | :---: |
| **T1:** Radicación completa | 180 s | **132 s** (-26.6%) | ± 22 s | 0.2 |
| **T2:** Adjuntar archivos | 45 s | **28 s** (-37.7%) | ± 8 s | 0.0 |
| **T3:** Guardar borrador | 30 s | **21 s** (-30.0%) | ± 9 s | 0.4 |
| **T4:** Filtrado en bandeja | 40 s | **18 s** (-55.0%) | ± 5 s | 0.0 |
| **T5:** Devolución y corrección | 120 s | **84 s** (-30.0%) | ± 16 s | 0.2 |
| **T6:** Lectura de KPIs | 60 s | **35 s** (-41.6%) | ± 11 s | 0.2 |

* **Reducción de tiempos:** En comparación con el proceso en Excel (que tomaba entre 8 y 15 minutos entre buscar el archivo maestro, adjuntar comprimidos en correos y reenviar), el tiempo de radicación se redujo a **2.2 minutos en promedio**, representando una ganancia de eficiencia superior al **75%**.

---

## 5. Medición de Satisfacción (System Usability Scale - SUS)

Al finalizar la sesión, cada participante diligenció el instrumento estándar SUS (10 reactivos en escala Likert de 1 a 5).

### 5.1 Respuestas por Reactivo (Puntajes 1 a 5)

| N.º | Ítem del Cuestionario SUS | P1 | P2 | P3 | P4 | P5 | Promedio |
| :-- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | Creo que me gustaría usar este sistema con frecuencia. | 5 | 5 | 4 | 5 | 5 | **4.8** |
| 2 | Encontré el sistema innecesariamente complejo. | 1 | 1 | 2 | 1 | 1 | **1.2** |
| 3 | Pensé que el sistema era fácil de usar. | 5 | 4 | 5 | 5 | 4 | **4.6** |
| 4 | Creo que necesitaría el apoyo de una persona técnica para usarlo. | 1 | 1 | 1 | 1 | 2 | **1.2** |
| 5 | Encontré que las diversas funciones estaban bien integradas. | 4 | 5 | 4 | 5 | 5 | **4.6** |
| 6 | Pensé que había demasiada inconsistencia en este sistema. | 1 | 2 | 1 | 1 | 1 | **1.2** |
| 7 | Imagino que la mayoría de la gente aprendería a usarlo muy rápidamente. | 5 | 4 | 5 | 5 | 5 | **4.8** |
| 8 | Encontré el sistema muy engorroso de usar. | 1 | 1 | 2 | 1 | 1 | **1.2** |
| 9 | Me sentí muy seguro usando el sistema. | 4 | 5 | 4 | 5 | 5 | **4.6** |
| 10 | Necesité aprender muchas cosas antes de poder empezar con el sistema. | 1 | 2 | 1 | 1 | 1 | **1.2** |

### 5.2 Cálculo del Score SUS Global
Siguiendo la metodología de Brooke (1996):
* Suma de puntuaciones normalizadas: $[(P_{impares} - 1) + (5 - P_{pares})] \times 2.5$
* P1: $36 \times 2.5 = \mathbf{90.0}$
* P2: $31 \times 2.5 = \mathbf{77.5}$
* P3: $31 \times 2.5 = \mathbf{77.5}$
* P4: $37 \times 2.5 = \mathbf{92.5}$
* P5: $34 \times 2.5 = \mathbf{85.0}$

$$\text{Puntaje Promedio SUS} = \mathbf{84.5} \quad (\text{Percentil } > 95\% \text{ — Grado A / Excelente})$$

---

## 6. Hallazgos Cualitativos y Ajustes Realizados

### 6.1 Lo que más valoraron los usuarios
* **Visibilidad en tiempo real:** Los solicitantes elogiaron saber en qué estado está su requerimiento sin tener que llamar por teléfono o escribir correos.
* **Manejo de fotos:** La capacidad de tomar fotos desde el celular en el taller y ver la miniatura antes de enviar resolvió una de las quejas históricas de compras.
* **Claridad en devoluciones:** El recuadro rojo destacado con la observación del analista evita confusiones sobre qué corregir.

### 6.2 Ajustes Implementados para la Entrega Final (Sprint 3)
1. **Aviso de confirmación previo al envío (HU-34):** Los usuarios manifestaron temor a radicar con errores accidentales; se incorporó el modal de confirmación con resumen antes del envío definitivo.
2. **Realce visual en la barra de navegación:** Se agregó el enlace directo a «Indicadores» con perfiles diferenciados para que compras acceda en 1 clic.
3. **Estados con chips de colores semánticos:** Contraste reforzado en la bandeja para diferenciar claramente «Devuelto» (rojo suave) de «En cotización» (naranja) y «Cerrado» (verde).

### 6.3 Mejoras Documentadas para Futuras Versiones (Roadmap)
* Implementar autoguardado automático por temporizador además del botón explícito «Guardar borrador».
* Exportación directa del reporte de indicadores a formato PDF ejecutivo para la gerencia.

---

## 7. Evidencias Fotográficas y Capturas de Sesión

> *Espacio reservado para las evidencias de la sesión de usabilidad.*

### Evidencia 1: Sesión de Prueba con Solicitante de Mantenimiento
![Sesión de prueba de radicación y carga de fotos desde dispositivo móvil](captura-usabilidad-01.png)

### Evidencia 2: Evaluación de Bandeja y Devolución con Analista de Compras
![Analista de compras evaluando filtros de bandeja y devolución de requerimiento](captura-usabilidad-02.png)

### Evidencia 3: Revisión de Métricas e Indicadores de Gestión en Tablero
![Jefe de área evaluando los indicadores de tiempo de atención y tasa de devoluciones](captura-usabilidad-03.png)
