# Claridad — Etapa 3: consulta y navegación

17 de octubre de 2026. Implementación de H06, H07 y H08, después de aprobar las pruebas de la etapa 2.

## Antes y después

| Hallazgo | Antes | Ahora |
| --- | --- | --- |
| H06 | Buscar una compra histórica abría Cobros sin selección y anunciaba que no había vista directa. | Se buscan sus participaciones mediante las fuentes existentes y se selecciona una de ellas; la explicación identifica comercio, fecha y personas. Se mantiene el filtro si permite encontrarla; en caso contrario se pasa a Todos. Un botón recupera filtro, selección y borrador previos. |
| H07 | Resultado personal, vínculo de recompra y edición/consulta de abonos imprimían identificadores internos. | Se usan comercio, fecha, referencia y número de operación en el desglose. Las claves internas continúan en datos y columnas ocultas para identificar el registro exacto. |
| H08 | Seleccionar un abono en el historial rellenaba el formulario de captura. | Encabezado «Consultando abono… Solo lectura»; campos de captura ocultos y bloqueados, borrador conservado. Editar abre el diálogo existente y modifica el mismo registro. Volver recupera la captura y selección anteriores. |

La lista de pagos no se convirtió en un navegador de auditoría. No se agregaron funciones de restauración ni se implementaron las etapas 4 o 5.

## Archivos

- `src/valenza/gui/app.py`: navegación a participaciones, contexto temporal de retorno, presentación de consulta, separación de captura y edición, descripciones humanas.
- `src/valenza/gui/receipt_editor.py`: encabezado comprensible del abono y explicación de que edita el mismo registro; actualización financiera existente intacta.
- `tests/test_clarity_stage3.py`: consulta sin escrituras, conservación del borrador/filtro/selección, edición del mismo ID y descripción humana.
- `tests/test_global_search.py`: reemplaza la expectativa del antiguo fallback sin selección por la nueva conducta autorizada; comprueba participación correcta y retorno al contexto previo. No se relajaron expectativas de geometría ni de importes.
- `tools/review_clarity_stages.py`: captura de consulta, editor, retorno y búsqueda histórica con registros exclusivamente sintéticos.

## Pruebas y capturas

Validación específica inicial: **38 casos aprobados, 0 fallos, 0 omitidos**, en `test_clarity_stage3.py`, `test_global_search.py`, `test_cobros_visual.py`, `test_global_receipts.py` y `test_personal_result_presentation.py`.

[Resultado XML](../artifacts/claridad-implementacion/etapa3.xml).

Después de la revisión visual se ocultó el formulario de captura durante la consulta para evitar confundir los importes de su borrador con el abono consultado. Se repitieron las pruebas de esta etapa y la geometría de las siete páginas: **11 casos aprobados**, incluyendo 1100 × 760 y 1360 × 900 sin modificar sus expectativas. [Resultado XML](../artifacts/claridad-implementacion/consulta-final.xml).

- [Consulta de abono](../artifacts/claridad-implementacion/etapa3-final-vistas/receipt-consultation.png).
- [Edición del mismo abono, sin ID visible](../artifacts/claridad-implementacion/etapa3-final-vistas/receipt-editor.png).
- [Retorno a captura](../artifacts/claridad-implementacion/etapa3-final-vistas/receipt-draft-restored.png).
- [Compra histórica seleccionada desde Buscar](../artifacts/claridad-implementacion/etapa3-final-vistas/search-historical-selection.png).
- [Ventana pequeña](../artifacts/claridad-implementacion/etapa3-final-vistas/3-680.png), [normal](../artifacts/claridad-implementacion/etapa3-final-vistas/3-1100.png), [maximizada](../artifacts/claridad-implementacion/etapa3-final-vistas/maximized.png).

## Límites y riesgos

Una compra histórica sin participaciones disponibles recibe una explicación, no una selección ficticia. La consulta no crea cuentas de seguimiento. Los abonos globales conservan su restricción de edición de fecha/referencia; modificar su importe/reparto sigue requiriendo el procedimiento existente. Se preserva el borrador de captura individual al consultar y volver; cambiar deliberadamente a otra participación conserva el comportamiento de preparar el importe de esa participación.

Revisar efectivo no se modificó. La regresión completa y cualquier incidencia de validación se detallan en el informe consolidado.

La revisión visual adicional descubrió que, al buscar desde Cobros una compra añadida después de la última actualización de la tabla, era necesario refrescar sus participaciones antes de seleccionar. Se agregó ese refresco de solo lectura y una prueba específica. La repetición final de `test_clarity_stage3.py` y `test_global_search.py` aprobó **16 casos**, incluyendo recuperación de filtro/selección/borrador. [XML](../artifacts/claridad-implementacion/busqueda-final.xml), [selección final de la compra histórica](../artifacts/claridad-implementacion/verificacion-final-vistas/search-historical-selection.png).

Las capturas definitivas están en [verificación final](../artifacts/claridad-implementacion/verificacion-final-vistas/). Las capturas anteriores se conservan para identificar las iteraciones, sin presentarlas como una corrección que aún no existía.
