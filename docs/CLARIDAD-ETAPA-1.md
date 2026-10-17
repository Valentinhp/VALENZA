# Claridad — Etapa 1: acciones y confirmaciones

17 de octubre de 2026. Implementación de H01, H02 y H05, autorizada por el usuario. No incluye etapas 4 o 5.

## Antes y después

| Hallazgo | Antes | Ahora |
| --- | --- | --- |
| H01 | La ficha general decía que los cambios afectaban ciclos futuros, aunque el editor podía reducir recargos anteriores. | La ficha explica que al editar se puede elegir reducir recargos anteriores y remite a la vista previa. Se conserva la casilla activada por defecto, sus bloqueos, el cálculo y la vista previa existentes. |
| H02 | Cancelar preguntaba por «futuros cobros», sin aclarar que actuaba localmente. | La confirmación dice expresamente que cancelar la previsión en Valenza NO cancela el servicio ni los cobros del proveedor. El éxito mantiene esa distinción. No cambia la transición de estado. |
| H05 | Muchos éxitos solo aparecían diez segundos en la barra de estado. El PDF no mostraba su destino. | Aviso persistente y seleccionable con lo guardado y dónde encontrarlo. Gastos y suscripciones incorporan comercio/fecha o servicio; el PDF muestra la ruta absoluta, incluido su nombre. Se conserva el mensaje breve de la barra. |

El aviso persistente no registra operaciones ni crea un historial nuevo. Los guardados continúan mostrando éxito después de la persistencia. Los errores y el inicio de otro diálogo financiero retiran el aviso anterior para evitar confundirlo con un resultado nuevo. Cancelar la selección de archivo no genera éxito.

El aviso de creación/edición de un abono también identifica persona, origen y fecha, y remite a Cobros → Ver historial. Se conserva el mensaje breve anterior para compatibilidad, sin perder el nuevo contexto persistente.

## Archivos

- `src/valenza/gui/app.py`: textos de Suscripciones, aviso persistente, contexto del gasto/suscripción y ruta de PDF; limpieza del mensaje anterior al iniciar otro diálogo o fallar.
- `tests/test_clarity_stage1.py`: cancelación local, ausencia de escritura al rechazar, aviso persistente y exportación/cancelación de PDF.
- `tools/review_clarity_stages.py`: captura reproducible de pantallas usando exclusivamente una fixture SQLCipher sintética.

## Pruebas y capturas

Primero se ejecutó y aprobó esta etapa antes de implementar la segunda: **40 casos aprobados, 0 fallos, 0 omitidos**, en `test_clarity_stage1.py`, `test_ux_block2.py`, `test_subscription_fee_reduction.py` y `test_family_pdf_export.py`.

[Resultado XML](../artifacts/claridad-implementacion/etapa1.xml).

- [Guardado real de gasto sintético y destino persistente](../artifacts/claridad-implementacion/etapa1-vistas/saved-feedback.png).
- [Editor de suscripción: casilla anterior conservada](../artifacts/claridad-implementacion/etapa1-vistas/subscription-editor.png).
- [Suscripciones, ventana pequeña](../artifacts/claridad-implementacion/etapa1-vistas/5-680.png).
- [Suscripciones, ventana normal](../artifacts/claridad-implementacion/etapa1-vistas/5-1100.png).
- [Ventana maximizada](../artifacts/claridad-implementacion/etapa1-vistas/maximized.png).
- [Confirmación local, captura final compartida](../artifacts/claridad-implementacion/etapa3-final-vistas/cancel-local-confirmation.png).

Se comprobaron 680 × 480, 1100 × 760 y 1360 × 900 unidades lógicas en una superficie virtual Qt de 2400 × 1600; los dos tamaños antes pendientes se alcanzaron sin cambiar expectativas. La franja amarilla de base sintética ocupa mucho espacio al maximizar por la distribución preexistente del modo de pruebas; no se modificó como parte de esta etapa.

## Límites y riesgos

El mensaje no garantiza que el servicio externo esté cancelado: aclara precisamente que no lo está. No se cambió ningún valor por defecto, cargo, deuda, reparto, recargo ni abono. Los textos de resultado se presentan dentro de la sesión, sin añadir persistencia nueva. El informe consolidado detalla la regresión final.
