# Valenza — Entrega de claridad, etapas 1 a 3

17 de octubre de 2026. Alcance autorizado: H01/H02/H05, H03/H04 y H06/H07/H08 del diagnóstico. Las etapas 4 y 5 no se implementaron.

## Entregas por etapa

- [Etapa 1: acciones y confirmaciones](CLARIDAD-ETAPA-1.md): alcance real de Suscripciones, cancelación exclusivamente local, resultados persistentes y ubicación de archivos/registros. Validación específica: 40 aprobados.
- [Etapa 2: cifras y periodos](CLARIDAD-ETAPA-2.md): mes de compromisos frente a saldos actuales/acumulados y explicación común de las distintas bases mensuales. Validación específica: 31 aprobados.
- [Etapa 3: consulta y navegación](CLARIDAD-ETAPA-3.md): búsqueda con selección, descripciones humanas, consulta de abonos separada de su edición y retorno al borrador. Validación específica inicial: 38 aprobados; repetición final de búsqueda: 16 aprobados.

Las etapas se implementaron y probaron en ese orden. Las mejoras visuales de cabecera y consulta se incorporaron durante la revisión final y se verificaron nuevamente. Los informes enlazan capturas y XML por etapa.

## Protección de datos y alcance técnico

Se creó un clon de archivos fuente, pruebas, herramientas y recursos del proyecto en `artifacts/claridad-implementacion/clone`. No se copiaron bases reales, TEST originales, respaldos, documentos privados ni claves del usuario. Las capturas utilizan nuevas fixtures SQLCipher con contraseña sintética y comprobación de cifrado. La regresión usa procesos separados por módulo y un perfil de usuario aislado; se retiró del entorno la opción de prueba con PDF privado.

La comparación SHA-256 contra el estado al iniciar esta implementación confirmó que **17 archivos protegidos** de finanzas, persistencia y Revisar efectivo siguen idénticos. [Evidencia de invariantes](../artifacts/claridad-implementacion/invariantes.json). Los cambios previos del usuario/proyecto no se revirtieron ni se presentan como trabajo nuevo.

Los únicos archivos fuente preexistentes modificados en esta implementación son:

| Archivo | Alcance |
| --- | --- |
| `src/valenza/gui/app.py` | Textos, feedback, cabecera del mes, consulta/edición y navegación/retorno; conserva las operaciones financieras existentes. |
| `src/valenza/gui/home_month_summary.py` | Texto del desglose; la función de cálculo permanece intacta. |
| `src/valenza/gui/bank_reconciliation.py` | Explicación en texto del forecast y desgloses; no cambia las fuentes ni los importes. |
| `src/valenza/gui/receipt_editor.py` | Encabezado del editor del abono, sin identificador técnico visible. |

Nuevo archivo de presentación: `src/valenza/gui/clarity_text.py`. Pruebas nuevas: `test_clarity_stage1.py`, `test_clarity_stage2.py`, `test_clarity_stage3.py`. Se actualizó `test_global_search.py` para comprobar la conducta autorizada de abrir la participación, en lugar del antiguo fallback sin selección. No se modificaron expectativas de geometría ni fórmulas.

Herramientas reproducibles: `tools/review_clarity_stages.py` y `tools/run_clarity_regression.py`. No se instalaron dependencias, generaron ejecutables, publicaron cambios ni abrieron bases originales.

## Verificación visual y tamaños pendientes

Se configuró el plugin offscreen de Qt con un archivo de pantallas de **2400 × 1600**, usando `offscreen:configfile=../offscreen.json` desde el clon. La geometría se comprobó mediante la API de Qt y aserciones exactas, sin reemplazar ni relajar pruebas.

Se capturaron ventanas de 680 × 480, 1100 × 760, 1360 × 900 y maximizada. Por tanto, los dos tamaños pendientes de la auditoría, 1100 × 760 y 1360 × 900, se repitieron completos en una superficie suficiente. La repetición de geometría de las siete páginas pasó.

Capturas finales: [Inicio pequeño](../artifacts/claridad-implementacion/verificacion-final-vistas/0-680.png), [Inicio normal](../artifacts/claridad-implementacion/verificacion-final-vistas/0-1100.png), [Tarjetas normal](../artifacts/claridad-implementacion/verificacion-final-vistas/4-1100.png), [confirmación de cancelación local](../artifacts/claridad-implementacion/verificacion-final-vistas/cancel-local-confirmation.png), [consulta de abono](../artifacts/claridad-implementacion/verificacion-final-vistas/receipt-consultation.png), [editor](../artifacts/claridad-implementacion/verificacion-final-vistas/receipt-editor.png), [compra histórica seleccionada](../artifacts/claridad-implementacion/verificacion-final-vistas/search-historical-selection.png), [maximizada](../artifacts/claridad-implementacion/verificacion-final-vistas/maximized.png).

Se conserva la distribución del modo de pruebas, cuya franja amarilla se expande mucho al maximizar. No se modificó ese comportamiento preexistente como parte de H01–H08. En pantallas pequeñas siguen existiendo barras de desplazamiento para tablas anchas; no se implementó la reorganización de formularios de las etapas 4/5.

## Regresión completa

Se ejecutaron **los 73 módulos de pruebas** del clon. La ejecución completa original reunió **763 casos: 761 aprobados, 1 fallido y 1 omitido**, sin errores de preparación. El fallo fue el de cabecera descrito abajo; se corrigió y repitió sin cambiar su expectativa. El omitido requiere un PDF privado explícito, que no se utilizó conforme a las restricciones.

El resultado consolidado por caso único, usando las repeticiones correctivas y la prueba adicional de búsqueda, es **764 casos: 763 aprobados, 0 fallos pendientes y 1 omitido**. Los resultados originales se conservan en [regresion/results.json](../artifacts/claridad-implementacion/regresion/results.json), junto a un log y XML por módulo. [Consolidado verificable por caso](../artifacts/claridad-implementacion/final-results.json).

No se ejecutó una segunda vuelta completa de todos los módulos después de la corrección de cabecera: se repitieron los bloques afectados, y la primera ejecución continuó con los módulos restantes. Los XML originales y las repeticiones permanecen separados. La prueba adicional de refresco de búsqueda se ejecutó en el bloque final correspondiente, sin contabilizarla como parte de la primera vuelta.

Incidencia encontrada: `test_home_header.py` detectó que la primera posición de la etiqueta del mes desplazaba accesos a una segunda fila. Se corrigió el layout; la repetición exacta de cabecera, tamaños y alcance mensual aprobó 11 casos. [XML original del fallo](../artifacts/claridad-implementacion/regresion/test_home_header.xml), [repetición aprobada](../artifacts/claridad-implementacion/cabecera-final.xml). No se declara que la primera ejecución completa fuera íntegramente verde.

Repetición final de mensajes y consulta: 22 aprobados en `test_clarity_stage1.py`, `test_clarity_stage3.py` (tres casos en esa ejecución), `test_cobros_visual.py` y `test_gui.py`. [XML](../artifacts/claridad-implementacion/mensajes-final.xml). La prueba adicional del refresco de compras históricas está incluida en la repetición de búsqueda de 16 casos y se contabiliza por separado, no como un caso aprobado previamente.

La suite completa también aprobó los tres bloques UX con sus expectativas originales, incluidos los dos tamaños antes pendientes. Se verificó que las fuentes del clon y de la entrega son idénticas: [manifest de fuentes](../artifacts/claridad-implementacion/final-source.json). `git diff --check` no reportó errores de espacios en los archivos modificados revisados.

## Límites de la entrega

No se agregaron reglas de contabilidad, fórmulas, descuentos, MSI, pagos, repartos, tablas ni migraciones. No se hizo coincidir artificialmente Inicio con Tarjetas. La privacidad del resultado y descuentos conserva sus controles existentes. Abrir participaciones y consultar abonos son recorridos de solo lectura; editar utiliza el registro original y su persistencia existente.

Los historiales generales/contextuales nuevos y la reorganización amplia de formularios quedan fuera de alcance hasta que el usuario autorice las etapas 4 y 5.
