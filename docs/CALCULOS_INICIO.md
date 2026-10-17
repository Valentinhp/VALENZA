# Cómo se calculan las cifras de Inicio

Revisión del código: 16 de octubre de 2026. Este documento describe el comportamiento implementado, no una reconstrucción del estado de cuenta de Nu. Todos los ejemplos son ficticios. No se modifican fórmulas ni datos al documentarlos.

## 1. Qué representa cada cifra

| Cifra visible | Qué mide | Periodo y alcance |
| --- | --- | --- |
| Compromisos del mes · tarjetas | Residual mensual de la deuda bancaria registrada, con la fórmula restaurada | Tarjetas/líneas de crédito; separa cuotas MSI por mes |
| Deuda total pendiente | Deuda bancaria registrada de todos los meses | Incluye el principal MSI futuro |
| Gráfica de pastel: Pendiente por persona | Compras normales pendientes hasta el mes elegido + pendiente MSI de ese mes | Todas las participaciones consultadas; no se restringe a una tarjeta |
| Mi parte pendiente | Suma de tus participaciones personales ajustadas menos tus abonos aplicados | Total registrado, sin filtro mensual; incluye MSI futuros |
| Mi parte · tu nombre, dentro del pastel | Tu aportación al total de la gráfica | Mismo criterio mensual que las demás personas del pastel |
| Mi parte pendiente menos descuentos | Comparación del pendiente personal total contra los descuentos registrados | No liquida deuda ni genera dinero |
| Resultado personal previsto | Asignaciones familiares menos costo efectivo de las compras | Proyección antes de abonos; no es dinero disponible |

**La cifra principal, la suma del pastel y tu pendiente personal no están obligados a coincidir: calculan conceptos y alcances distintos.**

## 2. Cifra principal: «Compromisos del mes · tarjetas»

Fuente: [`home_month_summary`](../src/valenza/gui/home_month_summary.py), usando [`FinanceRepository.list_card_summaries` y `list_installments`](../src/valenza/persistence/repository.py). La pantalla toma `home_month['current_cents']` en [`MainWindow._refresh_dashboard`](../src/valenza/gui/app.py).

### Paso A: deuda pendiente actual de cada instrumento de crédito

```text
Cargo neto registrado =
    cargos reales de pedidos activos
  + intereses de sus planes de financiamiento
  + movimientos INTEREST, COMMISSION y ADJUSTMENT
  − movimientos REFUND y BONUS

Deuda pendiente = máximo(0, cargo neto registrado − pagos bancarios activos)
```

Los descuentos del pedido ya están reflejados en el cargo real (`charged_cents`): no se descuentan otra vez. Las devoluciones afectan al instrumento donde se acredita su movimiento. Una devolución pendiente todavía no tiene ese efecto.

La consulta suma los tipos de movimiento indicados; no vuelve a añadir movimientos genéricos `CHARGE` o `PAYMENT` sobre los pedidos y los pagos bancarios. Tampoco integra la tabla `initial_balance` en esta fórmula. Tener un registro importado o un saldo inicial no garantiza por sí solo que forme parte de este total.

### Paso B: separar el pendiente de las cuotas MSI

Para cada cuota de un pedido activo:

```text
Pendiente de cuota = máximo(0, principal + intereses − aplicaciones activas de pagos bancarios a esa cuota)
```

[`month_totals`](../src/valenza/finance/monthly.py) clasifica esas cuotas por `due_date`, comparando año y mes con el periodo seleccionado:

- Mes posterior: MSI futuros.
- Mes anterior: cuotas anteriores. Esta clasificación por calendario no acredita por sí misma un vencido bancario confirmado.
- Sin fecha: cuotas sin fecha.
- Mismo mes: MSI del mes.

Para esta separación, la fórmula restaurada usa las fechas y pendientes de las cuotas; no exige que su asignación bancaria de periodo esté confirmada.

### Paso C: aplicar la fórmula restaurada

```text
Importe mensual de una tarjeta = máximo(
    0,
    deuda pendiente actual
    − pendiente de MSI futuros
    − pendiente de cuotas anteriores
    − pendiente de cuotas sin fecha
)

Cifra principal de Inicio = suma de los importes mensuales por tarjeta
```

Se limita a cero **por instrumento antes de agrupar**. Cada identificador se cuenta una vez, incluso en líneas compartidas. No se compensa automáticamente el saldo a favor de otra tarjeta. Wallet y otros instrumentos no crediticios quedan fuera de esta cifra.

Ejemplo: deuda de $13,500; MSI futuros de $11,000; sin cuotas anteriores ni sin fecha. Cifra principal: $2,500.

### Qué puede mover esta cifra

- Un pago bancario activo ya reduce la deuda; **no se resta nuevamente** al resultado mensual.
- Si ese pago también se aplica a una cuota futura, baja tanto la deuda como el bloque futuro separado. Por eso puede no reducir el importe del mes.
- Un cobro recibido de un familiar no es un pago bancario y no reduce directamente esta cifra.
- Las compras normales no se filtran individualmente por fecha de compra o corte en esta fórmula: quedan dentro de la deuda residual registrada. También pueden quedar cargos normales registrados para fechas posteriores.
- Cambiar el mes redistribuye las cuotas, pero mantiene los saldos actuales. No reconstruye cuánto se debía históricamente.

**No es una suma directa de «compras del mes + cuota del mes» ni un cálculo independiente del pago para no generar intereses de Nu.** Es la fórmula restaurada, conservada tal como está.

## 3. Gráfica de pastel: «Pendiente por persona»

Fuente: [`people_month_breakdown`](../src/valenza/gui/home_people_month.py), presentada por `MainWindow._refresh_people_dashboard`. Usa `list_collection_items` y `collection_monthly_summaries` del repositorio.

### Compras normales

Para cada participación:

```text
Participación ajustada = asignación original + ajustes vinculados de devoluciones/recompras
Pendiente de la participación = participación ajustada − cobros/abonos activos aplicados
Importe para la gráfica = máximo(0, pendiente de la participación)
```

Se incluye si la fecha de compra está en el mes elegido o en uno anterior. Una compra normal anterior sigue apareciendo mientras tenga pendiente. Las compras posteriores se excluyen; una fecha inválida o ausente produce un aviso y no se inventa un mes.

El límite a cero se aplica a cada participación. Un saldo a favor de un pedido no se interpreta como pago de otro pedido.

### MSI

El servicio `upcoming_obligations` usa la participación ajustada de cada persona y el número de cuotas del plan:

```text
Base de cada cuota = división entera(participación ajustada / número de cuotas)
Centavos sobrantes = residuo de esa división
```

Los primeros vencimientos reciben un centavo adicional hasta repartir el residuo. Ejemplo: $100 entre tres cuotas da $33.34, $33.33 y $33.33.

Después, el servicio distribuye los cobros aplicados a esa participación desde la primera cuota hacia las siguientes. La gráfica toma **solo el pendiente de las cuotas cuya fecha cae en el mes seleccionado**.

Ejemplo: participación de $600 a tres meses = $200 mensuales. Si ya se recibieron $250, el criterio existente cubre los primeros $200 y $50 de la segunda cuota: quedan $150 en la segunda y $200 en la tercera. No se descuentan esos $250 otra vez al construir el pastel.

Esto es una regla de organización de participaciones implementada en Valenza. No confirma el orden bancario de aplicación de Nu ni representa una elección explícita de cuota por el familiar.

No se suman el principal MSI completo, las cuotas futuras ni las anteriores. Si falta plan o fecha, no se transforma el MSI en una compra normal completa: se avisa de la información pendiente. Cuando existen cuotas con fecha y otras sin ella, solo se puede identificar la parte fechada del mes.

### Total y porcentajes

```text
Importe de una persona = compras normales pendientes incluidas + MSI pendientes del mes
Total del pastel = suma de los importes de todas las personas
Porcentaje de una persona = importe de esa persona / total del pastel × 100
```

Se usa el mismo criterio para ti y los familiares. Los porcentajes se muestran redondeados a una decimal; los importes se calculan en centavos enteros. Si el total es cero, no hay reparto porcentual positivo.

Al pasar el cursor sobre una persona aparecen los pedidos y las cuotas que forman su cifra. La gráfica no resta pagos bancarios ni usa el dinero que marcas en la checklist. Una previsión de suscripción sin pedido/cargo registrado tampoco se suma.

**Alcance:** a diferencia de la cifra principal, consulta todas las participaciones, sin filtrar por tarjeta o institución; puede incluir compras pagadas originalmente con Wallet u otros medios. Tampoco filtra por `participant_role` al sumar cada persona. Es un reparto de pendientes registrados, no exclusivamente de deuda con Nu.

Los saldos y cobros usados son los conocidos actualmente. Elegir un mes pasado no revierte cobros posteriores ni reconstruye un saldo histórico.

## 4. «Lo mío»: distinguir tres cálculos

### A. Tarjeta «Mi parte pendiente»

Fuente: `FinanceRepository.dashboard_summary()['personal_pending_cents']`.

```text
Mi parte pendiente = suma de remaining_cents de participaciones con rol PERSONAL
```

Incluye participaciones personales históricas que el repositorio puede proyectar sin crear nuevos registros. Las participaciones `UNKNOWN` se informan por separado y no se atribuyen automáticamente a ti.

Es tu pendiente total registrado: **no usa el mes elegido** y no separa MSI futuros. Un abono personal aplicado reduce este saldo; un cobro familiar o un pago al banco no liquida automáticamente tu participación.

Esta suma no aplica un máximo de cero a cada participación como sí hace el pastel. Si existiera un pendiente personal negativo por ajustes o datos históricos, el indicador podría reflejar esa compensación. Es otra diferencia concreta entre ambos cálculos.

### B. Tu porción del pastel

Usa el cálculo del apartado 3, para las participaciones asociadas a tu persona: compras normales pendientes hasta el mes seleccionado y MSI de ese mes.

Ejemplo: tienes $400 pendientes de una compra normal y una participación MSI de $600 a tres meses, sin abonos:

- «Mi parte pendiente»: $1,000.
- Tu porción del pastel en un mes con una cuota: $600 ($400 + $200).

La diferencia de $400 son las otras dos cuotas, no un error de suma.

### C. Comparaciones personales y resultado previsto

```text
Mi parte pendiente menos descuentos = pendiente personal total − descuentos de pedidos activos
```

Es una comparación visual; no cambia asignaciones, cobros ni deudas y puede ser negativa. Los descuentos consultados son la suma de `discount_cents` de los pedidos activos, no una entrada de efectivo.

[`personal_result`](../src/valenza/gui/personal_result.py), `expected_result_breakdown` y `order_benefit_summary` presentan otra proyección:

```text
Costo efectivo de una compra y sus recompras vinculadas =
    suma de sus cargos activos − devoluciones acreditadas

Resultado personal previsto = asignaciones familiares ajustadas − costo efectivo
```

Se agrupa el pedido raíz con sus recompras vinculadas para no contar el mismo conjunto dos veces. Los descuentos ya están dentro del cargo real. El cálculo no agrega automáticamente todas las comisiones, intereses u otros gastos ajenos a esos pedidos.

Resultado positivo o cero se etiqueta «a favor» y negativo «a tu cargo». Supone cobrar todas las asignaciones familiares y no descuenta abonos para convertirlo en efectivo disponible. Puede coincidir inicialmente con tu costo personal, pero **no equivale al pendiente personal después de abonos**.

## 5. Ejemplo conjunto: por qué las cifras se separan

Supuestos: una tarjeta; mes con la primera cuota; sin intereses, descuentos, devoluciones ni ajustes; las compras normales ya están registradas para ese mes o uno anterior.

| Compra | Cargo bancario | Tu participación | Participación familiar |
| --- | ---: | ---: | ---: |
| Normal | $1,000 | $400 | $600 |
| MSI a tres meses | $1,200 | $600 ($200 por mes) | $600 ($200 por mes) |

Deuda bancaria inicial: $2,200. MSI futuros: $800 ($400 mensuales de ambos participantes por los otros dos meses).

| Situación acumulada | Principal de Inicio | Tu porción del pastel | Familiar en el pastel | Total pastel | Mi parte pendiente total |
| --- | ---: | ---: | ---: | ---: | ---: |
| Sin abonos | $1,400 | $600 | $800 | $1,400 | $1,000 |
| Familiar entrega $100, aplicados a su compra normal | $1,400 | $600 | $700 | $1,300 | $1,000 |
| Además registras $150 de abono personal a tu compra normal | $1,400 | $450 | $700 | $1,150 | $850 |
| Además pagas $250 al banco, sin aplicación a cuotas | $1,150 | $450 | $700 | $1,150 | $850 |

En la última fila, deuda bancaria $1,950 − MSI futuros $800 = principal $1,150. El pastel no vuelve a descontar los $250 bancarios: ya refleja los abonos a las participaciones.

El resultado personal previsto de estas compras permanece en −$1,000: asignaciones familiares totales $1,200 − costo efectivo $2,200. No se modifica por esos cobros, abonos personales o pagos al banco.

La coincidencia entre el total del pastel y el principal en algunas filas depende de los supuestos y movimientos del ejemplo; no es una igualdad garantizada por el programa.

## 6. Qué acción afecta a qué cálculo

| Acción | Principal de Inicio | Pastel | Mi parte pendiente total |
| --- | --- | --- | --- |
| Cobro familiar aplicado | No lo reduce directamente | Reduce el pendiente de esa persona, según pedido/cuota | No |
| Abono personal aplicado | No lo reduce directamente | Reduce tu pendiente incluido, según pedido/cuota | Sí |
| Pago bancario registrado | Reduce deuda bancaria; el efecto mensual depende de los bloques MSI | No liquida participaciones | No liquida participaciones |
| Aplicar ese pago a una cuota | Cambia el pendiente de esa cuota y el bloque separado; no es otro pago | No es un cobro familiar/personal | No |
| Marcar o guardar checklist | No | No | No |
| Cambiar el mes de Inicio | Redistribuye cuotas con saldos actuales | Selecciona cuotas y excluye compras posteriores | No cambia su alcance total |

## 7. Referencias para revisar una diferencia

1. Identificar la cifra exacta y el mes seleccionado; no comparar pendiente personal total con cuota mensual.
2. Para el principal, revisar por tarjeta la deuda neta y los bloques MSI futuros, anteriores y sin fecha.
3. Para el pastel, revisar los pedidos del tooltip y los abonos aplicados a cada participación; comprobar fechas MSI.
4. Para tu saldo total, revisar participaciones `PERSONAL` y sus abonos, sin descontar pagos bancarios ni descuentos nuevamente.
5. Separar simulaciones guardadas de la checklist de las operaciones reales.

Referencias de pruebas existentes: [`test_home_initial_restore.py`](../tests/test_home_initial_restore.py), [`test_people_chart.py`](../tests/test_people_chart.py), [`test_personal_balance.py`](../tests/test_personal_balance.py), [`test_personal_result_presentation.py`](../tests/test_personal_result_presentation.py) y [`test_payment_preparation.py`](../tests/test_payment_preparation.py).

Las guías antiguas de «previsión por vencimiento» explican otro cálculo, empleado en Tarjetas; no sustituyen la fórmula restaurada del indicador principal descrita aquí.
