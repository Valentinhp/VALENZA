# Limpieza visual de Valenza — 15 de octubre de 2026

## Inventario inicial

- Inicio: referencias a la restauración de la fórmula en la interfaz, explicaciones extensas junto al importe principal y fechas ISO.
- Tarjetas: columnas secundarias que obligaban a desplazar la tabla, desglose largo siempre abierto y conceptos de deuda y pago con etiquetas poco uniformes.
- Comparación bancaria: explicación completa del cálculo junto al formulario, advertencias repetidas e identificadores internos en el desglose.
- Cobros y Personas: textos secundarios con exceso de énfasis; estados y fechas con convenciones distintas.
- Suscripciones, Configuración y desbloqueo: instrucciones que podían abreviarse sin perder las advertencias necesarias.
- Errores de almacenamiento: algunos diálogos podían mostrar mensajes internos de la base.

## Cambios realizados

- **Inicio:** nota breve con el periodo y la advertencia de que el indicador no sustituye el pago del banco. El cálculo detallado permanece en «Ver desglose». Se quitaron referencias a la «fórmula original» de los textos para el usuario.
- **Tarjetas:** tabla principal con tarjeta, institución, cargado, pagado al banco y deuda total pendiente. Las demás columnas siguen en «Ver todas las columnas». El detalle de compras y mensualidades se despliega con teclado o ratón.
- **Comparación bancaria:** deuda total primero, programación del periodo después. Advertencias visibles sobre fechas, aplicaciones incompletas y calendario sin confirmar. Explicación completa en el desglose; consultas antiguas separadas en el historial. Se retiraron los identificadores internos del texto visible.
- **Pedidos, Cobros y Personas:** fechas legibles, estados «Anulado» consistentes y etiqueta «Pendiente» para el importe que representa una deuda por cobrar. Menos texto repetido en la cuenta por persona.
- **Suscripciones y Configuración:** instrucciones más breves; se conserva la distinción entre previsiones y cargos reales, y las advertencias de restauración de respaldos.
- **Desbloqueo y errores:** mensajes más cortos y accionables. Los errores de almacenamiento conservan tipo y ubicación de la llamada en el registro técnico, sin SQL, parámetros ni datos financieros.
- Las fechas de las tablas se formatean únicamente al dibujarlas: sus valores originales se conservan para ordenar, seleccionar y registrar operaciones. No hay conversiones de zona horaria.
- Se reutilizaron los componentes y colores Warm Finance existentes.

## Protección de la contabilidad

Se compararon hashes de los 11 archivos de persistencia, finanzas y generación de PDF protegidos al iniciar este trabajo: sin cambios. También se comparó la estructura de la función `home_month_summary()`: idéntica.

Las pruebas mantienen el ejemplo de Inicio en **$2,500**, deuda total en **$13,500** y MSI futuros en **$11,000**, sin duplicaciones. Se preserva el tratamiento original de pagos asignados y sin asignar, el mínimo cero por instrumento y la gráfica futura de MSI pendientes.

No se abrió la base personal. No se modificaron esquemas, movimientos, fechas guardadas, participaciones, conciliaciones históricas ni PDFs financieros.

## Validación

**46 pruebas distintas aprobadas**, usando bases sintéticas cifradas en las pruebas con persistencia:

- `test_home_initial_restore.py`: 9.
- `test_ux_privacy_comparison.py`: 2.
- `test_home_structure.py`: 4 resoluciones, incluida la configuración estrecha.
- `test_due_month_final.py`: 13.
- `test_monthly_card_forecast.py`: 6.
- `test_visual_cleanup.py`: 3; navegación por las siete pantallas, base e historial sin escrituras, teclado, fechas y errores sin información interna.
- `test_tarjetas_visual.py::test_cards_layout_readonly`: 3, con 0, 1 y 10 tarjetas.
- `test_home_polish.py::test_representative_home_polish`: 4 resoluciones.
- `test_global_receipts.py::test_visual_manual_preview_and_history`: 1.
- `test_personal_balance.py::test_compact_home_bank_query_and_manual_form`: 1.

Además: inspección de capturas de las siete pantallas principales y `git diff --check` sin errores de formato. Capturas sintéticas en `artifacts/visual-cleanup/`.

Se ajustaron expectativas de texto en pruebas existentes sin cambiar sus importes esperados. La prueba antigua de Tarjetas ahora comprueba el saldo bancario guardado en el historial, donde corresponde; no lo confunde con una comparación actual. La lectura del código original desde Git usa una ruta explícita y una excepción de propiedad limitada al propio proceso de prueba.

## Límites y pendientes

No quedan fallos abiertos en las pruebas de este bloque. Esta revisión no equivale a probar exhaustivamente cada diálogo excepcional ni todos los documentos que pueden importarse. No se realizó una comprobación con datos personales ni una certificación integral de estabilidad de toda la aplicación. No se iniciaron otras mejoras pendientes.

## Gráfica mensual por persona: presentación interactiva

La gráfica mensual y su lista se integraron en una tarjeta adaptable. La parte del propietario tiene un color cálido y una fila destacada; las proporciones siguen representando los importes reales. Seleccionar una fila o porción actualiza el centro de la gráfica. El cursor permite explorar temporalmente otra persona y las teclas Arriba/Abajo y Espacio permiten seleccionarla.

Las flechas del mes se sincronizan con el selector existente de Inicio. «Ver cuenta» abre el desglose existente de la persona seleccionada. La tabla de deuda total conserva sus importes; las columnas de previsiones están disponibles al abrir su desglose.

El criterio mensual permanece igual al de la versión anterior: compras normales por fecha registrada y cuotas MSI del periodo después de abonos. No se modificaron servicios financieros ni la fórmula restaurada de Inicio.

Validación de esta actualización: **32 pruebas aprobadas** — 7 de gráfica e interacción, 9 de restauración original, 4 de estructura, 7 de presentación de Inicio, 2 de privacidad/comparación y 3 de limpieza visual. Incluyen ocho personas, nombres largos, importes grandes, vistas de 300/460/820 píxeles, meses vacíos, diciembre/enero, pagos parciales e historial sin escrituras. Las pruebas con persistencia usan exclusivamente bases sintéticas cifradas.

Capturas de la tarjeta en `artifacts/people-chart/`; `integrated-chart.png` muestra su presentación dentro de Inicio con datos sintéticos.
