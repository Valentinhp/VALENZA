# Historial de cambios

## Sin publicar — 2026-10-13

- Inicio → Ver desglose reemplaza el estado de cuenta de texto por personas
  desplegables, pedidos con asignado/abonado/pendiente y liquidados separados.
  Se mantienen la tabla superior, los PDF, Cobros y los cálculos financieros.
  [Alcance y validación del cambio](docs/INICIO_DESGLOSE_PERSONAS.md).

- Sistema central Warm Finance para controles secundarios, popups reales,
  menús, calendarios, confirmaciones y selectores Qt de archivos en español.
- Branding local de servicios e instituciones con alias normalizados, procedencia,
  licencia y huellas de integridad. Instrumentos vinculados diferenciados entre
  tarjeta, crédito, billetera y otro medio, sin inferencias por dígitos o alias.
- [Alcance y límites de Brand Experience](docs/BRAND_EXPERIENCE.md), pruebas de
  teclado e invariancia de datos y capturas sintéticas a escalas 100 % y 150 %.
- Validación final de Brand Experience: 486 pruebas aprobadas, una omitida y
  un fallo esperado; sin fallos inesperados. Recompra conserva visibles los
  campos completos y el pie fijo al desplazar y navegar con teclado.

- Warm Finance en Suscripciones, Usuarios y Configuración: encabezados,
  tarjetas compactas, tablas ajustadas a sus registros y desplazamiento en
  ventanas pequeñas.
- Suscripciones con previsión mensual separada de los cargos reales, estado
  vacío, ficha de responsables y diálogos agrupados para servicio y reparto.
- Usuarios con resumen de actividad y confirmación de cambios de identidad;
  Configuración con selector de propietario activo, respaldos diferenciados
  y resultados de diagnóstico plegables.
- Los responsables inactivos de una suscripción se muestran y conservan;
  guardarlos sigue sujeto a las validaciones existentes de personas activas.
- Capturas reproducibles con bases sintéticas cifradas mediante
  `tools/preview_admin.py`, a escalas Qt 100 %, 125 % y 150 %.
- Sin cambios en repositorio financiero, fórmulas, esquema ni migraciones.
- [Validación del rediseño](docs/VALIDACION_ADMIN_2026-10-13.md): 469 pruebas
  aprobadas, una omitida y un fallo esperado; cero fallos inesperados.

## Sin publicar — 2026-10-12

### Identidad y presentación

- Migración del paquete `sgccc` a `valenza`, comandos de inicio y assets de marca
  incluidos en el paquete. Se conserva la búsqueda de bases en la ruta heredada.
- Tema Warm Finance en Inicio, Pedidos, Cobros, Tarjetas y desbloqueo.
- Inicio con compromisos mensuales, indicadores, gráficas, calendario MSI,
  tablas compactas y movimientos recientes; pruebas de estructura y escalado.

### Operaciones y reportes

- Previsión mensual por tarjeta, captura manual MSI y reapertura de calendarios.
- Corrección de cargos de pedidos e interpretación de comprobantes.
- Reportes familiares con diseño compartido y recibos globales por persona.
- Regresiones para devoluciones, acuerdos de reparto y recompra vinculada.
- Pruebas de arranque vacío, identidad visual y auditoría financiera sintética.

### Preparación del repositorio

- Documentación actualizada de ejecución, funciones y límites conocidos.
- Corrección de un importe sintético inconsistente y adaptación de las pruebas
  de usuarios al diálogo de desbloqueo actual, sin cambiar lógica financiera.
- [Validación de la entrega](docs/VALIDACION_2026-10-12.md): 468 pruebas aprobadas,
  una omitida y un fallo esperado; paquete y arranque demo comprobados.
- Exclusión de resultados generados y temporales; conservación de fuentes SVG
  de marca y assets usados por la aplicación.

Los modelos anteriores en `docs/` conservan contexto histórico. Véase
[Estado actual](docs/ESTADO_ACTUAL.md) para interpretar las restricciones vigentes.
