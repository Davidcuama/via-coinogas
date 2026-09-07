# Casos de Prueba Funcionales - Sistema de Radicación Coinogas (Sprint 1)

Este documento recopila los Casos de Pruebas (CPs) funcionales basados en BDD para validar la interfaz y los flujos iniciales del software de compras.

## Módulo: Radicación de Requerimientos de Compra

### CP-01: Carga inicial del formulario en blanco (HU-01)
* **Dada** la URL principal del sistema de radicación de requerimientos de compra,
* **Cuando** el usuario accede a la ruta raíz desde un navegador web compatible (Chrome, Edge, Firefox),
* **Entonces** la interfaz debe cargar correctamente aplicando los estilos de Bootstrap 5 y mostrar todos los campos del formulario vacíos, listos para ser diligenciados.

### CP-02: Validación de campos obligatorios en el formulario
* **Dada** que el usuario se encuentra visualizando el formulario en blanco de radicación,
* **Cuando** intenta enviar el formulario dejando campos críticos vacíos (como Área Solicitante o Centro de Costo),
* **Entonces** el sistema debe bloquear el envío y mostrar alertas visuales de validación en HTML5/Bootstrap indicando que los campos son obligatorios.

### CP-03: Persistencia temporal de borrador
* **Dada** la sesión activa de un usuario diligenciando parcialmente los datos de radicación,
* **Cuando** hace clic en el botón "Guardar Borrador",
* **Entonces** la información introducida debe almacenarse temporalmente sin generar un número de radicado definitivo en el sistema principal.

### CP-04: Envío exitoso del requerimiento con datos válidos
* **Dada** que el usuario ha completado correctamente todos los campos obligatorios del formulario de radicación,
* **Cuando** hace clic en el botón de enviar o radicar la orden de compra,
* **Entonces** el sistema debe procesar la solicitud, mostrar un mensaje de éxito con el consecutivo asignado y limpiar la interfaz para un nuevo registro.

### CP-05: Compatibilidad multiplataforma de la interfaz
* **Dada** la estructura HTML y los estilos de Bootstrap 5 implementados en la HU-01,
* **Cuando** el formulario es abierto y evaluado desde diferentes navegadores web (Google Chrome, Microsoft Edge y Mozilla Firefox),
* **Entonces** la maquetación, los campos y los botones deben mantener una visualización idéntica y sin desbordamientos de diseño.

### CP-06: Restablecimiento de campos mediante el botón cancelar/limpiar
* **Dada** un formulario parcialmente diligenciado por el usuario,
* **Cuando** se presiona el botón de restablecer o limpiar campos,
* **Entonces** todos los textos introducidos y selecciones de menús desplegables deben borrarse de inmediato, regresando la interfaz a su estado inicial en blanco.