# Diagnóstico de devoluciones, recompras y dinero en Wallet

Fecha de investigación: **16 de octubre de 2026**, México. Etapa exclusivamente de investigación: **no se implementaron correcciones**.

## 1. Resumen ejecutivo

**Recibir un reembolso en Mercado Pago no paga Nu.** El código actual conserva esa separación. Una devolución acreditada en Wallet aumenta el saldo registrado de ese instrumento; la deuda de la tarjeta original permanece igual. Solo un reembolso registrado en la tarjeta, o un pago bancario real registrado para ella, reduce esa deuda.

La recompra vinculada también existe: crea otro pedido pagado desde la misma Wallet y lo compensa para evitar una segunda cuenta por cobrar por el sustituto. El sobrante puede compensar el reparto del producto original, pero esa compensación **no retira dinero de Wallet, no genera un cobro familiar y no paga al banco**.

En los escenarios sintéticos, después de recibir $186.57 y recomprar por $129.99, Wallet conserva $56.58 tanto con la casilla de compensación marcada como sin marcar. Lo que cambia con esa casilla es la responsabilidad asignada a las personas.

La carencia principal es **trazabilidad de usos posteriores de cada reembolso**. El sistema no puede demostrar que determinado pago a Nu provino de esos $56.58, ni enlazar una transferencia a Cuenta Nu con ese reembolso. Tampoco puede garantizar que un remanente histórico continúe disponible a partir de su resta inicial.

No se reprodujo una doble reducción automática de deuda bancaria ni un segundo cobro familiar automático en el flujo vinculado probado. Sí se comprobó que otra entrada genérica, con identidad distinta, puede volver a registrar el mismo importe sin relacionarse con la devolución original: es un riesgo de captura duplicada entre rutas, no evidencia de que Valenza lo haya hecho automáticamente en tu caso.

**Recomendación:** empezar por la alternativa A, seguimiento de solo lectura dentro del pedido. No hace falta un módulo de administración completa de Wallet. La alternativa B solo sería necesaria para controlar consumos posteriores por reembolso, con autorización específica.

## 2. Evidencia y límites del caso histórico

Se consideran confirmados por tu mensaje: compra de $602.87, descuento de $60.29, cargo de $542.58, reembolso a Wallet de $186.57, recompra posterior de $129.99 y **$56.58 que hoy siguen en Wallet**, sin transferencia ni pago a Nu.

Eso no prueba por sí solo:

- Que la recompra se pagara íntegramente con Wallet.
- Que se marcara «Aplicar sobrante» en Valenza.
- Qué persona asumió el costo restante.
- Que se registrara un abono, una transferencia o el aporte aproximado de $21.

Para buscar evidencia sin abrir la base REAL ni la TEST original, se hizo una **copia nueva del clon de referencia previamente autorizado**, abierta con `PRAGMA query_only=ON`. La búsqueda exacta de los tres importes originales ($602.87, $60.29 y $542.58) no encontró pedidos coincidentes. Se comprobó que los bytes del clon fuente no cambiaron. Esto solo limita lo verificable en ese clon: **no demuestra que el caso no exista en la base personal ni describe su estado actual**.

El código de pruebas sí contiene una reproducción sintética con esos importes. Allí el producto devuelto vale $207.79. Ese dato permite explicar los $21.22, pero es evidencia del escenario de prueba, no confirmación de una operación personal actual.

## 3. Capacidades actuales y clasificación

Las etiquetas de capacidad indican funcionamiento comprobado, no solo presencia de campos.

| Capacidad | Estado | Diagnóstico |
|---|---|---|
| Devolución parcial o completa de un producto importado | YA EXISTE | **Correcto, sin cambios necesarios** en los escenarios admitidos: importe, producto, destino y reparto final explícitos. |
| Devolución completa de un pedido y todas sus variantes | PARCIAL | El repositorio admite varias propuestas por producto al crear el pedido; el flujo documentado de importación asigna una devolución. No es un gestor general de devoluciones posteriores. |
| Reembolsos sucesivos del mismo producto | NO EXISTE como secuencia general | **Falta trazabilidad o información**: las restricciones únicas admiten una devolución por producto/comprobante. No confundir una devolución parcial con varias acreditaciones parciales sucesivas. |
| Reembolso pendiente y confirmación de acreditación | YA EXISTE | **Correcto, sin cambios necesarios**: confirmar dos veces la misma fecha no crea dos créditos. |
| Destino tarjeta frente a Wallet u otro saldo | YA EXISTE | **Correcto, sin cambios necesarios**: afecta únicamente al instrumento elegido. No hay verificación externa del destino real. |
| Descuento personal separado | YA EXISTE | **Correcto, sin cambios necesarios**: reduce el cargo original una sola vez y conserva la asignación bruta aprobada. |
| Recompra vinculada financiada por el reembolso | YA EXISTE | **Correcto, sin cambios necesarios** dentro de su alcance: una recompra, íntegramente desde el mismo instrumento no crediticio. |
| Recompra con tarjeta distinta o financiación mixta | PARCIAL | Se pueden registrar compras ordinarias por separado, pero el flujo vinculado rechaza estas combinaciones. **Falta trazabilidad o información** para mantenerlas vinculadas sin duplicar responsabilidades. |
| Reparto familiar de devolución/recompra | YA EXISTE | **Correcto, pero mal explicado**: «aplicar» significa compensar responsabilidades, no mover efectivo. La correspondencia con el acuerdo real requiere confirmación. |
| Abonos familiares y personales, parciales y globales | YA EXISTE | **Correcto, sin cambios necesarios** en los casos probados. Son distintos de ajustes y pagos bancarios. |
| Aplicar libremente un remanente a otra participación | NO EXISTE como uso trazable del reembolso | La casilla existente pertenece al producto original y a su recompra. No es una aplicación general a cualquier deuda. |
| Transferencias Wallet → cuenta bancaria | NO EXISTE como operación enlazada entre cuentas | No se encontró servicio, tabla ni flujo específico que una origen, destino y reembolso. **Falta trazabilidad o información**. |
| Pago bancario global | YA EXISTE | Reduce deuda de crédito; no exige pagar por pedido. **Falta trazabilidad del origen de fondos**, no del pago de destino. |
| Seguimiento del dinero sobrante después de la recompra | PARCIAL | Puede derivarse el remanente inicial. No hay registro específico de todos sus usos posteriores. |
| Anulación/corrección de devolución y recompra | PARCIAL | Se protege el historial bloqueando anulaciones aisladas; se permite corregir el reparto. No existe un flujo general de reversión del reembolso o de su financiación. |
| Confirmar qué se guardó en este caso personal | No verificable | **No verificable con la evidencia disponible**. No se abrió la base personal. |

No se confirmó un defecto automático de cálculo en los escenarios ejecutados. Las limitaciones de alcance no se presentan como defectos contables sin reproducción.

## 4. Mapa de código, tablas y campos

Las líneas corresponden al código inspeccionado durante esta investigación.

| Archivo / función | Responsabilidad y datos |
|---|---|
| `src/valenza/persistence/repository.py:963`, `create_order` | Conserva `order_record.original_cents`, `discount_cents`, `charged_cents`, `instrument_id`, `purchase_mode`, `order_status`; `order_allocation` y evidencia de importación. |
| `repository.py:1153`, `_insert_product_refunds` | Valida producto, centavos, límite de importe, reparto y destino. Inserta `imported_product_refund` y `product_refund_adjustment`; genera movimiento solo si está acreditado. |
| `repository.py:1378`, `_insert_refund_movement` | Crea un único `institution_movement` de tipo `REFUND` en el destino, con referencia `refund:<id>`. |
| `repository.py:1426`, `confirm_product_refund` | Cambia `PENDING` a `ACCREDITED`, guarda fecha y vínculo al movimiento; validación de abonos incompatibles e idempotencia. |
| `repository.py:1244–1248`, `register_refund_repurchase` / `_register_refund_repurchase` | Crea pedido vinculado y compensaciones en una misma transacción. Exige misma Wallet/otro saldo, acreditación, fondos registrados y una sola recompra. |
| `repository.py:1315`, `update_refund_repurchase_allocations` | Corrige responsabilidades sin repetir reembolso, cargo, recompra, cobro ni pago. Guarda auditoría y rechaza edición desactualizada. |
| `repository.py:1401`, `list_product_refunds` | Devuelve destino, ajustes, vínculo y participación final efectiva. No devuelve una cronología de usos posteriores del remanente. |
| `repository.py:2521`, `list_card_summaries` | Deuda y saldo registrado por instrumento; excluye Wallet de deuda de crédito. |
| `repository.py:2792`, `list_collection_items` | Asignación original + ajustes de devoluciones acreditadas + revisiones de recompra − abonos activos. |
| `repository.py:3024`, `record_receipt`; `:2956`, `record_global_receipt` | Crean `user_payment` y `receipt_application`. La compensación de devolución no usa estos servicios. |
| `repository.py:3143`, `cancel_user_payment`; `:2853`, `receipt_inconsistencies` | Anulación, reversión de aplicaciones y detección de inconsistencias; consultas excluyen abonos anulados aunque haya aplicaciones legadas activas. |
| `repository.py:2268`, `record_institution_payment`; `:2368`, `cancel_institution_payment` | Pago real a `CREDIT_CARD`/`CREDIT_LINE`, estado y auditoría; sin `refund_id` ni `source_instrument_id`. |
| `repository.py:1499`, `cancel_order` | Bloquea anular pedido original o recompra vinculada para no dejar crédito huérfano. |
| `repository.py:1732`, `update_manual_concepts` | Revisa conceptos y ajustes manteniendo evidencia original; las correcciones aisladas del cargo con devolución están protegidas por validaciones adicionales. |
| `repository.py:3242`, `order_benefit_summary` | Agrupa raíz y recompras una sola vez para costo efectivo y comparación personal. No es deuda bancaria ni saldo disponible. |
| `src/valenza/finance/refund_repurchase.py:4`, `refund_repurchase_amounts` | Resta y reparto exactos en centavos; distingue sobrante físico inicial y compensación. |
| `src/valenza/finance/models.py`, `RefundEvent`; `finance/rules.py:297`, `validate_refund_event` | Modelo y validación de importes. Sus campos abstractos no constituyen un servicio de transferencias ni prueban un pago a Nu. El destino persistido gobierna el efecto real. |
| `src/valenza/gui/pdf_import.py`, `RefundEditor`, `RefundRepurchaseDialog` | Importe, destino, acreditación, medio de recompra, casilla de sobrante y reparto; vista previa advierte que compensar no paga al banco. |
| `src/valenza/gui/app.py:3569` y métodos `_register_product_repurchase`, `_confirm_pending_product_refund` | Detalle de Pedidos y acciones de devolución/recompra. |
| `src/valenza/persistence/bank_reconciliation.py`, `BankReconciliation` | Fotografías informativas de deuda. No genera devolución, cobro ni pago. |

### Persistencia relevante

- `imported_product_refund`: `id`, `order_id`, `product_index`, `source_key`, `original_cents`, `amount_cents`, `destination_id`, `status`, `accredited_at`, `created_at`, `movement_id`. Claves únicas `(source_key, product_index)`, `(order_id, product_index)` y `movement_id`.
- `product_refund_adjustment`: por persona, `original_cents`, `final_cents`, `delta_cents`. No reescribe el importe original del pedido.
- `product_refund_repurchase`: `refund_id` como clave primaria, `order_id` único, `applied_cents`. **`applied_cents` es compensación familiar, no importe transferido a Nu.** El importe gastado en recompra está en el pedido vinculado.
- `product_repurchase_adjustment`: `refund_id`, `order_id`, `user_id`, `delta_cents`; revisa el original y neutraliza la segunda cuenta del sustituto.
- `institution_movement`: instrumento, fecha, tipo, importe, descripción, referencia externa y estado de conciliación. Referencia externa única por instrumento cuando está informada. Ese estado no equivale por sí solo a una reversión económica.
- `institution_payment`: tarjeta, importe, fecha, referencia de texto y estado activo/anulado. **No guarda origen de fondos estructurado.**
- `user_payment` / `receipt_application`: dinero efectivamente abonado y su aplicación a participaciones, con estados y reversión.
- `audit_event`: acciones de registro, acreditación, recompra y corrección, con valores anteriores/nuevos. No se encontró un historial específico de «uso posterior del reembolso».

Estas estructuras ya existen en las migraciones 13 y 14 de `database.py`. No se crearon tablas ni migraciones durante esta investigación.

## 5. Documentación oficial consultada

Consulta: **16/10/2026**. Se usaron fuentes oficiales mexicanas; no testimonios de foros ni políticas de otros países.

**Limitación de acceso:** varias páginas de Mercado Libre/Mercado Pago devolvieron 403 o no fueron accesibles en lectura directa. Se pudo consultar texto indexado de sus páginas oficiales. Algunas entradas de ayuda tenían una fecha de rastreo antigua. Por tanto, no puedo certificar que todas sus condiciones sigan idénticas hoy. La pantalla de la compra y los comprobantes concretos son necesarios para confirmar destino y acreditación. No se accedió a cuentas personales ni se eludieron restricciones.

| Fuente oficial | Qué respalda y límite |
|---|---|
| [Mercado Pago: devolución de una compra](https://www.mercadopago.com.mx/developers/pt/support/Reembolso-devoluci-n_5266) | El texto indexado describe revisión del producto y posibles reembolsos anticipados; normalmente mismo medio, con excepciones a Mercado Pago para determinadas compras. El detalle de compra informa destino y acreditación. La ruta de idioma no se usa para importar políticas de otro país: el dominio y contenido consultados son México; vigencia completa no comprobable. |
| [Mercado Pago: compra cancelada](https://www.mercadopago.com.mx/ayuda/devolver-dinero-compra_1601) | Diferencia tarjeta, dinero en Wallet y Meses sin Tarjeta. En este último producto, distingue cancelación de cuotas y reintegros totales/parciales. **Meses sin Tarjeta no equivale a MSI de Nu.** No extrapolo sus reglas a una tarjeta Nu. |
| [Mercado Libre México: gestión de devoluciones](https://developers.mercadolibre.com.mx/es_mx/gestionar-devoluciones) | Documenta devoluciones por reclamo, tipos y estados logísticos. Esos estados no certifican un abono ya reflejado en Nu. Se revisó contenido indexado; acceso directo bloqueado. |
| [Mercado Pago: pagar desde app o web](https://www.mercadopago.com.mx/blog/como-pagar-con-mercado-pago) | Artículo fechado 3/9/2026: saldo, tarjeta y transferencia son opciones distintas. Que exista una recompra no prueba cuál se eligió. |
| [Mercado Pago: retirar dinero](https://www.mercadopago.com.mx/blog/retirar-dinero-mercado-pago-sin-comisiones) | Describe transferir a cuenta bancaria mediante CLABE. No demuestra que una transferencia concreta haya ocurrido ni que el destino sea la tarjeta de crédito. No se prometen plazos ni comisiones universales. |
| [Nu: pagar la tarjeta](https://blog.nu.com.mx/productos-nu/tarjeta-de-credito/pagar-la-tarjeta-de-credito-nu/) | Distingue opciones de pago y datos para pagar la tarjeta por SPEI; la acreditación puede depender del método. Una CLABE de pago de tarjeta no debe confundirse con la cuenta de depósito. |
| [Nu: pago automático desde Cuenta Nu](https://blog.nu.com.mx/productos-nu/tarjeta-de-credito/pago-automatico-de-la-tarjeta-de-credito-nu/) | Requiere configuración y dinero disponible para ejecutar el cargo. Depositar en Cuenta Nu y pagar la tarjeta son acontecimientos distintos, aunque después exista un pago automático. Lectura directa disponible. |

La documentación distingue recibir dinero, gastarlo y enviarlo. **No prescribe el acuerdo entre tú y tus familiares** ni permite conocer si un movimiento concreto quedó guardado en Valenza. Tampoco confirma la regla exacta de aplicación de devoluciones a cada corte/MSI de Nu: no se inventó esa equivalencia.

## 6. Reconstrucción del recorrido de los $56.58

Esta tabla describe la compra aislada, sin otros movimientos ni pagos. Los importes de deuda no son los saldos totales de tu tarjeta actual.

| Paso | Hecho económico / registro esperado | Comportamiento comprobado | Tarjeta / participaciones / interfaz |
|---|---|---|---|
| A. Compra $602.87 | Productos por ese importe; conservar detalle y responsables. | Pedido y evidencia originales separados. | Asignación bruta $602.87 según reparto explícito. Visible en Pedidos. |
| B. Descuento $60.29 | Beneficio personal aprobado, no efectivo cobrado. | `discount_cents=6029`; asignaciones originales no se rebajan automáticamente. | No se suma a dinero recibido ni se vuelve a restar después. |
| C. Cargo $542.58 | Obligación original con la tarjeta: $602.87 − $60.29. | `charged_cents=54258`. | La deuda de esta operación es $542.58 antes de pagos/reembolsos bancarios. |
| D. Reembolso $186.57 a Wallet | Activo recuperado en Mercado Pago; no es abono a Nu. | Pendiente: sin efecto. Acreditado: un `REFUND` en Wallet y ajuste al producto. | Tarjeta sigue $542.58. Wallet registrada suma $186.57. Responsabilidad final del producto depende del reparto confirmado. Destino/estado visibles. |
| E. Recompra $129.99 | Nueva compra; confirmar su medio de financiación. | Si se usa el flujo vinculado, exige la misma Wallet y registra pedido por $129.99. Su cuenta adicional queda neutralizada por ajuste. | Tarjeta sigue $542.58; Wallet baja a $56.58. El original incorpora la responsabilidad del sustituto, sin cobrarlo otra vez en el pedido vinculado. |
| F. Remanente $56.58 | Dinero que confirmas que permanece en Wallet. | La resta del flujo Wallet es $186.57 − $129.99. La casilla de compensación no lo retira. | No hay pago a Nu ni cobro familiar automático. El saldo agregado registrado y el remanente de esta operación son conceptos distintos. |
| G. Uso futuro | Solo registrar cuando ocurra realmente, distinguiendo compra, transferencia a cuenta y pago a tarjeta. | No hay servicio específico que rastree por reembolso todos esos usos. El pago bancario existente sí registra un pago real global. | Falta vínculo estructurado entre reembolso, transferencia y pago. No se reconstruye desde cantidades coincidentes. |

### La financiación de la recompra no se puede deducir solo de la resta

Si estuviera pagada íntegramente con esa Wallet, el recorrido anterior sería el que el flujo vinculado registra. Si la recompra se hubiera cargado íntegramente a la misma tarjeta, sin otros movimientos, la deuda de esta operación sería $672.57 y el reembolso conservaría $186.57 en Wallet hasta otra salida. Una combinación de medios produciría otra distribución.

Tu confirmación de que hoy quedan $56.58 no identifica por sí sola la financiación histórica de cada operación si pudo haber otros movimientos. Un vínculo guardado en Valenza demostraría **qué se declaró en el programa**, no sustituiría el comprobante del medio realmente utilizado.

### Los $207 y los aproximadamente $21

En la reproducción sintética, el producto vale **$207.79**:

```text
Diferencia original no reembolsada: 207.79 − 186.57 = 21.22
Sobrante después de recomprar:       186.57 − 129.99 = 56.58
Con compensación en el reparto:     207.79 −  56.58 = 151.21
Responsabilidad explicada:           21.22 + 129.99 = 151.21
```

Asignar $21.22 a Yo y $129.99 a la persona beneficiaria es una opción de reparto implementada; **no acredita que hayas aportado o cobrado ese dinero**. Debe corresponder al acuerdo confirmado. No se asume que lo guardaste.

Sin marcar aplicar sobrante, la regla actual pide repartir $207.79: diferencia original + sustituto + sobrante sin compensar. Con la casilla marcada pide $151.21. **En ambos casos quedan físicamente $56.58 en la Wallet del escenario.** El sistema conserva esa elección y sus revisiones; no significa que la misma elección sea apropiada para todos los acuerdos familiares.

El costo efectivo comparativo del conjunto, si la recompra está vinculada, es $542.58 − $186.57 + $129.99 = **$486.00**. Esa cifra **no es** la deuda con Nu: antes de un pago real, siguen debiéndose $542.58 y existe el activo de $56.58 en Wallet. Restarlo otra vez del costo duplicaría el beneficio.

## 7. Movimientos que deben mantenerse separados

| Movimiento | Registro existente | Efecto correcto en deuda / cobros |
|---|---|---|
| Reembolso a Wallet | Devolución acreditada + movimiento en Wallet. | No baja Nu. Puede cambiar responsabilidad por el producto, sin inventar dinero recibido del familiar. |
| Reembolso directo a tarjeta | Movimiento `REFUND` en esa tarjeta. | Baja esa deuda cuando se registra acreditado. El programa confía en la fecha/destino capturados; no consulta Nu. |
| Recompra vinculada | Pedido nuevo + vínculo + revisiones. | Gasto de Wallet; sin segunda cuenta por cobrar del sustituto. No vuelve a cargar la tarjeta original. |
| Compensación del sobrante | `applied_cents` y ajustes familiares. | Cambia participación; no cambia Wallet física, cobros recibidos ni deuda bancaria. |
| Transferencia a Cuenta Nu | Sin entidad enlazada específica. | Cambia ubicación del dinero; no debería registrarse como pago de tarjeta solo por decir «Nu». |
| SPEI al destino de pago de tarjeta | Pago bancario global si realmente corresponde a ella. | Reduce deuda mediante `institution_payment`; no exige repartirlo por pedido. El origen Wallet no queda enlazado. |
| Abono familiar | `user_payment` + aplicación activa. | Reduce pendiente de esa persona; no paga al banco. |
| Aporte de Yo | Abono personal si se registra como tal. | Distinto de reasignar a Yo una responsabilidad. No demuestra una transferencia externa. |

Un pago `ACTIVE` en Valenza significa registrado y no anulado, **no una confirmación automática de Nu**. Registrar como pago algo que aún no corresponde a la tarjeta puede producir una diferencia de conciliación; no es evidencia de que el servicio reconozca una transferencia bancaria real.

## 8. Riesgos de duplicación: evidencia y clasificación

| Riesgo | Resultado | Evidencia / límite |
|---|---|---|
| Restar dos veces el reembolso al banco en el flujo importado | **Descartado en escenarios probados. Correcto.** | Se conserva cargo $542.58; a tarjeta llega un único movimiento $186.57 y queda $356.01. A Wallet, el banco permanece $542.58. |
| Restar otra vez el descuento personal | **Descartado en escenarios probados. Correcto.** | `charged_cents` ya contiene el descuento. `order_benefit_summary` agrupa raíz y recompra una sola vez. |
| Cobrar otra vez el sustituto en recompra vinculada | **Descartado en escenarios probados. Correcto.** | Pedido vinculado de $129.99 con cuenta neutralizada y revisión del original; sin abono ficticio. |
| Repetir confirmación de acreditación | **Descartado. Correcto.** | Dos confirmaciones con la misma fecha crean un movimiento y una acreditación auditada. Otra fecha se rechaza. |
| Registrar otra recompra con el mismo reembolso | **Descartado en el flujo vinculado. Correcto.** | Clave primaria `refund_id` y validación de vínculo existente. No equivale a control universal de cualquier uso posterior. |
| Wallet convertida automáticamente en pago a Nu | **Descartado. Correcto.** | Movimientos separados; cero pagos bancarios después de reembolso/recompra/compensación. |
| Compensación registrada como cobro familiar | **Descartado. Correcto, pero mal explicado.** | Ajustes separados; sin nuevas filas `user_payment` o `receipt_application`. |
| Devolución parcial aplicada a productos ajenos | **Descartado en casos probados. Correcto.** | Ajustes por `product_index` y persona; producto completo probado sin alterar el resto. No se guarda cantidad de unidades devueltas como seguimiento logístico independiente. |
| Anular original/recompra dejando crédito huérfano | **Bloqueado. Correcto con limitación funcional.** | `cancel_order` rechaza esos pedidos. Falta una reversión integral si se requiere corregir el hecho económico. |
| Abono anulado que sigue contando como recibido | **Protegido por consultas y pruebas relacionadas.** | Reversión de aplicaciones y filtro de estado del abono; inconsistencias legadas se detectan. No se repararon bases. |
| Introducir otra vez el mismo reembolso por un movimiento genérico | **Riesgo reproducido de falta de vínculo entre rutas.** | Añadir deliberadamente otro `REFUND` de $186.57 con referencia distinta deja Wallet en $373.14, aunque hay una sola devolución de producto. Misma referencia externa sí se bloquea. Esto no demuestra que el importador lo duplique ni que haya sucedido en tu caso. |
| Usar el remanente en pago y seguir tratándolo como disponible | **Falta trazabilidad o información.** | Tras registrar un pago real $56.58, Nu queda $486.00 pero Wallet registrada sigue $56.58: el pago no lleva origen de fondos. Podría provenir de otra cuenta; no puede inferirse que el saldo sea falso sin ese dato. |
| Transferencia a depósito registrada como pago de crédito | **Riesgo de captura; no confusión automática reproducida.** | El servicio exige instrumento de crédito, pero no valida un comprobante externo ni el propósito de una transferencia. |
| Recompra manual duplicada fuera del vínculo | **Pendiente para el caso real; riesgo de información.** | Una compra ordinaria independiente no se convierte automáticamente en la recompra de un reembolso. No es legítimo declarar duplicación solo por importe igual. |

**Defectos confirmados de cálculo automático en este alcance: ninguno reproducido.** Lo reproducido entre rutas genéricas exige una entrada duplicada deliberada; se clasifica como falta de identidad compartida, no se usa para cambiar reglas contables.

## 9. Interfaz: qué se puede consultar hoy

En **Pedidos**, seleccionar el original muestra «Devolución, recompra y compensación»: producto, importe, destino, estado/fecha, reparto anterior y efectivo; si hay vínculo, importe/fecha/medio de recompra, sobrante aplicado y pendiente original. Los botones permiten acreditar pendientes y registrar o editar el reparto de la recompra.

La previsualización de importación muestra Wallet registrada y prevista, y advierte expresamente que aplicar el sobrante al reparto no retira dinero ni paga al banco. El diálogo de recompra explica diferencia original, sustituto y sobrante sin aplicar. Esa explicación no queda igual de destacada en todos los puntos de consulta.

**Cobros**, Inicio y estados familiares usan las participaciones ajustadas. La presentación familiar también incorpora referencias a devolución/recompra sin sumarlas otra vez. **Tarjetas** muestra saldos registrados por instrumento y pagos bancarios; la conciliación conserva observaciones informativas.

Ya existen datos para mostrar mejor el destino, el vínculo, la compensación y el remanente inicial. No existe información suficiente para mostrar como hecho «los $56.58 se transfirieron a Cuenta Nu» o «financiaron el pago X». El historial de auditoría tiene más detalle que la pantalla, pero no reemplaza los datos que nunca se capturaron.

El problema es principalmente **presentación y trazabilidad**, con limitaciones de persistencia para usos posteriores. No se justificó modificar las fórmulas de Inicio, Cobros o deuda bancaria.

## 10. Información que no puede rastrearse con precisión

- Identidad del reembolso del proveedor y su conciliación completa con una transacción externa: `source_key` identifica comprobante/producto, no una verificación en Mercado Pago.
- Varias acreditaciones parciales sucesivas del mismo producto y sus distintos destinos.
- Recompra financiada parcialmente con Wallet y parcialmente con tarjeta dentro del flujo vinculado.
- Origen estructurado del pago bancario: Wallet, otra cuenta o efectivo del titular.
- Transferencia entre Wallet y Cuenta Nu, y pago posterior de crédito como dos hechos enlazados.
- Consumo de un reembolso en varias compras, retiros o transferencias posteriores.
- Saldo general real de Mercado Pago: entradas, retiros, rendimientos, bloqueos y otras operaciones no registradas.
- Estado actual del caso personal, acuerdo familiar definitivo y posible aplicación del sobrante.

Guardar un texto en `reference` o comparar cantidades puede ayudar a investigar, pero no proporciona integridad referencial ni impide aplicar dos veces una misma fuente de dinero.

## 11. Relación con conciliación bancaria de Nu

Un reembolso a Wallet correctamente capturado **no explica por sí solo que Nu muestre menos deuda**. El banco no recibió ese dinero. La comparación debe mantener ambos conceptos separados.

Sí pueden explicar diferencias: reembolso realmente acreditado en tarjeta aún pendiente en Valenza; pago bancario omitido o registrado antes de su reflejo; recompra que se capturó en Wallet pero realmente cargó a tarjeta; cargos o devoluciones faltantes; duplicación de captura; periodos o tipos de saldo distintos.

En el escenario aislado de banco $542.58, introducir $356.01 como deuda bancaria produce una diferencia de −$186.57. Guardar esa observación **no convierte** el reembolso de Wallet en abono a tarjeta ni modifica saldos. Se verificó comparando todas las tablas financieras antes/después.

Si un pago real de $56.58 se registra después, la deuda de la operación baja de $542.58 a $486.00. No debe descontarse también otra vez de la participación por el solo hecho de pagarse al banco. El pago puede ser un lote global con otras aportaciones; no necesita convertirse en un pago por pedido.

La conciliación seguirá informativa. Una diferencia no autoriza generar reembolsos, transferencias, cobros ni ajustes compensatorios.

## 12. Alternativas sin implementación

### Alternativa A — Seguimiento de solo lectura con datos existentes

Añadir un apartado breve **«Seguimiento del reembolso» dentro del detalle del pedido**, sin pantalla nueva:

```text
Recibido en Wallet:                    $186.57 · fecha registrada
Recompra vinculada:                    $129.99 · medio declarado
Remanente inicial de esta operación:    $56.58
Compensación en el reparto familiar:    [importe realmente guardado]
Uso posterior del remanente:            no rastreado por Valenza
```

El ejemplo solo se mostraría cuando los registros realmente lo respalden; si no hay recompra vinculada no se inventaría la resta. La compensación tendría una explicación corta: **«Cambia el reparto; no mueve dinero ni paga Nu»**. El remanente llevaría la aclaración **«No confirma saldo disponible actual»**. La deuda de la tarjeta se consultaría aparte, sin atribuirle un pago procedente de ese reembolso.

**Ventajas:** aprovecha importe, destino, fechas, pedido vinculado y auditoría existentes; sin migración ni riesgo contable nuevo; resuelve la confusión actual de vocabulario y localización.

**Limitaciones:** no controla consumos posteriores ni prueba el origen de pagos bancarios. No promete cero duplicaciones entre rutas externas. La precisión depende de lo capturado.

**Riesgo y efecto contable:** bajo si solo lee y deriva importes en centavos. Riesgo de presentación si se llama «disponible» a una resta histórica o se presenta una compensación como efectivo enviado. No cambia saldos, cobros ni pagos.

### Alternativa B — Persistencia mínima de usos del reembolso

Solo si necesitas registrar después **qué pasó con el remanente** y controlar su consumo, capturar usos concretos asociados al `refund_id`: importe, fecha, tipo de salida, destino, referencia, estado/reversión y vínculo al movimiento **ya existente** cuando lo haya. La selección de almacenamiento requiere diseño y aprobación posteriores; esta investigación no justifica por sí sola crear otra tabla.

La compensación familiar se mantendría separada del consumo físico. Una recompra ya vinculada contaría una sola vez. Si Wallet sale hacia Cuenta Nu y luego se paga la tarjeta desde allí, el primer paso consume la salida de Wallet; el segundo puede enlazarse como continuación, **sin consumir otra vez el mismo remanente**. Un pago global podría financiarse con varias fuentes, sin dividirlo en pagos bancarios por pedido.

**Ventajas:** permite identificar usos posteriores y limitar la suma de salidas activas a lo recuperado, sin administrar toda la cuenta Mercado Pago.

**Limitaciones:** sigue requiriendo evidencia/captura del usuario; no verifica movimientos bancarios ni descubre operaciones omitidas. Una nota informativa sin validaciones no basta para evitar duplicaciones.

**Riesgos y efecto contable:** moderados por concurrencia, anulaciones, fondos mixtos, enlaces rotos e históricos incompletos. Debe ser un registro de procedencia; no generar otro pago, otro cobro ni un ajuste financiero al vincular un movimiento. No asignar automáticamente usos históricos por importe coincidente.

**Recomendación:** A para la situación confirmada —el dinero sigue en Wallet—. B solo si decides controlar su recorrido posterior. A no debe venderse como seguimiento completo que no puede ofrecer. No recomiendo un administrador general de Wallet.

## 13. Validación ejecutada y pruebas futuras

Se ejecutaron las suites existentes `test_product_refunds.py`, `test_product_refund_preview.py`, `test_refund_agreement_investigation.py`, `test_bank_reconciliation.py` y `test_bank_manual_completion.py`: **119 casos aprobados, 0 fallidos, 0 omitidos**, en bases sintéticas cifradas. No se modificaron esas pruebas ni producción.

Adicionalmente se ejecutó un script privado con **8 escenarios documentados**, incluyendo dos rechazos de financiación inválida y comprobaciones de reversión:

1. Recompra con compensación desmarcada: banco $542.58, Wallet $56.58, participación del producto $207.79.
2. Recompra con compensación marcada: banco $542.58, Wallet $56.58, participación del producto $151.21; cero cobros/pagos automáticos.
3. Abono familiar de $10 y su anulación; pago bancario de $56.58 y su anulación: efectos separados; ausencia de origen Wallet estructurado.
4. Conciliación con diferencia de −$186.57 sin cambios en tablas financieras.
5. Acreditar dos veces una devolución pendiente genera un único reembolso.
6. Recompra desde tarjeta o por importe superior al reembolso: rechazo sin escrituras parciales.
7. Devolución completa del producto: conserva tarjeta y demás productos.
8. Alta genérica duplicada deliberada con referencia distinta: riesgo entre rutas; misma referencia externa bloqueada.

Evidencia local en `private/codex/auditoria-integral-20261016/`: `wallet-investigacion-suite.xml`, `wallet-investigacion-casos.json`, `wallet-historico-evidencia.json` y scripts de investigación. La copia histórica se abrió en solo lectura y su fuente se verificó sin cambios. El proceso de pruebas bloqueó acceso a bases fuera de la carpeta aislada y conexiones de red. La consulta pública de documentación fue independiente y no envió información personal.

Antes de implementar A: verificar lectura sin escrituras, pedido sin devolución, pendiente/acreditado, destinos tarjeta/Wallet/otro, recompra vinculada o ausente, ambas opciones de compensación, cantidades compartidas, nombres largos, ventanas pequeñas y mensajes que no prometan disponibilidad real.

Antes de B: conservación exacta de centavos; dos usos que excedan fondos; doble clic y concurrencia; cancelación y restauración; financiación mixta; transferencia seguida de pago sin doble consumo; pago global con varias fuentes; movimiento ya anulado; cambios de fecha/destino; comprobantes repetidos; reapertura y respaldo cifrado; consistencia entre historial y vistas. Congelar saldos y todas las tablas financieras para demostrar que enlazar procedencia no crea movimientos adicionales. Ejecutar después la regresión relacionada y la completa.

## 14. Confirmaciones pendientes y decisión

Para reconstruir el caso real, sin dar nada por guardado, faltaría confirmar con evidencia autorizada:

- Medio real de pago de los $129.99 y si existe pedido vinculado en una copia vigente.
- Si se marcó aplicar el sobrante y qué reparto se guardó; no inferirlo de los $56.58 actuales.
- Valor del producto devuelto y acuerdo sobre quién asume los aproximadamente $21; $21.22 solo es exacto bajo el producto sintético de $207.79.
- Si cualquier aporte familiar/personal ocurrió realmente y cómo se registró.
- Si la necesidad futura es solo consultar el recorrido o también registrar usos posteriores del remanente.

No se requiere repetir estas operaciones ni crear pagos para responderlas. Tu confirmación actual de **$56.58 aún en Wallet, no transferidos ni pagados a Nu**, se conserva como hecho y no como instrucción contable.

**Conclusión:** Valenza ya maneja el núcleo de devolución, recompra y compensación sin duplicación automática reproducida. Lo que no tiene es un seguimiento completo del destino posterior de cada peso recuperado. Para este caso, la primera mejora justificable es explicar y mostrar los registros existentes; ninguna modificación financiera está autorizada o implementada por este diagnóstico.
