# UX bloque 2: coherencia de acciones

Alcance: textos, mensajes y presentación de acciones existentes. Sin cambios en repositorios,
persistencia financiera, esquemas, fórmulas, calendarios ni PDF.

| Recorrido | Acción y resultado que comunica la interfaz |
| --- | --- |
| Gasto nuevo | **Guardar gasto** registra la operación. **Cerrar y conservar borrador**, Esc y X conservan la captura mientras Valenza continúa abierta. |
| Editar conceptos y reparto | **Guardar conceptos y reparto** conserva el guardado existente. **Descartar cambios**, Esc y X descartan únicamente lo no guardado. |
| Corregir cargo dentro del editor | La confirmación existente guarda el cargo por separado. El aviso dentro del editor distingue ese cargo ya guardado de los conceptos y reparto todavía pendientes. |
| Vincular MSI a un pedido sin plan | **Vincular plan MSI** guarda al confirmar; cancelar antes no vincula ni registra otro cargo. |
| Consultar/editar MSI existente | El aviso explica que cada fecha o ajuste se guarda al aplicarlo. Se confirma el éxito dentro del diálogo. **Cerrar**, Esc y X no deshacen operaciones guardadas. Se conserva un único botón de cierre; se elimina la duplicación engañosa de Cancelar/Cerrar. |
| Suscripciones | **Crear suscripción** y **Guardar suscripción** identifican la acción. Los avisos distinguen creación, edición, pausa, reactivación, cancelación, cargo real y vinculación de pedido. |
| Cobro global | **Revisar abono global** y **Revisar liquidación actual/total** abren la revisión existente. **Registrar abono global** registra desde esa revisión. **Volver sin registrar** conserva la captura del panel y no aplica cobros. |
| Importación | **Cancelar importación** cierra sin registrar. El éxito se anuncia al volver al formulario principal después de guardar. |
| Recompra y reparto de devolución | **Cancelar recompra** o **Descartar cambios**, según sea creación o edición. Se conservan las confirmaciones de corrección auditada; el aviso de éxito distingue recompra nueva de reparto corregido. |
| Personas y cuentas | **Guardar persona** y **Guardar cuenta** sustituyen etiquetas genéricas. Las confirmaciones de cambios sensibles se conservan. |
| Comparación bancaria | El aviso confirma **Comparación guardada en el historial**; no declara que los saldos coincidan. El vínculo informativo tiene su propio aviso de guardado. |
| Desbloqueo, Inicio, búsqueda, consultas y seguridad | Se conservan los controles de consulta, privacidad y cierre que ya eran claros. Respaldar, restaurar y verificar integridad mantienen sus advertencias y confirmaciones. |

Los mensajes añadidos no muestran importes ni datos personales. Un fallo no recibe un aviso de éxito;
los errores del formulario principal limpian el aviso transitorio anterior. No se añaden confirmaciones
ni pasos de captura.

## Comportamientos conservados que requieren atención

- La corrección de cargo y el guardado de conceptos/reparto son operaciones independientes ya existentes.
  Si el segundo guardado falla, el cargo confirmado permanece guardado. Se explica en el editor y se
  prueba expresamente. Hacerlos atómicos cambiaría el flujo y requiere autorización separada.
- Los borradores nuevos permanecen en memoria, no se garantiza recuperarlos tras cerrar Valenza.
  El cierre de la aplicación conserva su confirmación de descarte. No se implementa persistencia nueva.
- Cerrar la revisión de un cobro global conserva el importe/referencia del panel; no guarda las ediciones
  de reparto hechas únicamente en esa revisión. No se modifica ese comportamiento.
- Los mensajes transitorios no sustituyen los historiales. No se implementan nuevas rutas ni mecanismos
  de deshacer operaciones ya registradas.

## Validación

`tests/test_ux_block2.py` usa exclusivamente bases sintéticas cifradas y cubre botones, Esc y X,
guardado real, errores sin éxito falso, borradores, persistencia inmediata de MSI, corrección de cargo
independiente, suscripciones, importación, devoluciones/recompras y cobros globales.
Se conservan las regresiones del bloque 1, Inicio restaurado y ciclo de vida Qt en procesos aislados.

No se autoriza ni implementa el bloque 3.
