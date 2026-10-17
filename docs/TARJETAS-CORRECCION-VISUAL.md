# Tarjetas: corrección visual y verificación

Revisión del 16 de octubre de 2026. Cambios limitados a presentación.

## Problemas y causas

- Se fijaban alturas de etiquetas, del formulario y de sus paneles a partir de medidas tomadas durante un cambio de ancho. Las restricciones quedaban desfasadas al desplegar opciones o cambiar el texto.
- Las cuadrículas de conciliación y de vinculación no reorganizaban sus parejas de etiqueta y campo de forma suficiente en ventanas pequeñas.
- Qt subestimaba el espacio vertical de explicaciones extensas, especialmente texto enriquecido dentro del área desplazable.
- Los botones de despliegue ocupaban todo el ancho aunque su acción fuera breve.
- El historial mostraba identificadores internos y dimensionaba las columnas según las descripciones más largas, ocultando las tarjetas tras desplazamiento horizontal incluso en ventanas amplias.
- Un ajuste general de selectores ejecutado al final de construir la ventana anulaba el tamaño mínimo específico del formulario bancario. Se detectó al contrastar la captura nativa con las pruebas fuera de pantalla.

## Correcciones

`src/valenza/gui/app.py`:

- `_make_cards_page`: formularios bancarios con `QFormLayout`, etiquetas breves, campos y botones en filas independientes; botones desplegables alineados a la izquierda y de tamaño natural.
- `_cards_compact_form`: filas que permiten colocar la etiqueta encima del campo cuando no caben juntos, con márgenes y espaciados consistentes.
- `_fit_card_tables`: retirada la cadena de cálculos y alturas fijas del panel bancario. Se conserva la adaptación de indicadores y tablas existente.
- `_build_ui`: conserva el tamaño mínimo específico de los dos selectores de conciliación.
- `_select_card`: alias legibles en el historial; el ID permanece en `UserRole` y en la ayuda de la celda. Conceptos y diferencias más compactos en la tabla, con explicación completa en el detalle. Las columnas comparten el ancho disponible.
- `_add_advanced_section`: botones de despliegue compactos.

`src/valenza/gui/cards_layout.py`:

- `CardExplanation` comunica a los layouts el mínimo necesario para el texto a su ancho actual, también cuando contiene HTML. No fija alturas de paneles ni añade áreas desplazables.

No se modificaron fórmulas, operaciones, reglas de conciliación, tablas ni migraciones. Los 16 archivos protegidos de finanzas, persistencia y cálculos auxiliares coinciden con sus hashes previos.

## Verificación visual reproducible

`tools/review_cards_layout.py` abre la ventana real con el motor Qt `windows`, crea bases cifradas sintéticas dentro del directorio de auditoría y rechaza cualquier apertura de base fuera de él. No llama al lanzador normal ni a `app.main`.

Comprueba ventana pequeña de 680 × 600, normal y maximizada; las medidas efectivas se registran en `artifacts/tarjetas-interfaz/revision.json`. Windows puede ajustar la altura normal al espacio de trabajo. Las imágenes respetan la escala de pantalla.

Estados: los tres conceptos principales de conciliación, opciones avanzadas, misma línea, desglose, historial con selección y detalle, pagos, MSI, administración desplegada, ausencia de selección, historial vacío, base sin tarjetas y diálogo real de fechas obligatorias. Comprueba geometría de contenedores anidados, ancho útil del selector, ausencia de desplazamiento horizontal en la página, integridad y cero escrituras durante la revisión.

Las capturas proceden de `QWidget.grab()` de esa ventana nativa. La herramienta externa de captura de Windows devolvió errores de espera/geometría; las imágenes no se presentan como capturas del escritorio obtenidas con ella. Se revisan visualmente los PNG, además de las aserciones automatizadas.

En ventanas pequeñas las tablas de varias columnas conservan desplazamiento horizontal interno cuando es necesario; la página y sus formularios no lo requieren. Los textos completos de celdas abreviadas permanecen disponibles en su ayuda y detalle. El contenido fuera del borde superior o inferior del área desplazable es contenido desplazado, no una etiqueta comprimida por el layout.

Galería: [capturas](../artifacts/tarjetas-interfaz/index.html). Metadatos: [revisión nativa](../artifacts/tarjetas-interfaz/revision.json).

## Pruebas

- `tests/test_cards_refund_ui.py`: despliegues individuales y simultáneos, contención y ausencia de intersecciones de controles internos, altura del texto, selector legible, historial con alias e ID técnico, validación y cero cambios financieros.
- Regresión relacionada: conciliación manual, periodos, privacidad, Tarjetas y ciclo de vida Qt en procesos aislados, tanto `offscreen` como `windows`.
- Regresión relacionada: 63 aprobadas, 0 fallas. Verificación posterior del último ajuste de interfaz y ciclo de vida: 26 aprobadas, 0 fallas. Selector y geometría: 3 aprobadas, 0 fallas. Son ejecuciones con casos superpuestos; no se suman como pruebas distintas.
- Revisión nativa: 46 capturas, cero escrituras y saldos sin cambios.
- Regresión completa terminada: 709 casos, con 707 aprobados, un fallo de accesibilidad y una omisión prevista por privacidad. El fallo fue `bank_query_date.accessibleName()` vacío; se restauraron nombres explícitos para fecha de consulta, importe y cuenta compartida.
- Tras corregirlo se repitió íntegramente `test_ux_block3.py`, más geometría y teclado bancario: 16 casos aprobados, cero fallas. Resultado consolidado de los 709 casos: **708 aprobados, 0 fallas pendientes, 1 omitido**. No se volvió a ejecutar la suite completa después del último cambio de metadatos accesibles; la repetición dirigida cubrió ese cambio.
- La omisión corresponde al comprobante personal opcional `VALENZA_RECEIPT_TEST_PDF`; no se proporcionó ni se accedió a comprobantes reales.
- JUnit completo: `private/codex/auditoria-integral-20261016/tarjetas-regresion-final.xml`; repetición correctiva: `tarjetas-accesibilidad-final.xml`. Resumen verificable: [resultados](../artifacts/tarjetas-interfaz/resultados.json).

El fallo de memoria de Python mostrado anteriormente no queda atribuido a una causa específica por estas correcciones de distribución. Las verificaciones de ciclo de vida registran separadamente cualquier fallo nativo reproducible; aprobarlas no demuestra la causa del incidente histórico.
