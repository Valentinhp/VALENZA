# VALENZA — Etapa 1: auditoría integral de claridad y facilidad de uso

Fecha: 17 de octubre de 2026. Estado: diagnóstico entregado; implementación pendiente de autorización.

## 1. Alcance, método y límites

Esta etapa investiga la interfaz existente. No modifica código de producción, fórmulas, tablas, migraciones ni datos del usuario. No se abrió la base real ni la TEST original, no se instalaron dependencias, no se publicó nada ni se generaron ejecutables. Revisar efectivo se inspeccionó sin modificarlo.

Se revisaron las siete páginas de navegación, sus acciones, los principales diálogos y las fuentes de los indicadores. Se contrastaron código, documentación, pruebas de interacción y capturas actuales con una base SQLCipher nueva y exclusivamente sintética. Las migraciones y escrituras de preparación de fixtures ocurrieron únicamente en esas bases desechables. El proyecto ya tenía numerosos cambios anteriores a esta auditoría; este documento no atribuye esos cambios a esta etapa.

Evidencia visual actual: [siete páginas](../artifacts/claridad-vistas/), [diálogos y detalles](../artifacts/claridad-detalles/). Las capturas principales corresponden a una ventana de 820 × 600 unidades lógicas; la captura de Tarjetas con selección, a 680 × 480. La escala del entorno produce imágenes con más píxeles que esas dimensiones. Se cargaron fuentes de Windows mediante la fixture existente.

Pruebas ejecutadas: `test_ux_block1.py`, `test_ux_block2.py`, `test_ux_block3.py` y `test_cash_cut_files.py`: **42 casos, 40 aprobados y 2 fallidos**. Los fallos son las variantes de tamaño 1100 × 760 y 1360 × 900 de `test_all_seven_pages_keep_controls_and_financial_data`: se obtuvieron 1100 × 700 y 1283 × 700 respectivamente. Fallaron antes de recorrer las páginas; no prueban pérdida de datos ni un recorte concreto. Es necesario repetirlos con una superficie de escritorio suficiente. Las variantes 680 × 480 y 820 × 600 sí completaron el recorrido.

Comando: `.venv\Scripts\python.exe -m pytest tests/test_ux_block1.py tests/test_ux_block2.py tests/test_ux_block3.py tests/test_cash_cut_files.py -q -p no:cacheprovider --basetemp=artifacts/auditoria-claridad-20261017`.

Las capturas de pytest no pudieron abrirse por permisos del entorno, incluso tras intentar copiarlas con elevación. Se generaron otras capturas accesibles con la misma fixture sintética, sin modificarla. No se usaron capturas antiguas para declarar defectos actuales.

Tipos de evidencia:

- **Confirmado:** comportamiento visible o explícito en un manejador de la interfaz. No equivale necesariamente a fallo de cálculo.
- **Recomendación:** interpretación de diseño que debe validarse con el usuario.
- **Pendiente de comprobación:** no debe convertirse en una corrección automática.

No se realizó una prueba con usuarios externos ni una certificación financiera. La cobertura de todas las secciones no significa haber ejecutado todas las combinaciones de documentos, registros o errores del sistema operativo.

## 2. Diagnóstico general

Valenza tiene funciones de consulta, respaldo, desglose, corrección y recuperación que ya resuelven buena parte de las necesidades. El problema principal es la distancia entre la existencia de esas funciones y la facilidad para descubrirlas y comprender su alcance.

La distinción entre cobros familiares y pagos bancarios está presente y debe conservarse. También hay avances concretos: borradores de gastos identificados como temporales, confirmaciones para anular, comparaciones bancarias con advertencias, consultas históricas separadas de saldos actuales y conteos guardados que ya se pueden consultar, abrir y exportar.

Quedan tres fricciones principales: información de periodos repartida entre etiquetas y ayudas, resultados de acciones comunicados solo de forma transitoria, e historiales operativos que no siempre permiten comprender la secuencia de correcciones. No hace falta un rediseño general.

**No se confirmó un defecto crítico que produzca un cálculo incorrecto o haga imposible utilizar una función.** Sí hay problemas altos de comunicación que pueden llevar a interpretar mal una cifra o el alcance de una acción. La clasificación no supone que un error financiero ya haya ocurrido.

## 3. Inventario de pantallas y acciones

| Pantalla o recorrido | Acciones existentes y acceso | Experiencia y límites observados |
| --- | --- | --- |
| Desbloqueo | Contraseña, Mostrar/Ocultar, Desbloquear, Cancelar | Formulario breve, foco y visibilidad de contraseña cubiertos por pruebas. No requiere nuevos campos. Fuente: `gui/unlock.py`. |
| Inicio | Mes, accesos a Pedidos/Cobros/Tarjetas, Revisar efectivo, Ver desglose, Mostrar importes, Ver cómo se calcula, calendario, detalle bancario, desglose por persona, PDF, recientes | Mucha información en una página desplazable. El selector de mes no filtra todos los indicadores. Las tarjetas de cifras no tienen todas un acceso directo a sus componentes. |
| Usuarios | Crear persona, Guardar persona, Desactivar, Reactivar, Limpiar selección | Conviven creación y edición en el mismo formulario. Se conservan movimientos al desactivar. El término Usuarios puede sugerir cuentas de acceso que aquí no se administran. |
| Pedidos | Nuevo gasto, Importar PDF, filtro Activos/Anulados/Todos, Editar comercio, Editar conceptos y reparto, devolución, recompra, MSI, anular | Hay grupos de acciones y detalle del pedido seleccionado. En tamaños reducidos el detalle queda después de varios grupos y la tabla necesita desplazamiento horizontal. |
| Gasto nuevo / edición | Comercio, fecha, cuenta, modalidad, conceptos y responsables, importes, reparto, Resumen, Guardar, cierre | MSI muestra campos adicionales. La captura nueva conserva borrador solo durante la sesión. La corrección de cargo real se confirma y guarda por separado del reparto. No debe prometerse una cancelación global. |
| Importar PDF | Selección de archivo, revisión de extracción, conceptos, responsables, cargo, devoluciones y recompra, confirmación de guardado | Incluye casos financieros complejos. Pruebas verifican cancelación, fallos y guardado. La simplificación debe preservar la vista previa y confirmaciones existentes. Fuentes: `gui/pdf_import.py` y `gui/receipt_editor.py`. |
| MSI de un pedido | Vincular plan si no existe; consultar cuotas, corregir fecha y ajustar previsión si existe | La fecha y el ajuste se guardan al aplicarlos. Hay aviso de que Cerrar no revierte. Ajustar previsión no acredita un reembolso. |
| Cobros | Selector de persona, abono global y liquidaciones con vista previa; participaciones individuales; más detalles; extras/comisiones; historial; editar/anular abono; PDF | Dos recorridos válidos para abonos, con contextos distintos. La consulta del historial individual rellena campos de captura. Conviene distinguir con claridad qué modo está activo. |
| Tarjetas | Seleccionar cuenta; desglose; comparar con banco; historial de consultas; registrar/editar/anular pago; aplicar pago a cuota; fechas; administración bancaria | La página concentra varias tareas. Paneles plegables evitan mostrar todos los formularios, pero algunos nombres son genéricos. Sin seleccionar cuenta los indicadores muestran guiones. |
| Suscripciones | Nueva, Editar, Pausar/Reactivar, Cancelar, Registrar o vincular cargo real, Eliminar definitivamente | Previsión y cargo real ya se distinguen. Cancelar es local y eliminar puede retirar registros vinculados; no son sinónimos. El editor actual puede reducir recargos anteriores. |
| Revisar efectivo | Guardar corte JSON, Guardar en la app, Nuevo conteo, Abrir corte, Conteos guardados, consulta/apertura/exportación interna | Funcionalidad corregida, preservada en esta etapa. Tres pruebas actuales verifican archivo, cancelación y consulta/exportación/apertura interna. No se propone volver a rehacerla. |
| Configuración | Propietario, Crear respaldo cifrado, Restaurar respaldo, Ejecutar diagnóstico, Mostrar resultados | **Crear y restaurar respaldos ya existe.** La restauración verifica el respaldo y exige confirmación; conserva una copia anterior. Diagnóstico no equivale a restauración. |
| Buscar / Ctrl+K | Buscar, elegir y abrir resultados | Acceso visible, sin importes por diseño. Algunas compras históricas no tienen vista directa pese a figurar en resultados. |
| Reporte por persona | Generación desde Inicio y Cobros; archivo PDF | Consulta exportada, no una edición ni respaldo completo. El éxito no incluye la ruta en el mensaje transitorio. |
| Compatibilidad histórica | Formulario antiguo fuera de navegación | Se construye por compatibilidad. No debe inventariarse como una octava sección de uso habitual ni reactivarse sin estudiar sus datos. |

Fuentes principales: `src/valenza/gui/app.py`, métodos `_make_*`, `_financial_dialog`, `_msi_dialog`, `_open_search_result`; `person_receipts.py`, `pdf_import.py`, `cash_review.py`, `cash_review_history.py`, `unlock.py` y `family_pdf.py`.

## 4. Hallazgos priorizados

Cada propuesta es mínima y queda pendiente de autorización. Los archivos se expresan relativos a `src/valenza/` salvo indicación contraria.

### H01 — Alto, confirmado: aviso de Suscripciones contradice el alcance del editor

1. **Pantalla/control:** Suscripciones, texto de selección y Editar.
2. **Actual:** sin selección se dice «Los cambios afectan ciclos futuros». Al editar existe una casilla activada por defecto para quitar o reducir también recargos de cargos registrados; su vista previa explica el efecto.
3. **Confusión:** el primer mensaje general promete un alcance que el editor actual no siempre tiene. La vista previa reduce el riesgo, pero obliga a descubrir la excepción después.
4. **Propuesta:** sustituir la promesa general por «Consulta el calendario, reparto y cargos registrados». En el editor, mantener visible el alcance elegido y el total de recargos anteriores afectados. No cambiar el valor por defecto ni la política autorizada en esta etapa.
5. **Archivos:** `gui/app.py`, `_subscription_selection`, `_edit_subscription`; `persistence/subscription_fees.py` como referencia del comportamiento que debe conservarse.
6. **Riesgo:** medio: una simplificación excesiva podría ocultar un cambio de deuda familiar. No tocar cargo bancario ni abonos.
7. **Comprobación:** suscripción con cargos previos y recargo; revisar ambos estados de la casilla, vista previa, cancelación y guardado; verificar importes con `test_subscription_fee_reduction.py`.

### H02 — Alto, confirmado: Cancelar suscripción no explicita que actúa solo en Valenza

1. **Control:** Cancelar suscripción y confirmación «¿Cancelar futuros cobros?».
2. **Actual:** cambia el estado local y conserva pedidos/pendientes. No realiza una cancelación ante el proveedor.
3. **Confusión:** «cancelar futuros cobros» puede interpretarse como detener el servicio real. El aviso actual explica la conservación de deuda, pero no el límite externo.
4. **Propuesta:** «Cancelar previsión en Valenza» o conservar el botón y añadir en la confirmación «Esto no cancela el servicio ni los cobros del proveedor». Distinguir Pausar de cancelar permanentemente la previsión.
5. **Archivos:** `gui/app.py`, `_subscription_status`; `persistence/repository.py`, `set_subscription_status`.
6. **Riesgo:** bajo si solo cambia comunicación; medio si se cambia la máquina de estados, cosa no propuesta.
7. **Comprobación:** cancelar y pausar con deuda previa; verificar que se conserva y que la confirmación describe exactamente el efecto local.

### H03 — Alto, confirmado: el selector de mes no aplica a todas las cifras de Inicio

1. **Control:** selector junto al título Inicio y tarjetas de pendientes.
2. **Actual:** el mes modifica compromisos y programación; Mi parte pendiente, Cobros familiares, deuda total, descuentos y resultado usan saldos o acumulados vigentes. La gráfica por persona tiene un alcance mensual propio. Hay advertencias en varios detalles.
3. **Confusión:** un selector ubicado en la cabecera puede parecer un filtro de toda la página. Consultar otro mes no reconstruye una fotografía del saldo de ese mes.
4. **Propuesta:** etiquetar el selector «Mes de compromisos» y las cifras acumuladas «Saldo actual» o «Acumulado de pedidos activos», según corresponda. Mantener la advertencia al consultar meses anteriores.
5. **Archivos:** `gui/app.py`, `_make_dashboard`, `_refresh_dashboard`; `gui/home_month_summary.py`, `gui/home_people_month.py`, `gui/personal_result.py`.
6. **Riesgo:** medio: no convertir la etiqueta en un cambio de filtros o fórmulas.
7. **Comprobación:** mismo conjunto sintético en tres meses; documentar qué indicadores cambian y cuáles permanecen; comprobar la suma de cada desglose.

### H04 — Alto, confirmado: Inicio y Tarjetas no muestran el mismo concepto mensual

1. **Control:** «Compromisos del mes · tarjetas» frente a «Correspondiente al mes · previsto» y su detalle.
2. **Actual:** Inicio calcula un residual de deuda actual después de separar cuotas futuras, anteriores y sin fecha, con mínimo cero por instrumento. Tarjetas calcula programación por vencimiento, pagos identificados y advertencias de información incompleta.
3. **Confusión:** dos importes mensuales distintos pueden parecer una contradicción. No se confirmó una fórmula incorrecta; las bases son deliberadamente diferentes.
4. **Propuesta:** conservar las fórmulas y mostrar junto al detalle una frase específica: «Pendiente actual atribuido a este mes» para el primero y «Programado para vencer este mes, antes de pagos» para el segundo cuando ese sea el valor presentado. Explicar el pendiente identificado por separado.
5. **Archivos:** `gui/home_month_summary.py`, `persistence/bank_periods.py`, `gui/bank_reconciliation.py`, `gui/app.py`.
6. **Riesgo:** alto si se intenta igualar cifras cambiando cálculos; medio si se limita a textos y desgloses.
7. **Comprobación:** compras normales y MSI, pagos sin asignar, cuotas sin fecha y reembolso acreditado; preservar resultados de las pruebas mensuales existentes.

### H05 — Alto, confirmado: algunos éxitos no permiten volver a encontrar lo guardado

1. **Control:** mensajes de guardado generales y exportación PDF.
2. **Actual:** `_show_information` usa la barra de estado durante diez segundos. «Gasto guardado», «Suscripción actualizada» y «Estado de cuenta PDF generado» no ofrecen siempre destino o siguiente paso. Respaldos y cortes sí tienen mensajes con ruta más completos.
3. **Confusión:** si el mensaje desaparece, el usuario no distingue con facilidad archivo, registro interno o actualización. No implica que el guardado falle.
4. **Propuesta:** feedback persistente junto a la acción, con objeto y ubicación: «Guardado en Pedidos: comercio…»; para archivos, nombre y ruta seleccionada. Reutilizar selección del registro ya guardado; no agregar otra lista de historial global.
5. **Archivos:** `gui/app.py`, `_show_information`, `_save_order`, `_edit_subscription`, `_export_family_pdf`; `gui/person_receipts.py` como referencia de feedback local.
6. **Riesgo:** bajo en presentación; verificar que nunca se muestre éxito antes del commit ni se mantenga un éxito anterior tras un fallo.
7. **Comprobación:** éxito, cancelación y error por operación; revisar tras diez segundos que aún se pueda identificar el resultado y localizarlo.

### H06 — Alto, confirmado: Buscar promete abrir una compra histórica sin vista directa

1. **Control:** resultado de tipo `purchase` en Buscar.
2. **Actual:** `_open_search_result` abre Cobros, limpia selecciones y avisa «No hay una vista directa de esta compra»; no selecciona el registro buscado.
3. **Confusión:** «Abrir» conduce a una sección sin el objeto seleccionado. El usuario debe buscarlo otra vez y puede pensar que se perdió.
4. **Propuesta:** seleccionar las participaciones existentes relacionadas con esa compra y llevar al detalle de solo consulta. Si no es posible, identificar en el resultado «Ver participaciones en Cobros» y explicar la limitación antes de activar.
5. **Archivos:** `gui/app.py`, `_open_search_result`; `gui/search.py`, `persistence/search.py`.
6. **Riesgo:** medio por navegación y selección; no revivir el editor histórico como solución automática.
7. **Comprobación:** compra histórica sintética, varias personas, filtros activos y registro inexistente; abrir debe ubicar el objeto correcto sin escribir datos.

### H07 — Medio, confirmado: detalles normales muestran identificadores técnicos

1. **Control:** desglose del resultado personal y detalle de recompras.
2. **Actual:** `_show_result_breakdown` agrega `order_id` a cada operación. El detalle de recompra puede imprimir el identificador del pedido original. Las tablas principales ya ocultan sus columnas ID.
3. **Confusión:** un UUID o identificador interno no ayuda a reconocer una compra y hace el texto más difícil de leer.
4. **Propuesta:** usar comercio, fecha y referencia comprensible; reservar ID para información técnica desplegable. No cambiar claves ni referencias persistidas.
5. **Archivos:** `gui/app.py`, `_show_result_breakdown`, `_show_order_detail`; `gui/refund_tracking.py`.
6. **Riesgo:** bajo en texto; medio si se elimina un identificador necesario para desambiguar registros iguales.
7. **Comprobación:** dos pedidos del mismo comercio y fecha deben seguir distinguiéndose; detalle y búsqueda deben apuntar al registro correcto.

### H08 — Medio, confirmado: consultar un abono también rellena campos operativos

1. **Control:** selección en historial de Cobros.
2. **Actual:** `_select_receipt_history` selecciona el abono y rellena importe, fecha y referencia del formulario. Existen botones explícitos de editar/anular y señales de selección.
3. **Confusión:** la transición de consulta a posible edición se mezcla visualmente con la captura de un abono. No se confirmó que la selección por sí sola modifique datos.
4. **Propuesta:** un encabezado persistente «Consultando abono del…»; dejar los campos de consulta de solo lectura hasta pulsar Editar, o diferenciar claramente el editor existente sin duplicarlo. Mostrar cómo volver a «Nuevo abono».
5. **Archivos:** `gui/app.py`, `_select_receipt_history`, `_edit_selected_receipt`, `_toggle_collection_history`; `gui/receipt_editor.py`.
6. **Riesgo:** medio: conservar aplicaciones de abonos globales y no crear un segundo abono al editar.
7. **Comprobación:** consultar no escribe; editar modifica el mismo ID; cancelar no cambia saldos; nuevo abono no reutiliza accidentalmente la selección anterior.

### H09 — Medio, confirmado: historiales operativos no explican toda la secuencia de cambios

1. **Control:** historial de pagos, abonos y detalle de pedidos/suscripciones.
2. **Actual:** pagos y abonos muestran registros y estados; los eventos de auditoría se conservan en persistencia, pero no se encontró una vista general de antes/después por registro en la navegación. Suscripciones anuncia conservar historial sin ofrecer en su ficha una lista de ciclos/cambios equivalente al historial de consultas bancarias.
3. **Confusión:** «se conserva el historial» puede hacer esperar una pantalla donde consultar cada cambio. Ver el estado final o un movimiento anulado no explica por sí solo quién corrigió qué.
4. **Propuesta:** acceso contextual «Ver cambios» al registro seleccionado utilizando los eventos ya existentes; primero fecha, descripción y campos modificados. Para suscripciones, facilitar consulta de cargos vinculados existentes. Solo lectura, sin botón Restaurar.
5. **Archivos:** `gui/app.py`; `persistence/repository.py`, inserciones de `audit_event`; `persistence/subscription_delete.py` para respetar excepciones de eliminación.
6. **Riesgo:** medio/alto: no interpretar JSON de auditoría como un comando reversible ni prometer que todos los eventos contienen un estado completo.
7. **Comprobación:** editar/anular un abono y corregir un cargo; distinguir registro, versión y evento; consulta sin escrituras. Identificar expresamente los datos que no están disponibles.

### H10 — Medio, confirmado: los controles de reparto pueden requerir desplazamiento horizontal

1. **Control:** Nuevo gasto, tabla Conceptos y reparto, botón Dividir; tablas de Pedidos y Tarjetas.
2. **Actual:** en [captura del formulario](../artifacts/claridad-detalles/gasto.png), Dividir queda parcialmente fuera del área visible y se alcanza con la barra horizontal. En las tablas principales también hay columnas fuera de la primera vista. El desplazamiento existe y no se observó superposición.
3. **Confusión:** el control decisivo para repartir una compra puede parecer ausente. Esto es descubribilidad y distribución, no pérdida del control.
4. **Propuesta:** asegurar que el responsable y Dividir se vean juntos al ancho mínimo; permitir que detalles largos se expandan en la fila o en el panel de reparto ya existente. No quitar columnas contables para hacerlas caber.
5. **Archivos:** `gui/app.py`, `_make_orders_page`, `_add_manual_concept`; `gui/pdf_import.py`, `ProductAssignment`.
6. **Riesgo:** medio por componentes compartidos entre captura e importación.
7. **Comprobación:** 480/680/820 de ancho, escalas 100/125/150 %, nombres largos y reparto entre varias personas; acceso por Tab sin perder importes. Repetir tamaños grandes en escritorio suficiente.

### H11 — Medio, recomendación: acciones de Pedidos alejan la consulta del registro

1. **Control:** bloques Editar, Devoluciones y recompra, MSI/anulación y detalle.
2. **Actual:** la captura de Pedidos a 820 × 600 muestra grandes botones verticales; el usuario debe bajar para llegar a controles y detalle posteriores.
3. **Confusión:** se ofrece modificar antes de entender el pedido. No se afirma que el detalle esté inaccesible.
4. **Propuesta:** colocar el resumen del seleccionado junto a la tabla y conservar acciones secundarias en sus grupos plegables; no agregar otro editor.
5. **Archivos:** `gui/app.py`, `_make_orders_page`, `_show_order_detail`.
6. **Riesgo:** bajo/medio por foco, orden y conservación de selección.
7. **Comprobación:** seleccionar, consultar, editar y volver a la misma fila con filtros y desplazamiento conservados; recorrido por teclado.

### H12 — Bajo, recomendación: nombres distintos para el mismo objeto de consulta

1. **Controles:** Usuarios/Persona, Nuevo gasto/Pedido, PDF de la persona/Generar PDF, Más detalles/Ver desglose/Detalle bancario.
2. **Actual:** los nombres varían; algunos representan el mismo objeto y otros operaciones financieras diferentes.
3. **Confusión:** cuesta predecir qué se abrirá y si habrá escritura.
4. **Propuesta:** aplicar el vocabulario de la sección siguiente solo después de mapear el manejador de cada botón.
5. **Archivos:** `gui/app.py`, `gui/person_receipts.py`, `gui/pdf_import.py`; pruebas UX de etiquetas y accesibilidad.
6. **Riesgo:** bajo, salvo renombrar de forma indiscriminada Registrar, Aplicar, Anular y Eliminar.
7. **Comprobación:** inventario antes/después con resultado real por acción; mismo nombre accesible y visible; actualizar únicamente pruebas cuyo contrato de texto cambie con autorización.

## 5. Vocabulario coherente propuesto

| Concepto | Significado que debe conservar | Nombres y feedback propuestos |
| --- | --- | --- |
| Guardar | Persistir una creación o edición concreta | «Guardar cambios de [objeto]». Éxito: objeto, destino interno y forma de consultarlo. En archivos indicar ruta. |
| Registrar | Crear un movimiento financiero real | «Registrar abono», «Registrar pago al banco», «Registrar cargo real». No sustituir todos por Guardar. |
| Aplicar | Vincular dinero ya registrado a una obligación | «Aplicar pago a cuota». No significa registrar un pago adicional. |
| Abrir | Mostrar un archivo/registro o recuperar un conteo | «Abrir corte» para archivo; «Abrir conteo» para versión interna. Si reemplaza captura pendiente, advertirlo. |
| Nuevo | Empezar una captura sin afectar registros existentes | «Nuevo gasto», «Nueva persona», «Nuevo conteo». Indicar si el borrador anterior se conserva o descarta. |
| Editar | Entrar al modo de modificación | «Editar comercio», «Editar conceptos y reparto». No prometer editar el cargo si ese control no lo modifica. |
| Consultar / Ver | Mostrar información sin escribir | «Ver detalle del pedido», «Ver desglose de [cifra]». La vista de consulta no debe parecer un guardado pendiente. |
| Historial | Lista de movimientos o cambios anteriores | Especificar «Historial de abonos», «Historial de consultas bancarias», «Ver cambios». Conteos guardados ya tiene su nombre específico. |
| Exportar | Crear un archivo con datos existentes | «Exportar estado de cuenta PDF» en Inicio y Cobros; «Exportar JSON» en conteos. Mostrar ruta y resultado. |
| Anular | Invalidar un movimiento conservando trazabilidad | «Anular abono», «Anular pago al banco», «Anular pedido». Confirmar qué saldos se recalculan. |
| Eliminar | Retirar el objeto según el alcance real de esa operación | «Eliminar definitivamente» solo donde realmente corresponde; detallar registros vinculados y respaldo. Quitar concepto de un borrador es distinto. |
| Restaurar | Reemplazar datos activos a partir de respaldo | Reservar «Restaurar respaldo» para esa operación. Abrir un conteo no restaura la base. |

Propuestas concretas sin cambio de reglas: Usuarios → Personas; Generar PDF/PDF de la persona → Exportar estado de cuenta PDF; Preparar nueva cuenta → Nueva cuenta; Guardar persona → Guardar cambios de la persona cuando hay selección. Mantener Pedidos como nombre de sección si abarca importaciones, devoluciones y gastos; explicar que Nuevo gasto registra una compra/pedido. No es necesario cambiar todos los textos a «pedido».

## 6. Mapa de cifras: significado, cálculo, periodo y acceso

Las fórmulas siguientes describen lo existente; **no son propuestas de sustitución**. Todos los importes internos son centavos. Las filas activas, ajustes, aplicaciones y roles los determinan los métodos existentes, no una suma nueva en la interfaz.

| Cifra / pantalla | Cálculo y movimientos componentes | Periodo; qué aumenta o disminuye | Desglose actual y acceso propuesto |
| --- | --- | --- | --- |
| Mi parte pendiente — Inicio/Cobros | Suma de `remaining_cents` de `list_collection_items()` con rol PERSONAL. Incluye ajustes y abonos aplicables del modelo de participaciones. | Saldo vigente de participaciones; no solo el mes visible. Aumenta con asignaciones personales, disminuye con abonos/ajustes admitidos. Pagar al banco no es un abono personal. | Cobros, filtro Mi parte y detalle de participaciones; Inicio, personas. Proponer enlace desde el indicador al filtro existente. |
| Cobros familiares pendientes — Inicio/Cobros | Misma fuente con rol FAMILY; no sumar UNKNOWN ni previsiones de suscripción. | Saldo vigente, con MSI futuros incluidos en el pendiente total. Abonos activos reducen saldo; anularlos revierte su efecto. | Cobros, cuenta por persona y participaciones. Enlace contextual desde cifra, preservando filtro y selección previos. |
| Deuda total pendiente — Inicio/Tarjetas | Por instrumento: máximo entre cero y cargos menos pagos activos. Cargos: pedidos activos + intereses de planes + movimientos de interés/comisión/ajuste, menos reembolsos/bonificaciones acreditados. Inicio agrupa cuentas/líneas según comparaciones, una vez. | Saldo actual completo, principal MSI futuro incluido. Cobros familiares y conteos no lo reducen. Cargos aumentan; pagos bancarios y acreditaciones aplicables reducen. Anulaciones revierten su efecto. | Tarjetas y desglose bancario existentes. Acceso desde indicador a cuentas/componentes; explicar agrupación de líneas. |
| Compromisos del mes — Inicio | `home_month_summary`: por instrumento `max(0, deuda actual − cuotas pendientes futuras − anteriores − sin fecha)`; después agrupa/suma. | Mes seleccionado aplicado a saldos pendientes actuales. Pagos ya descontados en deuda. No es estado histórico ni pago oficial del banco. | Ver desglose y texto por cuenta; parte de la fórmula está en ayudas. Poner explicación breve visible dentro del desglose. |
| Correspondiente al mes / programado — Tarjetas | `period_forecast`: suma de cargos normales estimados por vencimiento, cuotas MSI (principal + interés) y otros cargos del mes. Separar pagos aplicados a cuotas y pendiente identificado. | Mes seleccionado por vencimiento; programación antes de pagos en el importe programado. Un pago sin asignar reduce deuda total, pero no se atribuye arbitrariamente a este mes. | Panel Comparar con mi banco y desglose. Cuando faltan datos se muestra «Total sin determinar»; añadir explicación y acceso a qué falta, sin inventar cero. |
| Meses futuros — Tarjetas/calendario | Tarjetas distingue programación futura y pendientes futuros; `period_forecast` calcula ambos campos. Inicio/calendario usa cuotas pendientes según sus funciones propias. | Posterior al mes elegido. Crear plan aumenta programación; aplicar pagos reduce pendiente; no confundir programación con pendiente. | Calendario completo, cuotas y ayudas. Especificar en cada título «programado» o «pendiente», conforme al campo mostrado. |
| Cuotas anteriores / sin fecha | Agrupación por vencimiento de cuotas, con distinción entre confirmado y por confirmar. | Antes del mes elegido o sin fecha utilizable. Corregir fecha redistribuye entre periodos; no crea un pago. | Desgloses y calendario existentes. No llamar vencido confirmado a un calendario sin confirmar. |
| Saldo a favor registrado | Exceso de pagos sobre cargos, calculado por instrumento con mínimo cero y agregado por resumen. | Actual; no es dinero físico contado ni garantía de saldo disponible en Wallet. Más pagos lo aumentan y nuevos cargos lo consumen según el modelo. | Etiqueta condicional en Inicio, detalle de Tarjetas. Enlazar a cuenta y componentes, sin presentarlo como efectivo disponible. |
| Último saldo banco / diferencia histórica | Consulta manual con tipo, fecha/hora, alcance y fotografía calculada al guardarse. Diferencia tomada de la consulta guardada, no recalculada contra deuda actual. | Fecha de consulta, independiente del mes visual actual. Una consulta no crea deuda ni pagos. Comparación solo si el alcance es válido. | Historial de consultas y `query_text`; acceso disponible. Mantener fecha y tipo visibles al lado del importe. |
| Descuentos personales — Inicio/Pedidos | `dashboard_summary`: suma de descuentos de pedidos activos; beneficio de operación en detalle del pedido. | Acumulado vigente, no ahorro de un mes seleccionado. Cambia al cambiar los pedidos activos correspondientes. No es dinero cobrado. | Ayuda y detalle por pedido; el resultado personal tiene desglose relacionado, pero no un listado directo exclusivo del indicador. Proponer acceso a pedidos componentes. |
| Resultado personal previsto | Suma de `expected_result_cents` de operaciones raíz activas en `order_benefit_summary`; recompra vinculada incluida una vez. El signo compara lo asignado a familiares con el costo efectivo de la operación; no es caja recibida. | Operaciones activas, antes de abonos personales; excluye intereses/comisiones conforme a explicación actual. Cambia con costo/reparto/devolución/recompra admitidos. | Ver cómo se calcula y detalle de pedido ya existen; respetar privacidad y retirar IDs del texto principal. |
| Mi parte menos descuentos | Pendiente PERSONAL menos descuentos de pedidos activos. Comparación informativa, no ajuste de deuda familiar o bancaria. | Acumulado vigente; cambia con abonos personales/descuentos, no es lo mismo que resultado previsto. | Ver desglose de Inicio. Mantenerlo como detalle secundario, con componentes enlazados. |
| Abonos familiares realmente recibidos | Suma de `user_payment.amount_cents` activos, tipo FAMILY, una vez por pago; no una vez por cada aplicación. | Acumulado vigente, no filtrado por mes de Inicio. Registrar suma; anular resta. Reembolso y aportación personal no pertenecen a esta cifra. | Historial de Cobros. Enlace con tipo FAMILY; distinguir importe del pago de importes aplicados a cada pedido. |
| Asignado / Abonado / Pendiente — Cobros | Participaciones ajustadas, aplicaciones activas y pendiente del modelo. Abono global: un ingreso con varias aplicaciones. | Saldo vigente por persona o participación; actual/futuro/sin fecha de `person_receipt_accounts`. | Cuenta por persona, tablas y vista previa del abono ya existentes. Cambiar «Deuda actual» por una descripción de las cuentas que incluye solo después de validar elegibilidad. |
| Original / Cargo real / Descuento / reparto — Pedidos | Valores del pedido; descuento registrado y participaciones del modelo, que pueden diferir del cargo bancario por beneficios/ajustes. | Operación concreta; total completo si es MSI, no mensualidad salvo captura expresamente configurada. Correcciones de cargo y reparto son operaciones distintas. | Detalle del pedido y editor. Mostrar primero resumen legible, luego ajustes y vínculos. No inferir descuento ni reasignar personas para cuadrar visualmente. |
| Suscripciones previstas / familia prevista | Suma de importes de suscripciones ACTIVE; familia = participaciones no propietarias + recargos. Pendiente de cargos registrados es otra cifra. | Previsión recurrente configurada, no deuda bancaria ni suma de facturas ya cobradas. Pausar/cancelar cambia previsión; cargo real crea/vincula la operación correspondiente. | Resumen y ficha visibles. Agregar acceso a cargos existentes, no duplicar el registro del cargo. |
| Dinero revisado — Revisar efectivo | Suma de marcas manuales; identificado = conteo + propio/otro; diferencia = físico/objetivo − identificado. Barra: identificado / físico si se indicó; si no, / referencias de pedidos, limitada a 100 %. | Conteo y periodo guardados; separado de movimientos financieros. Cambia con casillas/importes, no registra cobros ni pagos. | Resumen, filas, archivos y Conteos guardados existentes. Se conserva el comportamiento corregido. |

Fuentes de cálculo: `persistence/repository.py`, `list_collection_items`, `list_card_summaries`, `dashboard_summary`, `order_benefit_summary`, `people_debt_summary`, `person_receipt_accounts`; `persistence/bank_periods.py`; `gui/home_month_summary.py`, `home_people_month.py`, `people_month_chart.py`, `personal_result.py`, `cash_review.py`.

**Patrón mínimo para consultar una cifra:** conservar el indicador y añadir un acceso discreto «Ver detalle». Abrir un panel de solo consulta con significado, periodo, componentes, ajustes/restas y total; enlazar al registro existente. No hacer clic obligatorio sobre toda la tarjeta ni llenar Inicio de tablas nuevas. La suma debe salir de las mismas fuentes que el indicador; no implementar una segunda fórmula en el diálogo.

## 7. Historiales: qué se conserva y qué puede consultar el usuario

| Historial o conjunto | Encontrar e identificar | Abrir / consultar / editar | Comprender cambios y volver |
| --- | --- | --- | --- |
| Abonos — Cobros | Ver historial; fecha, persona, comercio, importe, referencia, estado. El historial agrupa abonos globales. | Seleccionar consulta y rellena campos; Editar y Anular son acciones aparte. | Describe el registro actual, no toda la secuencia antes/después. H08/H09. Conservar filtros y selección al cerrar edición. |
| Pagos reales — Tarjetas | Panel Pagos reales e historial; fecha, importe, aplicaciones y estado. | Editar/anular o aplicar un pago a cuotas. | No confundir historial de pagos con auditoría de sus correcciones. Verificar que seleccionar otra tarjeta no haga perder una captura pendiente. Esta última verificación es recomendada, no fallo confirmado. |
| Consultas bancarias | Ver historial de consultas; selecciona fotografía y su explicación. | Solo consulta del registro seleccionado; guardar otra comparación crea otra referencia. | Conservar la fotografía, no recalcular su diferencia con saldo de hoy. Tiene acceso explícito y es un patrón útil para otras consultas. |
| Pedidos anulados | Filtro Anulados/Todos; fecha y comercio. | Selección muestra detalle; no es papelera con restauración automática. | Anulación conserva trazabilidad; ofrecer cambios existentes de solo lectura, no «deshacer» genérico. |
| Devoluciones/recompras | Detalle y seguimiento en pedido; enlaces de la operación. | Hay correcciones y acreditación expresas; cerrar una recompra no revierte automáticamente una devolución guardada. | El seguimiento explica estado/destino, no garantiza trazabilidad de todo consumo posterior del Wallet. No prometer esa información. |
| Suscripciones canceladas/cargos | Listado de estados y ficha; cargos son pedidos vinculados. | Cancelada no se edita; eliminación definitiva es operación distinta y retira información según su confirmación. | Falta acceso contextual claro a la secuencia/cargos: H09. No anunciar auditoría universal recuperable tras eliminación. |
| Conteos guardados | Ventana con fecha/hora, mes, contado y físico/objetivo, para tarjeta actual. | Selección consulta; Abrir recupera y advierte cambios pendientes; Exportar JSON no reemplaza conteo actual. | Versiones consultables, no se suman. La app recupera su última versión interna al abrir; un JSON externo se carga por Abrir corte. Ya corregido; sin rediseño propuesto. |
| Eventos de auditoría | Persistencia conserva eventos; no se encontró navegador general accesible desde navegación. | No hay restauración genérica legítima a partir de cualquier evento. | Proponer Ver cambios por objeto solo cuando exista información suficiente. Separarlo del historial de movimientos. |
| Movimientos recientes | Inicio muestra cinco y permite ver los recientes disponibles; consulta de origen en secciones/buscador. | Lista resumida, no un historial completo de todos los tiempos. La consulta SQL obtiene como máximo diez. | «Ver todos los recientes» no debe presentarse como auditoría completa. Recomendación: «Ver los últimos 10» si el límite se conserva. |
| Respaldos | Configuración crea/verifica y restaura archivos seleccionados. | Restaurar reemplaza base activa tras confirmar; no es consultar un movimiento. | Resultados muestran ruta y copia anterior. No se comprobó una lista persistente de últimos respaldos en la interfaz; sería comodidad futura, no ausencia del respaldo. |

## 8. Recomendaciones adicionales y límites de la revisión visual

- **Medio, recomendación:** en Tarjetas, antes de seleccionar cuenta mostrar «Selecciona una tarjeta para ver sus importes» junto a los guiones, en lugar de exigir deducirlo por el título. Afecta `_select_card`/indicadores de `gui/app.py`; riesgo bajo; comprobar estado vacío y selección por teclado.
- **Medio, recomendación:** mantener captura básica breve y mostrar fechas MSI, alcance de comparación y operaciones extraordinarias al necesitarlas. Ya hay paneles plegables y campos condicionales: mejorar su orden, no introducir un asistente nuevo por sistema. Verificar captura/importación compartida con `test_ux_block3.py`.
- **Bajo, recomendación:** desactivar o explicar acciones no aplicables junto al registro seleccionado. Un botón gris sin motivo no siempre explica si falta selección, permiso o un estado válido. No se confirmó una acción inaccesible por este motivo en las pruebas ejecutadas.
- **Pendiente:** el texto técnico de errores depende de su origen. `gui/errors.py` traduce errores de base de datos, pero otros `ValueError` se muestran directamente; el enlace MSI pasa errores de fecha por ese camino. Revisar con entrada inválida en cada diálogo antes de afirmar exposición concreta de un mensaje en inglés. No sustituir validaciones de negocio por mensajes genéricos.
- **Sin defecto visual confirmado de superposición:** las capturas inspeccionadas muestran desplazamiento y controles parcialmente fuera de tablas, no controles montados unos sobre otros. No afirmar que todas las escalas y pantallas están libres de problemas: faltan repetición de tamaños grandes, estado de historial extenso y combinación de nombres/importes extremos en cada diálogo.
- **Revisar efectivo:** se vio truncamiento de nombres dentro del árbol, con espacio limitado por columna. No impidió guardar/abrir ni se investigó un fallo funcional adicional; no justifica reabrir su implementación en esta etapa.

## 9. Riesgos y pruebas necesarias para una implementación futura

| Bloque | Riesgo principal | Verificación mínima antes de entregar |
| --- | --- | --- |
| Textos y acciones | Cambiar la promesa de una operación sin cambiar su efecto, o viceversa | Mapear señal → manejador → escritura/destino; éxito después de persistir; cancelación sin cambios nuevos. |
| Cifras/desgloses | Doble conteo, mezcla de acumulado/mes o cambio inadvertido de fórmula | Mismos importes antes/después; normales+MSI+pagos sin asignar+reembolsos+cuotas sin fecha; líneas compartidas una vez. |
| Historiales | Presentar un evento como versión restaurable; duplicar ingresos al editar | Consulta sin escrituras, mismo ID al editar, importes globales contados una vez, anulación auditada. |
| Suscripciones | Ocultar que un cambio puede afectar recargos previos o borrar vinculados | Previsualización, token/revisión concurrente, deuda familiar, cargos y pagos sin cambios no autorizados; cancelación local explícita. |
| Navegación/formularios | Perder borrador, selección o foco | Volver a registro y filtros previos; Esc/X coherentes; teclado y scroll; nombres largos. |
| Privacidad | Mostrar resultado/descuentos ocultos al abrir un desglose | Mantener controles y pruebas de `test_ux_privacy_comparison.py`; abrir/cerrar/refrescar sin revelar importes protegidos. |
| Archivos y respaldos | Confundir exportación con respaldo o reemplazar datos al consultar | Ruta visible, extensión correcta, cancelación y error; restauración solo por acción/confirmación ya previstas y exclusivamente en bases sintéticas. |

Suite de referencia adicional para las etapas autorizadas: `test_home_month_total.py`, `test_monthly_card_forecast.py`, `test_bank_period_experience.py`, `test_subscription_fee_reduction.py`, `test_subscription_delete.py`, `test_global_receipts.py`, `test_cash_review.py`, `test_cash_review_msi.py`, `test_global_search.py`, `test_family_pdf_export.py`. No se ejecutó toda esa suite durante este diagnóstico; no se declara aprobada por inferencia.

## 10. Plan en etapas pequeñas, sin implementación en esta entrega

1. **Mensajes de alcance y resultados:** H01, H02 y H05; ajustar texto de cancelación, alcance de recargos y ubicación de guardado. Sin fórmulas ni estado financiero nuevo. Entregar comparación de textos y pruebas de éxito/error/cancelación.
2. **Periodo y significado de cifras:** H03/H04; identificar acumulados frente a mes y explicar los dos indicadores mensuales dentro de desgloses existentes. Entregar ejemplos sintéticos con resultados intactos y revisión de privacidad.
3. **Consulta y navegación:** H06/H07/H08; ubicar resultados de búsqueda, ocultar IDs principales y distinguir consulta/edición. Entregar recorrido completo sin escrituras de consulta ni pérdida de captura.
4. **Historial contextual existente:** H09; comenzar por un solo objeto con auditoría suficiente, después cargos vinculados de suscripciones. No implementar restauración de auditoría ni un panel general complejo.
5. **Distribución y vocabulario:** H10/H11/H12; asegurar acceso a reparto, acercar resumen seleccionado y aplicar etiquetas aprobadas. Repetir ventanas pequeñas y escalas; resolver primero los límites de entorno de las dos pruebas fallidas.

Cada etapa debe poder revisarse y revertirse por separado. Revisar efectivo queda fuera de estos cambios salvo defecto nuevo demostrado. No instalar herramientas ni reconstruir datos históricos para conseguir una presentación más simple.

## 11. Las cinco mejoras de mayor impacto

1. **Aclarar el alcance de Suscripciones (H01/H02).** Primero porque una frase puede hacer creer que se canceló un servicio externo o que solo se modificó el futuro cuando se pueden reducir recargos pasados. Son correcciones pequeñas de comunicación con efecto importante en la decisión del usuario.
2. **Identificar periodos y explicar por qué Inicio y Tarjetas difieren (H03/H04).** Evita interpretar dos cantidades legítimas como un error, y distinguir cuánto está pendiente de cuánto está programado sin tocar fórmulas aprobadas.
3. **Confirmar qué se guardó y dónde consultarlo (H05).** Atiende directamente el problema que originó esta auditoría. Aprovecha registros, rutas y selecciones existentes; no exige otra función financiera.
4. **Separar consultar de editar y hacer que Abrir encuentre el registro (H06/H08).** Reduce búsquedas repetidas y dudas al revisar dinero ya registrado. La consulta debe ser comprobablemente de solo lectura.
5. **Hacer accesibles los cambios y cargos ya conservados (H09).** Permite comprobar una corrección anterior sin confundir auditoría con restauración. Debe empezar por un historial contextual acotado, no por una pantalla nueva que concentre toda la aplicación.

**Cierre de etapa:** únicamente investigación, documentación y evidencias sintéticas. Se espera autorización del usuario antes de implementar cualquiera de las propuestas.
