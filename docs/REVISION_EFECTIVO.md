# Revisar y contabilizar efectivo

Desde Inicio, «Revisar efectivo» abre la revisión del dinero. Esta revisión no paga la tarjeta ni registra cobros. Los pagos al banco siguen siendo globales, desde Tarjetas.

1. Selecciona la tarjeta e introduce el dinero físico que contaste.
2. En cada persona/pedido consulta **recibido registrado**, **sin comprobar** y **por cobrar**. Un pedido liquidado sigue visible.
3. Escribe directamente un importe parcial en **Contabilizar**. La casilla completa todo el recibido de ese pedido; no es obligatorio marcarla para introducir un parcial.
4. Despliega el pedido para consultar sus abonos y productos. Las casillas de productos significan «revisado» y no suman dinero. Las mensualidades son referencia del desglose del producto; no son pagos a Nu.
5. Usa «Propio / otro sin abono» solo para efectivo que no hayas contado en los pedidos. No crea un abono personal.
6. Guarda la revisión para conservar marcas e importes. Al abrirla de nuevo se recupera una sola revisión activa por tarjeta.

**Diferencia de efectivo** compara el dinero físico contra lo contabilizado más el dinero propio/otro declarado. «Cuadra lo contabilizado» no significa que todos los cobros estén revisados: consulta también «Por revisar». «Sin comprobar» puede ser dinero por localizar o fuera del efectivo de ese conteo; no se convierte automáticamente en faltante ni en deuda familiar.

Para otro lote, «Nuevo conteo» desmarca la revisión y refresca los cobros actuales. Al guardarlo conserva la versión anterior. El historial permite consultar sus orígenes e importes; sus versiones no se suman.

Si un abono contabilizado cambia de importe/fecha/aplicación o se anula, se pide revisar sus marcas. La aplicación no repara registros ni inventa pagos. Si dos ventanas guardan la misma revisión, la segunda debe volver a abrirla para no sobrescribir cambios ajenos.

«Consultar corte anterior» permite leer los JSON de preparación anteriores. No aplica sus cantidades a la revisión vigente ni los interpreta como prueba de disponibilidad actual.

## Almacenamiento y separación contable

Se reutiliza `audit_event` en la base cifrada, con `entity_type='cash_review'`, una revisión por tarjeta y versiones anexadas. No se crean tablas ni se cambia el esquema. Cada contabilización referencia el par `(payment_id, receivable_id)`, con importe y huella del origen. Un abono global conserva aplicaciones distintas, sin duplicar su total. Guardar la misma revisión sin cambios es idempotente.

La persistencia solo agrega eventos de revisión: no modifica `user_payment`, `receipt_application`, pedidos, repartos, cuotas, pagos bancarios ni sus aplicaciones. Los respaldos cifrados existentes incluyen estas revisiones.

## Otros cambios de la auditoría

- Los productos MSI conservan su importe al sumar todo el plan y conservan también cada cuota.
- El importador permite marcar MSI, indicar número de mensualidades y primer vencimiento. Guarda un solo pedido con su plan en la misma transacción. No reconoce MSI automáticamente a partir del texto.
- «Sin asignar a cuotas» es un pago bancario ya realizado cuyo importe aún no se distribuyó internamente a cuotas. No es efectivo disponible.
- En el desglose de Inicio, MSI por fecha muestra V (meses anteriores), M (mes seleccionado), F (meses futuros) y el importe sin fecha en la ayuda. No es una nueva obligación ni se suma al pendiente.
- La edición de un abono del historial abre su propio diálogo. Los globales mantienen la restricción de fecha/referencia; cambiar importe/reparto requiere anulación completa y registro correcto.
- Las aplicaciones activas de abonos anulados se excluyen del recibido y se avisan en Cobros. No se reparan automáticamente.
