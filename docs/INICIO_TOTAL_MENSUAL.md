# Total mensual de Inicio

> Documento de una etapa anterior. El criterio vigente está en [PREVISION_MENSUAL_POR_VENCIMIENTO.md](PREVISION_MENSUAL_POR_VENCIMIENTO.md).

## Causa

Inicio leía `current_month_cents` de la previsión bancaria por vencimiento.
Las compras normales se desplazaban por corte/vencimiento o quedaban sin periodo
cuando no había calendario. Los movimientos adicionales no se incluían en esa
previsión. El resultado podía mostrar solo MSI, aunque existieran compras
normales del mes. No se encontró un error en la deuda contable.

## Corrección limitada a Inicio

La consulta de presentación `home_month_summary` reutiliza cuotas y aplicaciones
existentes, datos de pedidos activos y los mismos tipos de cargos adicionales
que forman parte de la deuda bancaria. El criterio queda visible:

- Compras normales: cargo registrado por mes de compra, sin volver a añadir
  principal de pedidos que ya tienen plan MSI.
- MSI: pendiente de la cuota por mes de vencimiento, descontando únicamente
  pagos bancarios aplicados explícitamente a esa cuota.
- Otros cargos: intereses, comisiones y ajustes por mes de registro.
- MSI futuros, vencidos identificados, anteriores por confirmar y sin fecha:
  separados del total del mes.

Los cargos importados `CHARGE` no se suman como una segunda compra; conservan el
tratamiento de la fuente bancaria existente. Devoluciones, bonificaciones y
pagos sin asignación conservan su efecto en la deuda total, sin atribuirlos a
cuotas o compras por suposición. Se advierte esa limitación. El indicador es
programación por fechas registradas, no el saldo neto exigible ni el pago para
no generar intereses de un estado de cuenta.

Ejemplo probado sin calendario: compra normal de octubre $1,500 + cuota MSI de
octubre $1,000 = $2,500. MSI futuros $11,000 aparte; deuda total $13,500.

La previsión de Tarjetas, las consultas guardadas, los movimientos, compras,
fechas, pagos, participaciones, cálculos personales y PDF no se modifican.

## Pruebas

Bases sintéticas SQLCipher: ejemplo solicitado en servicio y en Inicio; compras
con y sin calendario bancario; cargos por fecha; cambio de periodo y vencidos;
MSI futuros; pagos parciales aplicados y sin aplicar; líneas compartidas sin
duplicaciones; exclusión de Wallet. Se compara el contenido de las tablas
financieras antes y después de consultar. Se añaden regresiones de Inicio,
proyección bancaria y mensualidades existentes.
