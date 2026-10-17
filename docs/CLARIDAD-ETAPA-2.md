# Claridad — Etapa 2: periodos y significado de cifras

17 de octubre de 2026. Implementación de H03 y H04, después de aprobar las pruebas de la etapa 1.

## Antes y después

| Hallazgo | Antes | Ahora |
| --- | --- | --- |
| H03 | El mes junto al título podía parecer un filtro global de todos los saldos. | Etiqueta «Mes de compromisos», nombre accesible y ayuda específicos. Una nota identifica compromisos/calendario/gráfica mensual y otra identifica saldos actuales y acumulados de pedidos activos. |
| H04 | Inicio y Tarjetas ofrecían explicaciones separadas, sin una explicación común de por qué difieren. | Ambos desgloses explican las dos bases: pendiente actual atribuido al mes en Inicio; programación por vencimiento antes de pagos y pendiente identificado en Tarjetas. No se suman ni deben coincidir necesariamente. |

La nota de la gráfica se refiere a la vista mensual; los pendientes totales por persona siguen siendo saldos vigentes. Consultar un mes anterior no reconstruye un estado histórico.

## Archivos

- `src/valenza/gui/app.py`: etiquetas y notas de alcance; ninguna operación aritmética nueva.
- `src/valenza/gui/clarity_text.py`: explicación compartida de presentación, sin importes ni consultas.
- `src/valenza/gui/home_month_summary.py`: agrega la explicación al texto del desglose; `home_month_summary` conserva su cálculo.
- `src/valenza/gui/bank_reconciliation.py`: agrega la misma explicación al texto de programación vigente; no altera el forecast.
- `tests/test_clarity_stage2.py`: cambio de mes sin escrituras y con saldos actuales invariantes; texto de ambos desgloses y privacidad del resultado personal.

No se duplicaron fórmulas en la interfaz ni se modificaron módulos de finanzas o persistencia. La explicación compartida no contiene cantidades que puedan revelar descuentos o resultado personal ocultos.

## Pruebas y capturas

Antes de empezar la etapa 3: **31 casos aprobados, 0 fallos, 0 omitidos**, en `test_clarity_stage2.py`, `test_home_month_total.py`, `test_monthly_card_forecast.py`, `test_bank_period_experience.py` y `test_ux_privacy_comparison.py`.

[Resultado XML](../artifacts/claridad-implementacion/etapa2.xml).

- [Inicio pequeño: mes y alcance](../artifacts/claridad-implementacion/etapa2-vistas/0-680.png).
- [Inicio normal con desglose abierto](../artifacts/claridad-implementacion/etapa2-vistas/0-1100.png).
- [Tarjetas normal](../artifacts/claridad-implementacion/etapa2-vistas/4-1100.png).
- [Ventana maximizada](../artifacts/claridad-implementacion/etapa2-vistas/maximized.png).

La herramienta produjo y verificó los mismos tamaños pequeños/normales/grandes en la superficie virtual ampliada. En pequeño sigue siendo necesario desplazarse para consultar los detalles: se conserva la estructura existente, sin convertir la pantalla principal en otra tabla contable.

La regresión completa detectó que la primera ubicación horizontal de «Mes de compromisos» movía los accesos a otra fila a 900 de ancho. Se corrigió colocando la etiqueta sobre el selector, sin ensanchar su grupo. No se cambiaron las expectativas: la repetición de `test_home_header.py`, `test_ux_block1.py` y `test_clarity_stage2.py` aprobó **11 casos**. [Resultado de la corrección](../artifacts/claridad-implementacion/cabecera-final.xml), [captura final normal](../artifacts/claridad-implementacion/verificacion-final-vistas/0-1100.png), [pequeña](../artifacts/claridad-implementacion/verificacion-final-vistas/0-680.png).

## Riesgos controlados

Se preservaron importes mensuales, pagos sin asignar, distinción entre previsión y pago oficial, líneas compartidas y privacidad. «Total sin determinar» continúa apareciendo cuando faltan fechas; no se sustituyó por cero ni se inventó una asignación mensual para hacerlo coincidir con Inicio. La regresión final se documenta en el informe consolidado.
