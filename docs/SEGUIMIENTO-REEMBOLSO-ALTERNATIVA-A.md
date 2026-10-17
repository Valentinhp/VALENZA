# Seguimiento del reembolso — alternativa A

Implementación de presentación, 16 de octubre de 2026. No se añadieron operaciones contables.

## Cambios

**Primero, Tarjetas.** El panel de conciliación recalcula su altura después de abrir/cerrar opciones avanzadas, línea compartida, desglose e historial, y después de seleccionar una consulta. El ajuste se agrupa con un temporizador de interfaz para esperar al nuevo tamaño de los controles. Al cambiar el ancho se liberan las alturas anteriores de los textos antes de medirlos otra vez. Se conserva el tamaño compacto al cerrar el panel. No cambió la lógica de guardado ni de comparación bancaria.

**Después, Pedidos.** En «Detalle del pedido seleccionado» aparece **Seguimiento del reembolso** cuando hay datos pertinentes. No abre ventanas, no añade formularios y permite seleccionar/copiar el texto.

Muestra los datos existentes de importe, destino y acreditación; la recompra registrada y su medio; la compensación aplicada al reparto familiar; y, cuando la financiación registrada lo permite, el remanente inicial tras esa recompra. Al seleccionar la recompra también se puede ver el seguimiento del pedido original relacionado.

La resta del remanente exige devolución acreditada, recompra activa, importe conocido y coherente y el mismo instrumento Wallet/otro saldo. Si faltan esos datos o no concuerdan, se muestra «no calculable». Un importe en el PDF sin devolución vinculada no se presenta como acreditado: destino, acreditación y uso quedan sin confirmar. Sin devolución ni referencia de reembolso, el apartado se oculta.

**El remanente inicial no es saldo disponible actual.** El texto indica expresamente que el uso posterior no se rastrea y que compensar el reparto no mueve dinero, no registra un cobro familiar ni paga Nu. Los $56.58 no aparecen como una constante del programa: solo se muestran cuando resultan de los datos del pedido sintético o del registro que el usuario consulte.

## Archivos

- `src/valenza/gui/app.py`: ajuste de alturas de Tarjetas e incorporación del resumen al detalle existente.
- `src/valenza/gui/refund_tracking.py`: formato de solo lectura y condiciones de presentación de datos conocidos/desconocidos; cálculo derivado únicamente para mostrar el remanente inicial.
- `tests/test_cards_refund_ui.py`: secciones desplegables, ausencia de superposición, límites de campos, cierre y redimensionado, capturas y comprobación de ausencia de escrituras.
- `tests/test_refund_tracking.py`: ocho estados de interfaz, seis escenarios de financiación desconocida/incoherente y escape de nombres; conservación de tablas, auditoría e importes.
- Este documento y las capturas sintéticas enlazadas abajo.

No se modificaron repositorios, modelos financieros, esquemas, migraciones, deuda, MSI, descuentos, participaciones, cobros, pagos globales ni revisión de efectivo. No se abrió la base REAL ni la TEST original, ni se utilizaron clones con datos personales: todas las pruebas de esta implementación usaron datos sintéticos y bases cifradas aisladas.

## Validación

La primera etapa ejecutó 15 casos de Tarjetas y conciliación. Después se ejecutaron **133 pruebas de integración**, todas aprobadas, y **6 complementarias**, todas aprobadas; el caso de Tarjetas está repetido entre bloques, por lo que cubren **138 casos distintos**.

La integración incluye devoluciones/recompras, importación y previsualización, conciliación, privacidad y los estados nuevos. Las complementarias comprueban el encabezado de Inicio y el reparto de devolución/recompra a través de interfaz, PDF y reapertura. Después del ajuste final de alturas se repitieron las **38 pruebas del bloque bancario afectado: todas aprobadas**, sin errores ni omisiones. No se suman como casos nuevos las repeticiones del mismo escenario.

Estados nuevos revisados: pendiente de acreditación; acreditado en Wallet sin recompra; recompra con y sin compensación; devolución directa a tarjeta; importe del PDF sin destino confirmado; pedido sin devolución; y selección del pedido de recompra. También se probaron pedido vinculado ausente, anulado, con distinto instrumento/importe o estado desconocido: no se confirma el remanente.

Se compararon las tablas financieras y la auditoría antes/después de navegar, seleccionar y redimensionar; también el contador de escrituras. No se introdujeron diferencias. Se inventariaron 16 archivos financieros protegidos antes de trabajar: sus hashes permanecen idénticos al cierre. Resultado de los casos distintos: **138 aprobados, 0 fallidos y 0 omitidos**.

La revisión visual usa **capturas de la aplicación Qt con datos sintéticos en el backend offscreen**, inspeccionadas como imágenes. Se probaron 680, 900 y 1920 píxeles, volver de ancho amplio a normal, y `showMaximized()` en la pantalla virtual. Esto comprueba widgets y distribución reales de la aplicación; no representa una sesión en la base personal ni una verificación bancaria externa. No se ejecutó una regresión completa adicional de toda la aplicación en esta tarea de interfaz.

## Capturas

Todas contienen datos ficticios.

- [Tarjetas, ventana normal](../artifacts/seguimiento-reembolso/tarjetas-normal.png)
- [Tarjetas, ventana amplia](../artifacts/seguimiento-reembolso/tarjetas-amplia.png)
- [Tarjetas, ventana maximizada](../artifacts/seguimiento-reembolso/tarjetas-maximizada.png)
- [Opciones de conciliación desplegadas](../artifacts/seguimiento-reembolso/tarjetas-opciones.png)
- [Historial desplegado](../artifacts/seguimiento-reembolso/tarjetas-historial.png)
- [Pedido, ventana normal](../artifacts/seguimiento-reembolso/pedido-normal.png)
- [Pedido, ventana amplia](../artifacts/seguimiento-reembolso/pedido-amplio.png)
- [Pedido, ventana maximizada](../artifacts/seguimiento-reembolso/pedido-maximizado.png)
- [Reembolso pendiente](../artifacts/seguimiento-reembolso/pendiente.png)
- [Recompra sin compensación del sobrante](../artifacts/seguimiento-reembolso/sin-compensacion.png)
- [Reembolso directo a tarjeta](../artifacts/seguimiento-reembolso/reembolso-tarjeta.png)
- [Referencia sin destino ni acreditación confirmados](../artifacts/seguimiento-reembolso/sin-destino-confirmado.png)

## Uso y límite

Entra en **Pedidos**, selecciona el pedido y consulta el apartado en su detalle. No hay nada nuevo que guardar. Para consultar ajustes detallados se conserva el detalle anterior y sus acciones existentes.

La alternativa A explica los registros; no añade trazabilidad de transferencias ni consumo posterior por reembolso. No identifica el origen de un pago bancario ni certifica que el saldo calculado permanezca en Mercado Pago. Esas limitaciones quedan visibles y no se resuelven inventando movimientos.
