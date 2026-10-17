# Preparar pago del mes

> Documento del cálculo y formato de cortes anteriores. El acceso actual de Inicio es **Revisar efectivo**; consulta [Revisión de efectivo](REVISION_EFECTIVO.md). Los cortes descritos aquí se conservan como consulta y no se incorporan automáticamente al conteo actual.

Acceso desde Inicio. Calculadora independiente con cortes guardables en archivos, sin escrituras contables ni migraciones.

1. Seleccionar tarjeta y escribir un objetivo manual en MXN. No se usa la fórmula mensual ni se descuentan pagos históricos.
2. Expandir persona y pedido. Las participaciones e importes ajustados se leen de `list_collection_items`; se filtran por tarjeta de origen e identidad. Se incluyen participaciones FAMILY y PERSONAL, también las personales históricas virtuales, sin materializarlas en la base. El propietario aparece identificado como «Mi parte». Se omiten participaciones sin importe ni cobros y las de origen no confirmado.
3. Marcar «Incluir pedido» para precargar y sumar su pendiente sin escribir. Desmarcar excluye todas sus aportaciones sin borrar sus importes. «Ver detalle» permite ajustar una cantidad parcial y añadir aportaciones. Si ya se editó la primera cantidad, volver a marcar conserva ese importe. No se exige un cobro previo ni se limita el cálculo al importe cobrado. Los importes registrados de deuda y cobros permanecen visibles como referencia. Los importes inválidos excluyen ese pedido del total y bloquean continuar o guardar.
4. Tu parte se selecciona desde tus pedidos y productos. «Dinero extra» permite añadir solo aportaciones adicionales que no hayas incluido arriba, para evitar repetir tu parte. El resumen y progreso se actualizan al instante. Los archivos anteriores conservan la compatibilidad del campo `own_cents`.
5. Escribir nombre y fecha para el corte. Guardar corte permite elegir un archivo JSON legible; Abrir corte recupera ese archivo y permite editarlo y guardarlo otra vez. Para conservar varios cortes, usar nombres de archivo distintos. No es un estado de cuenta bancario ni confirma disponibilidad real.
6. Cancelar o cerrar descarta los cambios que no se hayan guardado. Cambiar tarjeta también reinicia el objetivo, aportaciones y selecciones. Ir a Tarjetas descarta el borrador y selecciona esa tarjeta en el formulario existente; no registra ni precarga un pago. Los archivos guardados se conservan.

No se interpreta la lista como un estado de cuenta: incluye todos los pedidos familiares registrados de la tarjeta, también los liquidados. Para registrar una entrega real sigue existiendo Cobros. El cálculo libre no crea entregas.

Los cortes conservan una fotografía de nombres, participaciones, cobros de referencia y aportaciones; al abrirlos no se mezclan con movimientos posteriores. El total se recalcula en centavos a partir de las aportaciones seleccionadas y Mi dinero. No se acumulan cortes entre sí. Los archivos son independientes de la base activa y se pueden abrir sin recrear registros financieros. La interfaz identifica que son archivos JSON legibles.

El guardado usa reemplazo atómico. La apertura valida formato, tipos, límites de importes e identidades duplicadas antes de cambiar el borrador. No se guardan contraseñas, credenciales ni claves de la base.

## Revisión por producto

Los pedidos con conceptos manuales o productos importados muestran exclusivamente los importes asignados a la persona. Las compras históricas usan sus participaciones por producto. Se muestra la cantidad original del producto cuando está registrada, sin interpretarla como unidades de esa persona.

Cada producto tiene una casilla y un importe editable, limitado a su participación para permitir parciales. El total se suma una sola vez desde las selecciones de productos. No se añade además el importe del pedido. La casilla del pedido selecciona todos los productos y muestra un estado intermedio si solo algunos están incluidos. Los parciales editados se conservan al seleccionar todos.

Los cobros del pedido no tienen una asignación verificada por producto: no se distribuyen entre artículos ni se descuentan de cada uno. Por eso seleccionar todos los productos suma sus participaciones, no necesariamente el pendiente de cobrar del pedido. Si los productos no cuadran con la participación ajustada, se muestra la diferencia y se bloquea marcar todo; se permite revisar artículos individualmente. No se inventan artículos para compensar devoluciones, recargos o ajustes.

Sin desglose, se mantiene la selección del pendiente y las aportaciones libres. Los cortes antiguos siguen abriéndose así, sin agregarles productos actuales. Los nuevos cortes con productos guardan sus descripciones, cantidades, participaciones, importes parciales y casillas como fotografía independiente.

## MSI: solo este mes

Las preparaciones nuevas usan `upcoming_obligations(participations=...)` y las cuotas del plan registrado para mostrar una fila por mensualidad con vencimiento en el mes actual por participación, también la del propietario. Cada fila tiene su propia identidad, número de cuota, fecha y casilla «Incluir mensualidad». No se crean pedidos reales. Se conserva el criterio existente de aplicación de cobros familiares a cuotas; no se cambia el servicio. El importe mensual ya contempla esos cobros y no se descuentan otra vez. No se suman cuotas anteriores ni futuras. Sin fechas o plan suficientes no se usa el principal completo: se muestra un aviso.

Con productos cuyo desglose cuadra, se reparte el pendiente mensual proporcionalmente a las participaciones de los productos usando centavos enteros y mayores residuos; la suma coincide exactamente con el pendiente del mes. Es un reparto para preparar dinero, no una asignación bancaria ni una atribución de cobros reales por artículo. Sin desglose fiable se usa el importe mensual del pedido. Las aportaciones seleccionadas no pueden superar ese pendiente MSI mensual.

Los datos totales permanecen en la fotografía guardada, pero la fila visible de MSI muestra solo su mensualidad. Al abrir un corte anterior al formato de filas por mensualidad, sus MSI se sustituyen en el borrador por las cuotas pendientes actuales de las mismas compras y tarjeta; las casillas MSI se reinician y se muestra un aviso para revisarlas. Las compras normales conservan sus selecciones. El archivo original solo cambia si el usuario guarda. Los cortes nuevos conservan las filas guardadas con identidad de cuota; no se duplican al reabrir. La fecha escrita para nombrar un corte no cambia el mes de cálculo.

Pruebas: `tests/test_payment_preparation.py` crea únicamente bases sintéticas cifradas en el directorio temporal de pytest. Verifica importes exactos, cálculo sin cobros y por encima de ellos en compras normales, MSI mensuales con/sin productos, centavos residuales, cobros sin doble descuento, cuotas anteriores/futuras/sin fecha, desmarcado, edición, eliminación, separación de tarjetas, descarte, navegación, guardar/reabrir/editar, archivos inválidos y ausencia de escrituras contables. Las migraciones del fixture se aplican exclusivamente a esas bases nuevas sintéticas.
