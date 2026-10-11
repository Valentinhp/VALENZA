# Núcleo financiero inicial de SGCCC

## Alcance de este incremento

Se implementó un modelo de dominio puro en `src/sgccc/finance`. No se creó una base de datos, migración ni conexión con OCR. Todas las operaciones monetarias usan enteros en centavos; `Decimal` solo se usa internamente para redondeo proporcional determinista.

## Entidades propuestas

- `User`: beneficiario o propietario.
- `Institution`: Nu, Mercado Pago u otra institución configurada.
- `FinancialInstrument`: línea de crédito, tarjeta o saldo wallet. El wallet de Mercado Pago se distingue del crédito.
- `Purchase`: comercio, fecha, instrumento, líneas, descuentos y cargos.
- `ProductLine`: descripción, cantidad y precio unitario.
- `Allocation`: atribución de una línea a una persona por línea completa, unidades o porcentaje.
- `Discount`: descuento verificable, con origen, elegibilidad y estado confirmado.
- `Charge`: interés, comisión, envío u otro cargo con usuario destinatario explícito.
- `FinancingPlan`: un principal único por compra/instrumento.
- `Installment`: vencimiento separado en principal e interés; no es una compra adicional.
- `Receivable`: obligación pactada de un tercero y costo atribuible.
- `UserPayment`: cobro efectivamente recibido de un usuario.
- `ReceiptApplication`: aplicación inequívoca de un cobro a una cuenta por cobrar.
- `InstitutionPayment`: pago a Nu/Mercado Pago, separado de un cobro de usuario.
- `InstitutionMovement`: cargo, pago, interés, comisión, devolución, bonificación o ajuste observado en un instrumento.
- `InstrumentCalendar`: historial versionado de corte y fecha límite por instrumento.
- `InstallmentPeriodAssignment`: asignación propuesta/confirmada de una cuota al periodo del instrumento.
- `PeriodCorrectionEvent`: corrección manual auditable del periodo o vencimiento de una cuota.
- `InitialBalance`: saldo global de apertura por instrumento, sin convertirlo en compra.
- `InitialBalanceReconciliation`: diferencia y resolución de solapamientos de apertura.
- `MatchSuggestion`: coincidencia propuesta entre movimientos, aperturas u operaciones.
- `RefundEvent`: solicitud, aprobación y destinos separados de una devolución.
- `BonusEvent`: promoción o bonificación pendiente, confirmada o revertida.
- `ReceivableAdjustmentEvent`: `write_off`, `forgiveness` o `recovery` manual y auditable.
- `AuditEvent`: historial de correcciones con valor anterior, nuevo valor, actor y motivo.
- `FinancialSummary`: proyección, cobros aplicados, costo reconocido, utilidad realizada y cobros sin asignar.

En una futura persistencia, `ReceiptApplication` deberá ser una relación explícita y `InstitutionPayment` no podrá modificar directamente una cuenta por cobrar.

## Reglas implementadas y verificadas

- Las asignaciones de cada línea deben sumar exactamente el bruto de la línea y, cuando se usan unidades, también la cantidad.
- Los descuentos se distribuyen proporcionalmente sobre importes elegibles, con residual determinista por clave ordenada.
- El costo interno se separa del precio bruto cobrado al tercero.
- Principal e interés de las mensualidades se conservan separados.
- La suma de cuotas iguala exactamente el principal e interés del plan.
- Un saldo wallet no puede originar una deuda de crédito.
- Los cobros se aplican explícitamente a cuentas por cobrar.
- Cobros sin asignar no reconocen utilidad realizada.
- La utilidad realizada se reconoce proporcionalmente al cobro aplicado, con redondeo acumulado.
- Los sobrepagos quedan fuera de la utilidad automática.
- Una venta cero no se divide; queda sin utilidad realizada y requiere revisión.
- Una apertura histórica puede producir una sugerencia de solapamiento, pero no incrementa deuda sin aceptación.
- Una coincidencia de conciliación requiere aceptación explícita; aceptar/rechazar es auditable e idempotente.
- Una cuota sin calendario o con discrepancia queda `requires_review`; no se inventa vencimiento.
- Corregir un periodo no modifica principal ni pagos anteriores.
- Una bonificación pendiente no reduce costo; una confirmada crea efecto y una reversión conserva ambos eventos.
- Una devolución pendiente no reduce saldos; sus destinos aplicados se validan por separado.
- La deuda vencida permanece exigible hasta un evento manual de pérdida o condonación.
- `write_off`, `forgiveness` y `recovery` se conservan separados; una recuperación no recrea la deuda original.

## Cobertura de pruebas

`tests/test_finance_rules.py` contiene 12 pruebas sintéticas para asignaciones, descuentos, cuotas, wallet, cobros parciales, redondeo, cobros sin asignar, sobrepagos y venta cero. `tests/test_finance_events.py` cubre otras 12 pruebas para aperturas, conciliación, calendarios, devoluciones, bonificaciones e incobrables. La suite completa del proyecto se ejecuta después de cada incremento.

## Límites antes de crear la base de datos

El modelo de dominio ya cubre esas relaciones, pero falta diseñar su persistencia y probarla:

- claves, índices y unicidad;
- transacciones atómicas;
- idempotencia de reimportación sin referencia externa;
- estados de operación y restricciones SQL;
- auditoría inmutable;
- cifrado y recuperación;
- restauración y pruebas de integridad.

Este incremento no registra movimientos financieros automáticamente y no conecta el OCR con el núcleo. Todavía no es seguro generar migraciones hasta probar el repositorio transaccional sobre este modelo completo.

## Contradicciones documentales observadas

Las menciones históricas que marcaban D-019 como pendiente quedan superadas por ADR-003. Las reglas de este módulo siguen ADR-001, ADR-002 y ADR-003; no se introdujeron reglas financieras nuevas. Las pruebas sintéticas no constituyen validación de D-032 ni sustituyen evidencia real.
