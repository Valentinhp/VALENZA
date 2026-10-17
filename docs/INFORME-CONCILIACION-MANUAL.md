# Cierre de conciliación manual

16 de octubre de 2026.

## Resultado funcional

En Tarjetas, «Comparar con mi banco» permite registrar observaciones sin movimientos financieros. Se conserva el cálculo bancario existente; la diferencia informativa usa centavos enteros: banco menos Valenza. El estado distingue «Coincide», «El banco muestra más», «Valenza muestra más» y «No comparable».

La interfaz exige confirmar el alcance de una deuda total. Sin esa confirmación, o con una fecha/periodo/agrupación no comparable, no se guarda una diferencia válida. «Pago para no generar intereses» se captura separadamente con corte y límite obligatorios en el formulario. No se estima a partir del calendario, ni se reduce automáticamente con abonos posteriores. Las consultas antiguas no se reescriben.

La documentación pública de Nu no confirma que su «saldo actual» sea deuda total con principal MSI futuro. No se inventó esa equivalencia ni una suma automática de saldos. Las fuentes oficiales, conceptos y pasos de uso están en [CONCILIACION-NU.md](CONCILIACION-NU.md).

## Archivos de este trabajo

| Archivo | Cambio |
|---|---|
| `src/valenza/persistence/bank_reconciliation.py` | Campos de corte y límite, validación, confirmación de alcance, fotografías versión 4 y prevención de duplicados; ninguna escritura contable. |
| `src/valenza/persistence/repository.py` | La fachada `record_bank_balance` transmite esos campos; no cambia el cálculo de deuda. |
| `src/valenza/gui/bank_reconciliation.py` | Estados solicitados, referencia oficial sin diferencia aproximada nueva, fechas en detalle histórico. |
| `src/valenza/gui/app.py` | Formulario, explicación específica de Nu, confirmación, limpieza del importe después de guardar, teclado y altura del panel. Se reutiliza el resumen por tarjeta existente en Inicio. |
| `tests/test_bank_manual_completion.py` | 14 casos nuevos sobre centavos, duplicados, fechas, alcance, restauración, fallo atómico e interfaz. |
| `tests/test_bank_reconciliation.py`, `tests/test_bank_period_experience.py`, `tests/test_due_month_final.py`, `tests/test_personal_balance.py`, `tests/test_tarjetas_visual.py` | Expectativas actualizadas para referencia oficial independiente con fechas, confirmación explícita y limpieza del importe tras guardar. |
| `tests/test_home_header.py` | Tab y Shift+Tab en los tamaños de encabezado existentes. |
| `tests/test_ux_block2.py`, `tests/test_ux_privacy_comparison.py` | Escenarios actualizados con fechas obligatorias, confirmación del alcance y nuevas etiquetas, conservando las comprobaciones de privacidad y de operaciones financieras. |

Los ajustes de encabezado y dona ya estaban realizados antes de esta solicitud: se conservaron y se vuelven a comprobar, sin duplicar controles ni modificar sus fórmulas. No se atribuyen a este trabajo otras modificaciones que ya existían en el directorio.

## Persistencia y aislamiento

No se crearon tablas ni se cambió la versión SQL. El historial reutiliza entradas inmutables y específicas `instrument/BANK_BALANCE_QUERIED` del almacén cifrado. Las versiones anteriores permanecen legibles. La versión 4 es solo la del contenido de cada observación JSON; no implica migración de la base.

Se probaron respaldo cifrado, verificación, restauración con respaldo de seguridad, reapertura y conservación de valores históricos después de pagos posteriores. Un fallo de inserción simulado revierte la operación sin registro parcial. La prevención de duplicados compara concepto, fecha/hora, importe, alcance y fotografía; una fotografía diferente es una observación distinta.

Solo se usaron bases sintéticas cifradas y un clon nuevo del respaldo autorizado. El proceso de pruebas bloqueó aperturas fuera de la carpeta aislada y conexiones de red. La investigación pública se hizo por separado, sin enviar datos de Valenza. No se abrió la base REAL ni la TEST original.

## Saldos de referencia

Se verificaron antes y después de guardar una comparación y una referencia oficial en el clon aislado:

| Indicador | Importe conservado |
|---|---:|
| Deuda bancaria | $7,243.18 |
| Compromisos de octubre | $4,843.24 |
| Dona de octubre | $4,197.22 |
| Familiares pendientes | $4,179.44 |
| Mi parte pendiente | $2,667.72 |

Todas las tablas distintas de `audit_event` conservaron su contenido. La integridad del clon fue correcta. Los hashes de `home_month_summary.py` y `home_people_month.py` coinciden con los del inventario auditado. No se editaron las reglas de pedidos, descuentos, repartos, cobros, MSI, pagos globales ni revisión de efectivo.

Evidencia privada local: `private/codex/auditoria-integral-20261016/conciliacion-saldos.json` y archivos XML de pruebas de esa carpeta.

## Verificación

Las etapas de conciliación sumaron 48 casos aprobados. El formulario se revisó a 680, 900 y 1920 píxeles con datos sintéticos. Se comprobaron navegación por teclado, alturas de campos, ausencia de superposición con el resultado y ausencia de desplazamiento horizontal. El encabezado de Inicio conserva sus pruebas de ventana normal, amplia y maximizada.

Se ejecutaron **692 casos** en la regresión completa (854.765 segundos). Esa ejecución terminó con **687 aprobados, 4 fallidos y 1 omitido**, sin errores de infraestructura.

Los cuatro fallos eran pruebas de interfaz desactualizadas: `test_compact_home_bank_query_and_manual_form`, `test_card_buttons_preserve_operation_types`, `test_comparison_feedback_never_claims_financial_agreement` y `test_live_comparison_dates_types_keyboard_and_immutable_history`. Esperaban guardar sin confirmar el alcance, omitir las fechas del pago oficial, conservar el importe después del guardado o usar las etiquetas anteriores. Se actualizaron sus escenarios y expectativas, conservando las comprobaciones de privacidad, saldos, historial y operaciones bancarias. **Se repitieron juntas: 4 aprobadas, 0 fallidas.** No se cambió producción después de ejecutar la suite completa.

El resultado más reciente por cada caso único es **691 aprobados, 0 fallos pendientes y 1 omitido**. Esto consolida la suite completa y la repetición explícita de esos cuatro casos; no se afirma que la primera ejecución saliera íntegramente verde ni que se repitieran otros 692 casos después de los cambios exclusivos a pruebas. Los XML originales se conservaron y el resumen verificable está en `private/codex/auditoria-integral-20261016/conciliacion-resultados.json`.

La omisión corresponde al comprobante PDF privado opcional, no utilizado conforme a la restricción de datos. No se omitieron los escenarios sintéticos de conciliación, MSI, pagos, respaldos ni restauración.

## Limitaciones

- La aplicación no conoce cargos omitidos, autorizaciones bancarias pendientes ni el momento real en que Nu refleja un pago; requiere que el usuario confirme el mismo alcance.
- Una diferencia es informativa y no demuestra un error del banco. Cero tampoco certifica que todos los movimientos estén capturados.
- No se reconstruye un estado de cuenta histórico ni el pago oficial. La fotografía es de la contabilidad al guardar.
- Las referencias oficiales no vencen ni se actualizan solas: la fecha de consulta permite reconocer cuándo se capturaron.
- El límite de cinco minutos para comparar una consulta con la fotografía actual se conserva de la infraestructura anterior. Consultas sin hora o antiguas se guardan sin confirmar coincidencia.
- Las observaciones antiguas que ya incluían una diferencia orientativa conservan ese dato histórico; las nuevas referencias oficiales no la generan.
- No se añadieron dependencias, conexiones bancarias, instituciones ficticias ni servicios externos. No se generaron ejecutables ni se publicó en GitHub. Se mantiene la tecnología existente compatible con Windows 10; no se ejecutó una sesión aparte en otra instalación de Windows 10.
