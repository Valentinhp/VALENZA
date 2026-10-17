# Previsión mensual por vencimiento — criterio vigente

Este documento sustituye las definiciones de mensualidad de Inicio en
INICIO_TOTAL_MENSUAL.md y en las primeras versiones de
PERIODOS_Y_COMPARACION_BANCARIA.md. Esos documentos conservan el diagnóstico
de las etapas anteriores; no deben utilizarse como especificación vigente.

## Causa corregida

Inicio clasificaba compras normales por fecha de compra, mientras Tarjetas
estimaba su vencimiento. Además, se sumaban cargos completos de compras normales
y pendientes de cuotas MSI después de pagos. El resultado podía ser $1,000 o
$2,100 cuando la programación del mes era $2,500.

Ahora ambas pantallas consumen `period_forecast()`. `home_month_summary()` solo
agrega cuentas/líneas y presenta esa fuente; no consulta otra fórmula.

## Fórmula y fechas

Programado para el mes = cargos efectivos de compras normales con vencimiento
estimado en el mes + principal e interés de cuotas MSI con vencimiento en ese
mes + intereses/comisiones/ajustes bancarios adicionales con vencimiento estimado
en ese mes. Los pedidos con plan se sustituyen por sus cuotas; no se suma otra
vez su principal ni el interés incluido en el plan.

Para compras normales se usa el calendario registrado para la fecha de compra.
Si no hay calendario histórico, pero sí reglas actuales configuradas, se usan
estas como supuesto explícito de la previsión. No se cambia su vigencia ni
se exige confirmar individualmente cada compra. Esto no reconstruye el corte
real que aplicó el banco a una compra anterior a la configuración.
La compra posterior al corte pasa al siguiente corte; si el día de pago es
anterior o igual al día de corte configurado, se estima pago al mes siguiente
del corte. Los días se limitan al último día existente del mes. Esta es una
estimación configurable, no una regla bancaria universal ni confirmación de
la fecha de contabilización bancaria. Los cargos bancarios adicionales usan
su fecha registrada como entrada a esa misma regla.

Sin reglas configuradas o sin fecha de cuota, el importe queda sin vencimiento.
No se atribuye al mes de compra por descarte. Si no hay nada fechable para el mes
y hay importes sin fecha, ambas pantallas muestran «Por configurar». Si solo
parte tiene fecha, muestran «Total sin determinar» y el subtotal identificado
por separado. Una cuota fechada nunca se presenta como el total completo cuando
hay compras sin vencimiento asignable.

Programación vigente significa la que existe en el calendario actual guardado,
incluidos ajustes de previsión previamente registrados. No se reconstruye una
programación original que ya hubiera sido modificada.

## Aplicaciones y pendiente

- Programado: antes de pagos, incluso si la cuota ya está pagada.
- Pagos aplicados al periodo: aplicaciones activas a cuotas que vencen en ese
  periodo, independientemente del mes en que se realizó el pago.
- Créditos aplicados al periodo: actualmente cero, porque el modelo no tiene
  una aplicación mensual verificada de créditos bancarios. No se inventa.
- Pendiente identificado actualmente: programación menos esas aplicaciones.
  Es una referencia estimada y se marca incompleta cuando hay pagos sin asignar,
  créditos sin asignación mensual, fechas ausentes o diferencias con la deuda neta.
- MSI futuros: programación de cuotas posteriores antes de pagos; el pendiente
  actual de esas cuotas se conserva como dato distinto.
- Vencidos: pendientes de meses anteriores con asignación de calendario
  aceptada. Lo que requiere revisión se presenta aparte. No certifica mora bancaria.

Las devoluciones y bonificaciones acreditadas conservan su efecto en la deuda
total de su destino. No se restan de una mensualidad por suposición. Las
devoluciones pendientes no reducen esa deuda. Una devolución a Wallet y su
recompra no se trasladan a la tarjeta original. No cambian repartos, abonos
familiares, resultado personal ni PDF.

Consultar otro mes muestra programación vigente de ese periodo y pendiente
conocido ahora. No filtra las aplicaciones actuales para simular una fotografía
histórica. Esto se explica expresamente en Inicio y Tarjetas.

## Pantallas y consultas

Inicio: «Previsto para pagar este mes», mes/año, importe programado y desglose
por cuenta/línea; normales y MSI, pagos vinculados y pendiente identificado,
futuros y anteriores separados. La deuda total sigue independiente. Los detalles
financieros conservan el desglose completo. El calendario/gráfico usan importes
programados, no pendientes después de pagos.

Tarjetas: misma fuente por vencimiento en indicadores y tabla, con programación,
aplicaciones y pendiente actual separados. «Comprobar mi saldo» conserva los
tipos de saldo y opciones avanzadas existentes.

Pago para no generar intereses: comparación orientativa, con diferencia banco
menos programación antes de pagos, sin confirmar coincidencia exacta ni error.
Si faltan vencimientos o el alcance no es fiable, no se calcula esa diferencia.
Pago mínimo: se muestra el importe informado, sin diferencia numérica contra
la previsión. Deuda total: comparación secundaria con sus verificaciones de
tipo, alcance, periodo actual y hora de consulta reciente.

«Lo que pide el banco» solo usa consultas manuales NO_INTEREST o MINIMUM del
mismo periodo y mismos miembros de la cuenta/línea. Se prioriza NO_INTEREST.
Incluye concepto y etiqueta de captura manual; no se reutilizan importes de
otro mes ni de un alcance distinto.

Las consultas nuevas son fotografías de formato 3 dentro de la auditoría
existente, sin migración de esquema. Guardan programación, aplicaciones,
pendiente identificado y diferencia orientativa por separado. No alteran
`difference_cents` para convertir una comparación mensual en coincidencia exacta.
Las fotografías de formatos anteriores no se reescriben ni recalculan; conservan
sus importes y su presentación anterior.

## Validación

Las pruebas usan archivos sintéticos SQLCipher. Incluyen compra de septiembre
con pago previsto en octubre, compras posteriores al corte, MSI presentes y
futuros, mezcla normal+MSI, pagos antes/después del corte y aplicaciones parciales,
pagos sin asignar, descuentos, devoluciones pendientes/acreditadas a tarjeta y
Wallet, recompra, intereses sin duplicar, meses anteriores y diciembre-enero.
Se prueban concordancia de Inicio/Tarjetas, captura manual por periodo y alcance,
pago mínimo no comparable, comparación orientativa y fotografías inmutables.
Se verifican teclado, privacidad, PDF y ausencia de cambios en tablas financieras
al consultar. No se accede a la base personal.

Ejemplo de aceptación: normal $1,500 con vencimiento estimado en octubre +
MSI de octubre $1,000 = $2,500 programados; MSI futuros $11,000; deuda antes
de pagos $13,500. Si se aplican $400 a la primera cuota, la programación sigue
en $2,500, pagos vinculados $400 y pendiente identificado $2,100.

## Límites heredados, sin corrección contable

La deuda registrada sigue usando sus fuentes originales; no se reinterpretan
movimientos CHARGE/PAYMENT importados, compras históricas o saldos iniciales
para agregarlos automáticamente. Una conciliación completa de esas fuentes
sería otro trabajo. No se crearon pagos, cargos ni aplicaciones para cuadrar
los indicadores. No se implementaron otras mejoras.
