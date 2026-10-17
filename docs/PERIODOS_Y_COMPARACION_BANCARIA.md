# Periodos y comparación bancaria

> Para la implementación vigente, consultar [PREVISION_MENSUAL_POR_VENCIMIENTO.md](PREVISION_MENSUAL_POR_VENCIMIENTO.md). Este documento conserva el diagnóstico anterior.

## Diagnóstico

Las cuotas MSI ya se repartían correctamente por fecha de vencimiento y por
pagos bancarios aplicados. No se encontró duplicación del principal en esas
cuotas. Se conserva esa lógica y las asignaciones existentes de corte.

Sí había un error en la proyección «Compromisos del mes»: se obtenía restando
MSI futuros, anteriores y sin fecha a la deuda bancaria neta. El residuo no
demuestra qué cargos corresponden al mes. Podía incluir compras normales
antiguas o futuras y descontar del mes un pago sin asignación.

Pruebas documentadas en `test_bank_period_experience.py`:

- $12,000 a 12 MSI: $1,000 en octubre y $11,000 futuros; total $12,000.
- Pago de $500 sin asignar: la fórmula anterior mostraba $500 en octubre.
  Ahora conserva $1,000 programados, deuda neta $11,500 y advierte que se
  desconoce qué cuota cubre el pago. Al aplicar el pago explícitamente a la
  primera cuota, octubre queda en $500. No se crea ni aplica ningún pago solo
  por consultar la vista.
- Compras normales de diferentes periodos mezcladas con MSI: el residuo
  anterior daba $1,900 para octubre; por las fechas justificables son $1,200.

## Indicadores

- **Deuda total pendiente:** fuente bancaria existente, incluye MSI futuros,
  pagos reales y ajustes. No se cambia su fórmula.
- **Correspondiente al mes · previsto:** cuotas pendientes por vencimiento y
  compras normales con vencimiento estimable por el calendario vigente en la
  fecha de compra. El selector indica mes/año; no cambia compras ni calendarios.
- **Meses futuros:** programación posterior al periodo seleccionado.
- **Vencidos identificados:** cuotas de meses anteriores con calendario aceptado.
  Las fechas que requieren revisión y las compras normales estimadas aparecen
  como anteriores por confirmar, no como vencidos bancarios confirmados.
- **Sin periodo:** importes que no se pueden fechar, incluidos MSI sin cuotas
  o compras normales sin calendario. Nunca se cargan por descarte al mes actual.

El calendario es una previsión de pendientes al consultar, no reconstruye un
saldo histórico. Pagos sin asignar, ajustes de previsión MSI, devoluciones y
movimientos bancarios pueden hacer que no cuadre con la deuda neta; se advierte
sin repartir ni compensar automáticamente la diferencia. Las compras normales
no tienen aplicaciones de pagos individuales en el modelo actual: sus cargos
se muestran como programación estimada, con esa limitación visible.

Inicio reutiliza la tarjeta principal para el mes y una tarjeta existente para
la deuda total. Futuros, anteriores y datos pendientes aparecen juntos debajo;
no se añaden tarjetas. Tarjetas, el calendario y el diálogo MSI de Pedidos
distinguen saldo total y cuotas por periodo. El calendario usa vencimientos;
el periodo de corte almacenado se conserva y no se convierte en un pago bancario.

## Comprobar mi saldo

Seleccionar cuenta, periodo de vencimiento, concepto e importe del banco.
Por defecto se consulta pago para no generar intereses. También permite pago
mínimo, otro saldo con nombre obligatorio y los tipos anteriores.

La previsión mensual y el importe bancario se muestran juntos. No hay datos
suficientes para reconstruir exactamente pago mínimo ni pago para no generar
intereses; no se declara coincidencia, diferencia comparable ni error bancario.
La deuda total permanece como opción secundaria y solo compara deuda TOTAL,
alcance fiable, periodo actual y consulta con hora dentro de cinco minutos.

Guardar crea una fotografía versión 2 en la auditoría cifrada existente:
concepto, periodo, deuda total y programación mensual al guardar, importe
bancario, hora y advertencias. Las fotografías anteriores, sus importes y sus
diferencias no se recalculan ni reinterpretan. El historial identifica la
columna de deuda total y el detalle muestra la previsión mensual cuando existe.

## Privacidad y alcance

Un ojo oculta descuentos, resultado personal, signo y comparación derivable por
defecto. El desglose respeta ese estado; solo se guarda en memoria. Se comprueba
teclado y orden de tabulación del formulario. No se cambian PDF ni cálculos
personales, participaciones, cobros, Wallet, devoluciones o recompras.

Solo se utilizan bases sintéticas SQLCipher. No se accede a la base personal.

## Validación realizada

100 casos distintos aprobados entre pruebas de periodos, conciliación,
privacidad, teclado, Inicio en cuatro tamaños, MSI y reapertura, resultado
personal/PDF y reglas/eventos financieros. Se revisaron capturas puntuales de
Inicio y del formulario; no se generó una batería masiva de capturas. También
pasó `git diff --check`. No se ejecutó la suite completa de tareas no relacionadas.
