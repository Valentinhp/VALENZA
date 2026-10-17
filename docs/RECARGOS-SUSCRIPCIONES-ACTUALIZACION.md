# Quitar recargos de suscripciones y cargos anteriores

17 de octubre de 2026. Cambio autorizado por el usuario para afectar tanto los cargos registrados como el recuento independiente.

En **Suscripciones → Editar**, la opción «Quitar o reducir también los recargos de cargos ya registrados» presenta los cargos/personas afectados y el importe antes de guardar. También funciona cuando la configuración futura ya tiene recargo cero y los pedidos anteriores aún conservan el recargo.

Al guardar, se reducen únicamente los recargos anteriores que excedan la configuración indicada. No se agregan retrospectivamente recargos nuevos ni se cambia el importe base de los pedidos. Los cargos anulados quedan excluidos. No se modifica ningún cargo bancario, pago, abono, descuento ni reparto base.

La deuda familiar se reduce por el importe exacto retirado. Si los abonos superarían el nuevo importe, la operación completa se rechaza con el motivo visible: no se inventan devoluciones, créditos ni reasignaciones de dinero.

El último recuento guardado de cada tarjeta afectada recibe una nueva versión de auditoría. Se ajustan sus referencias y las marcas completas; los parciales explícitos se conservan, incluso si coinciden con el total anterior. En revisiones antiguas sin modo de selección, un importe igual al total anterior se considera una marca completa, según lo explicado en el desglose. Los parciales de importe diferente permanecen intactos. Los archivos de corte originales y las versiones anteriores nunca se sobrescriben ni se suman.

La revisión previa incluye un token del estado de cargos, abonos y recuentos. Si cambian antes de guardar, se exige revisar el desglose nuevamente. Una transacción con `BEGIN IMMEDIATE` protege la aplicación conjunta; cualquier error revierte tanto la configuración como las cuentas, recargos y la nueva revisión del conteo.

Implementación: `persistence/subscription_fees.py`, `FinanceRepository.save_subscription`, editor de suscripciones y modo completo/parcial del conteo. El API mantiene por defecto la edición solo futura; la actualización histórica requiere el parámetro explícito `reduce_posted_surcharges=True`. No hay tablas ni migraciones nuevas y no se realizan correcciones automáticas al iniciar.

Se utilizaron exclusivamente bases sintéticas cifradas y aisladas. No se accedió a la base real ni a TEST original. Capturas nativas de Qt Windows: [desglose antes de guardar](../artifacts/recargos-suscripciones/antes-de-guardar.png) y [recuento actualizado](../artifacts/recargos-suscripciones/recuento-actualizado.png).

Pruebas: reducción exacta, API futura compatible, idempotencia, conteo completo frente a parcial, corte retomado, cargos con abonos, exceso de cobro bloqueado, estado desactualizado, concurrencia real entre dos conexiones cifradas, reversión completa al fallar, editor, suscripciones, efectivo/MSI, devoluciones y cobros globales. JUnit: `private/codex/auditoria-integral-20261016/recargos-entrega.xml`.

Resultado final: 126 pruebas aprobadas, cero fallas y cero omisiones.


Corrección adicional: al abrir un corte antiguo después de retirar un recargo, sus referencias podían conservar el importe anterior. `refresh_resumed_cut` actualiza una copia en memoria únicamente cuando existe una cadena de reducciones auditadas del mismo pedido y persona y su resultado coincide con la cuenta actual. Conserva parciales explícitos, objetivo, archivo original e historial. No escribe en la base al abrir ni interpreta la configuración futura como prueba de una reducción registrada. Cuatro escenarios nuevos cubren archivo antiguo, marca completa, legado y parcial. Regresión relacionada: 55 aprobadas; `private/codex/auditoria-integral-20261016/recargos-corte-retomado.xml`.
