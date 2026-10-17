# Revisar efectivo: conteo personal independiente

17 de octubre de 2026. Esta definición sustituye la restricción anterior por abonos registrados.

Puedes marcar un pedido aunque tenga cero abonos, escribir un parcial o un importe superior a la referencia del pedido. Las casillas y los campos están habilitados. «Marcar todo» y «Marcar selección» usan el importe del pedido como referencia; el importe manual es libre y no negativo, con hasta dos decimales.

La barra compara tus marcas manuales más dinero propio/otro con el efectivo contado. No representa pagos a Nu, cobros recibidos ni liquidación de deudas. La deuda pendiente y los abonos registrados se muestran únicamente como referencia. Escribir temporalmente un importe inválido retira las cifras anteriores y deshabilita guardar hasta corregirlo.

Seleccionar una persona incluye sus pedidos. Ctrl y Shift permiten selección múltiple. Seleccionar persona y pedido simultáneamente no duplica el conteo. El parcial reemplaza el importe de la selección; se reparte por el orden mostrado y el último pedido conserva cualquier exceso sobre las referencias. Repetir la acción no acumula dinero. Las marcas de productos siguen siendo revisión visual, sin sumar otra vez el importe del pedido.

Las revisiones se conservan en el historial de auditoría cifrado ya existente, usando un campo JSON `manual_counts`, separado de las aplicaciones de abonos. No se agregaron tablas ni migraciones. Las revisiones antiguas se leen conservando sus importes; abrirlas no reescribe datos. El formato anterior ligado a abonos conserva sus validaciones; el conteo nuevo no se mezcla con aquellas aplicaciones. Las versiones del historial nunca se suman entre sí.

Abrir un corte anterior lo retoma en la misma ventana: sustituye el borrador visible por sus pedidos, casillas, productos/aportaciones, parciales, dinero extra y objetivo guardados. No suma el corte al borrador anterior. El objetivo se identifica como «Objetivo del corte». Al guardar se añade una revisión al historial existente, sin sobrescribir el archivo ni modificar movimientos financieros. Al reabrir se recuperan también esos pedidos históricos, aunque no coincidan con la lista actual.

«Historial» ofrece un menú para seleccionar y retomar una revisión en esta misma ventana. Retomar usa el identificador de revisión vigente para que guardar conserve una nueva versión y mantenga el control de cambios entre ventanas.

Cambios: `src/valenza/gui/cash_review.py` y el almacenamiento de esta revisión en `src/valenza/persistence/cash_review.py`. No se modificaron cálculos de deudas, participaciones, MSI, abonos familiares ni pagos bancarios. No se accedió a la base real ni a TEST original.

Pruebas actuales: 39 casos de efectivo y preparación aprobados, incluyendo apertura en la misma ventana, restauración del objetivo y marcas, edición, guardado y reapertura del corte retomado y recuperación desde el historial sin escrituras automáticas. Se comprobó un conteo sin ningún abono, marcado completo, parcial libre superior al recibido y al pedido, guardado y reapertura, selección múltiple sin duplicados, historial, validación de JSON y separación estricta de movimientos financieros. JUnit final: `private/codex/auditoria-integral-20261016/efectivo-retomar.xml`.

Revisión visual nativa Qt Windows, con datos sintéticos cifrados, en 900 × 650 y 680 × 480: [normal](../artifacts/efectivo-tiempo-real/efectivo-900.png), [pequeña](../artifacts/efectivo-tiempo-real/efectivo-680.png). Las capturas muestran el conteo independiente sin abonos; se capturaron antes de acortar dos etiquetas de referencia. [Corte retomado en la misma ventana](../artifacts/efectivo-tiempo-real/corte-retomado-misma-ventana.png): captura nativa de Qt Windows con datos sintéticos.


## MSI: referencia por mensualidad

La checklist ya no presenta el total del pedido MSI como referencia de la casilla. `cash_review_items.py` muestra únicamente cuotas con fecha en el mes del conteo. Cada fila tiene identidad de mensualidad, número, mes e importe propio; «Marcar todo» tampoco incorpora futuras. Si hay dos cuotas fechadas en el mismo mes se muestran separadas. Los productos se desglosan solo para esa cuota, con la distribución de centavos existente.

La referencia conserva la mensualidad aunque esté cubierta por abonos, porque este conteo personal sigue siendo independiente. Los parciales permanecen libres. Los MSI sin fecha muestran una advertencia y referencia cero, nunca el principal completo como supuesta mensualidad.

Guardar conserva el mes del conteo. Retomarlo recupera ese mismo periodo y sus marcas; «Nuevo conteo» usa el mes actual. Un corte antiguo con el pedido MSI completo se separa en cuotas del periodo del corte, sin trasladar automáticamente su marca global a una cuota. Se informa para que se revise esa marca; el archivo original y las revisiones previas permanecen intactos.

Verificación: 48 pruebas relacionadas aprobadas (`efectivo-msi-entrega.xml`), más repetición de las 9 específicas de MSI después de acortar las etiquetas. Se verificaron cuotas únicas, dos cuotas en un mes, futuros, sin fecha, centavos por producto/persona, abonos previos, marcas antiguas, reapertura y cambio de mes sin escrituras financieras. Capturas nativas actualizadas: un pedido sintético de $300 en 3 MSI marca únicamente $100 de la cuota de octubre.
