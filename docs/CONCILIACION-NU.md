# Conciliación manual con Nu México

Investigación: 16 de octubre de 2026. Procesamiento y almacenamiento locales.

## Qué importe comparar

Valenza conserva la deuda total registrada, incluidas las cuotas futuras. **No copies automáticamente «saldo actual» ni «saldo a pagar» de Nu como deuda total.**

La documentación pública de Nu describe una pantalla de crédito con saldo actual, saldo a pagar, saldo futuro y crédito disponible. No confirma una etiqueta universal «saldo total de la tarjeta» que garantice el mismo alcance que Valenza, ni permite asegurar que una suma de colores funcione para todos los estados de la cuenta. No se automatiza esa equivalencia.

| Concepto | Interpretación y uso |
|---|---|
| Saldo actual | Gastos del estado en curso, con mensualidades; no necesariamente todo el principal futuro. |
| Saldo a pagar | Obligación del periodo cerrado. No es toda la deuda futura. |
| Saldo futuro | Mensualidades posteriores; no es el pago del mes. |
| Saldo al corte | Fotografía de un periodo cerrado; no debe compararse con movimientos actuales. |
| Pago para no generar intereses | Referencia oficial manual, con corte y límite copiados del banco. |
| Pago mínimo | Concepto separado. No evita por sí mismo los intereses ordinarios. |
| Crédito disponible | Capacidad de gasto; no es una deuda. |

Las etiquetas y colores son los descritos en la documentación pública, no una inspección de una cuenta personal ni garantía de la misma versión de interfaz. Las definiciones de «saldo actual» de artículos de distintas fechas no bastan para afirmar una equivalencia general.

Fuentes oficiales:

- [Crédito disponible y pantalla de saldos](https://blog.nu.com.mx/productos-nu/dudas-sobre-productos-nu/credito-disponible-nu/) — artículo del 7/8/2025.
- [Consultar el estado de cuenta](https://blog.nu.com.mx/productos-nu/dudas-sobre-productos-nu/como-consultar-estado-de-cuenta-de-tarjeta-de-credito-nu/) — corte, saldo a pagar, mínimo, pagos y devoluciones; también documenta que tarjeta física y virtual comparten estado de cuenta.
- [Plazo después del corte](https://blog.nu.com.mx/productos-nu/dudas-sobre-productos-nu/cuantos-dias-tengo-para-pagar-despues-de-mi-fecha-de-corte/) — artículo del 5/3/2026; distingue saldo actual y pago para no generar intereses. Las fechas concretas se copian del banco, no se infieren sumando días.
- [Cómo pagar Nu](https://blog.nu.com.mx/productos-nu/tarjeta-de-credito/pagar-la-tarjeta-de-credito-nu/) — el reflejo de pagos depende del método y banco. No debe suponerse inmediato.

No se encontró una especificación pública exhaustiva para reconstruir autorizaciones pendientes, prelación de aplicación de todos los pagos, intereses y redondeos internos de Nu. Esta función no reconstruye estados de cuenta ni certifica errores bancarios.

## Fuente contable existente

`FinanceRepository.list_card_summaries` conserva su cálculo: cargos de pedidos activos, intereses de financiamiento y movimientos bancarios registrados, menos pagos bancarios activos. Reembolsos y bonificaciones registrados reducen los cargos; la deuda tiene piso cero y el saldo a favor se muestra separado. Incluye el principal MSI completo desde la compra, no solo la mensualidad actual. Los cobros familiares y sus repartos no son pagos al banco. Una aplicación de un pago a cuotas no crea un segundo pago.

No registra por sí sola cargos omitidos del banco, autorizaciones pendientes ni tasas bancarias desconocidas. Las devoluciones pendientes no se descuentan como acreditadas. Las consultas se basan en lo registrado, no verifican la integridad de la captura del usuario.

`BankReconciliation` ya guardaba fotografías inmutables en `audit_event`, con miembros de la cuenta, componentes y saldos. Se reutiliza ese formato como observación independiente y versionada (versión 4 del contenido JSON). **No hay migración SQL, tablas nuevas ni reparación de bases existentes.** Las versiones anteriores se siguen leyendo sin recalcular sus diferencias. No se alteró el agrupamiento informativo existente de líneas compartidas.

## Uso

1. En Tarjetas selecciona tu tarjeta y abre **Comparar con mi banco**.
2. Para deuda total selecciona el concepto que incluye MSI futuros. Confirma con Nu que cubre esa misma cuenta y todos sus cargos aplicados, con pagos ya reflejados. Marca la confirmación solo entonces. Si no puedes confirmar el alcance, guarda la referencia sin diferencia comparable.
3. Introduce el importe en pesos. La diferencia es **banco menos Valenza**, en centavos enteros. Cero: «Coincide»; positivo: «El banco muestra más»; negativo: «Valenza muestra más». Una diferencia no demuestra por sí sola un error del banco.
4. Para registrar cuánto pide Nu, elige **Pago para no generar intereses** y copia importe, corte y fecha límite. Se guarda sin aproximarlo, recalcularlo ni descontar futuros pagos automáticamente.
5. Consulta registros anteriores en el historial. Sus cifras pertenecen al momento de guardado. Inicio muestra deuda actual por cuenta y permite revisar la consulta histórica; no la presenta como una conciliación actual recalculada.

La fecha/hora de consulta es automática; las opciones avanzadas permiten otra. Una consulta antigua, sin hora, de otro periodo o con alcance no confirmado no recibe una diferencia comparable. El guardado conserva la deuda existente en ese instante, no reconstruye deuda de una fecha pasada.

Un guardado repetido con igual fecha/hora, concepto, importe y fotografía no duplica la observación. Tras guardar se limpia el importe del formulario para evitar otro clic accidental. Corte y límite se validan juntos; límite anterior al corte, importes negativos, fraccionarios en centavos o excesivos se rechazan antes de escribir.

Compromisos del mes conserva su fórmula aprobada y representa una estimación interna distinta. La dona y la revisión de efectivo tampoco cambian. La referencia oficial puede quedar desactualizada después de abonar: hay que consultar Nu y guardar otra observación. Ninguna diferencia genera ajustes, compras, cobros ni pagos ficticios.
