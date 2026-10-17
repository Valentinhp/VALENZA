# Conciliación bancaria manual

En Tarjetas, selecciona una cuenta y abre «Conciliación bancaria manual».
Introduce saldo, fecha y hora de consulta y tipo de saldo; guarda la consulta.
La comparación principal utiliza deuda total actual aplicada, incluido el principal
MSI futuro. Saldo al corte, pago del mes, saldo con pendientes y tipo desconocido
se conservan como información y muestran «No comparable».

El panel muestra deuda actual, fotografía de Valenza al guardar, saldo manual y
diferencia histórica: saldos coinciden, banco muestra más deuda o menos deuda.
«Ver desglose bancario» explica los cargos reales, intereses, movimientos
registrados, devoluciones en esa cuenta, pagos reales, saldo a favor separado
y cuotas previstas. Los descuentos ya están incluidos en el cargo; no se
descuentan otra vez. Las participaciones, cobros familiares y compensaciones
de Wallet no se reconstruyen como pagos al banco.

«Ver historial de consultas» permite seleccionar las fotografías anteriores.
Su deuda, diferencia, fecha, tipo, componentes y advertencias se conservan aunque
se registren movimientos posteriores. La fecha de consulta y el momento de
guardar la fotografía aparecen diferenciados.

Inicio reutiliza las mismas cuentas y consultas: deuda total actual, último saldo
manual, fecha y diferencia histórica. El total cuenta cada cuenta o línea una vez.
Se mantienen visibles Descuentos personales y Resultado personal previsto.

## Cuentas y líneas compartidas

Las cuentas permanecen independientes por identificador, incluso dentro del
mismo banco. En «Tarjetas de una misma línea» se puede vincular una tarjeta a
la cuenta principal de su línea, dentro de la misma institución. El vínculo es
informativo: no mueve cargos, pagos ni cambia los instrumentos financieros.

Cada miembro aparece una sola vez en el total de la línea; las cuotas MSI futuras
no se añaden otra vez. La deuda de cada miembro procede exclusivamente de
`list_card_summaries`. No se fusionan cuentas por nombre de banco.

## Límites conocidos

- La agrupación requiere una declaración manual. El modelo no permite verificar
  con el banco que realmente se comparta una línea ni detectar movimientos
  duplicados entre distintos instrumentos. Se muestra esa advertencia.
- Si una línea agrupada tiene saldo a favor en alguno de sus instrumentos, el
  modelo existente no establece una compensación entre cuentas. Se mantiene
  su cálculo y la diferencia se marca como no comparable, sin inventar un neteo.
- El saldo al corte, pago exigible confirmado por el banco y movimientos bancarios
  pendientes no se conocen con precisión. Las cuotas vencidas del calendario
  no se presentan como un pago bancario confirmado.
- Las consultas antiguas solo tenían saldo y fecha. Se conservan con «Sin
  fotografía» y sin diferencia histórica calculada. No se usa la deuda actual
  para inventar su deuda pasada.
- La deuda fotografiada corresponde al momento de guardar. Una fecha bancaria
  anterior o una consulta sin hora genera una advertencia. Ninguna diferencia
  se presenta como un error contable confirmado.
- Se capturan importes de deuda no negativos; el saldo a favor de Valenza se
  explica por separado. No se solicitan credenciales ni conexiones a bancos.

## Persistencia y garantías

Se utiliza `audit_event` dentro de la base cifrada existente, con consultas
`BANK_BALANCE_QUERIED` y vínculos `BANK_RECONCILIATION_SCOPE`. No se cambia el
esquema ni su versión (15). Cada consulta nueva se guarda dentro de una
transacción que fotografía el cálculo y sus componentes. Las consultas
anteriores nunca se modifican.

No se alteraron fórmulas financieras, movimientos históricos, pedidos,
participaciones, cobros, pagos, descuentos, devoluciones, recompras ni MSI.
La conciliación escribe únicamente sus metadatos. No se abrió una base personal.

## Pruebas y evidencias

**50 pruebas distintas aprobadas**, sin fallos ni errores en las ejecuciones
finales pertinentes, con bases sintéticas cifradas SQLCipher:

- Coincidencia, banco mayor y menor; validación de entradas sin escrituras.
- Cuentas independientes, línea compartida, identificadores únicos, restricciones
  de institución, persistencia y ausencia de cambios financieros al vincular.
- Descuentos, devoluciones pendientes y acreditadas en tarjeta, Wallet,
  compensaciones, recompras, MSI y pagos bancarios reales.
- Fotografías inmutables después de pagos y compras nuevas; saldo al corte,
  pago mensual y pendientes no comparables.
- Migración cifrada de versión 14 a 15 con respaldo verificado, consultas antiguas
  preservadas y reapertura con consultas nuevas y vínculos compartidos.
- Tarjetas e Inicio, historial, indicadores personales y regresiones del resultado
  personal, MSI y recompras. Comparación de tablas financieras antes/después de
  guardar y de saldos contra el servicio bancario existente.

No se detectó un problema contable preexistente en los escenarios probados.
Las limitaciones del modelo compartido se muestran sin corregirlo ni ampliar
el alcance. No se implementó búsqueda global ni otras funciones pendientes.

Informes JUnit en `artifacts/bank-reconciliation/`: `results.xml` (34 casos),
`final-results.xml` (31, con regresiones y repetición del servicio),
`financial-results.xml` (6) y `delivery-results.xml`/`ui-results.xml`
(comprobaciones dirigidas tras los ajustes de presentación). Hay 50 casos
distintos contando las repeticiones una sola vez.

Capturas representativas: `artifacts/bank-reconciliation/tarjetas.png` e
`artifacts/bank-reconciliation/inicio.png`, ambas de la base sintética cifrada.
`git diff --check` y compilación Python correctos.

```powershell
$env:QT_QPA_PLATFORM='offscreen'
.venv/Scripts/python.exe -m pytest tests/test_bank_reconciliation.py tests/test_personal_balance.py tests/test_home_structure.py tests/test_personal_result_presentation.py tests/test_monthly_msi_reopen.py -q -p no:cacheprovider --basetemp=.bank-validation
.venv/Scripts/python.exe -m pytest tests/test_product_refunds.py -k 'wallet_purchase or complete_repurchase or discount_comparison or pending_refund_is_not_cash or topup_in_another_bank' -q -p no:cacheprovider --basetemp=.bank-financial-validation
```

## Archivos de esta tarea

- `src/valenza/persistence/bank_reconciliation.py`: servicio de fotografías,
  vínculos, historial, compatibilidad y consulta del cálculo existente.
- `src/valenza/persistence/repository.py`: puntos de entrada que reutilizan ese
  servicio; cálculo financiero sin cambios.
- `src/valenza/gui/bank_reconciliation.py`: textos y desglose compartidos.
- `src/valenza/gui/app.py`: sección de Tarjetas y resumen de Inicio.
- `tests/test_bank_reconciliation.py`: pruebas nuevas con bases cifradas.
- `tests/test_personal_balance.py`: expectativas de los textos históricos.
- `docs/CONCILIACION_BANCARIA_MANUAL.md`: informe y uso.

Se conservaron los cambios de la mejora anterior del resultado personal.
