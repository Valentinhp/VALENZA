# Resultado personal previsto visible

Inicio muestra Descuentos personales y Resultado personal previsto sin abrir
«Detalles financieros». El único botón «Ver cómo se calcula» está junto al
resultado y abre el desglose existente por operación, con costo efectivo,
participaciones familiares vigentes, resultado «a favor» o «a tu cargo» y totales.
El PDF del propietario incorpora una sección adicional con esos mismos datos.
Los conceptos, asignaciones, abonos y pendiente registrado se conservan.

La previsión supone cobrar todas las participaciones familiares antes de abonos
personales. No es dinero ya recibido, disponible ni exigible hoy. Los descuentos
ya incluidos en el costo efectivo no se vuelven a restar. El resultado permanece
separado del pendiente registrado, abonos, cobros familiares y deuda bancaria.

## Cálculo y alcance

Se reutilizan `dashboard_summary`, `expected_result_breakdown` y su cálculo
existente `order_benefit_summary`. `gui/personal_result.py` comparte la consulta
y las expresiones de presentación entre el desglose y el PDF, sin nuevas
fórmulas contables. Inicio conserva el mismo total de `dashboard_summary`.
El estado de cuenta transmite `person.is_owner`; no se compara ningún nombre.
No hay cambios de esquema, migraciones, escrituras financieras ni búsqueda global.

## Validación

**30 pruebas distintas aprobadas; cero fallos u omisiones.** La ejecución principal
aprobó 25 casos, otras cuatro pruebas cubrieron la comparación contable existente
y una comprobó varias operaciones a 680 × 600. Se repitieron los ocho casos de
presentación tras ajustar la fuente de las capturas y fijar las huellas del PDF
familiar previo. Todas las bases utilizadas fueron sintéticas y cifradas con
SQLCipher; no se abrió una base personal.

- Descuento, devolución a tarjeta, Wallet y otro saldo, recompra vinculada,
  MSI, abonos personales y familiares; resultados positivos y negativos.
- Coincidencia exacta en centavos entre Inicio, suma del desglose y PDF del
  propietario. Costo efectivo comprobado sin restar descuentos otra vez.
- Recompras agrupadas con la operación raíz y MSI sin duplicaciones.
- PDF familiar idéntico al generador previo en texto, posiciones, estilos y
  píxeles, comprobado con huellas de un caso sintético fijo.
- Comparación de todas las tablas antes y después de consultar Inicio,
  expandir, refrescar y exportar; ninguna modificación financiera.
- Revisión visual de Inicio, desglose y PDF; ventana compacta y tamaños
  representativos de las pruebas existentes. Fuente Segoe UI explícita para
  evitar glifos ausentes del entorno Qt de capturas.

Los escenarios Wallet comprueban la consistencia de la presentación con el modelo
actual; no constituyen una auditoría global de su comportamiento. No se detectó
un problema contable en los casos probados y no se amplió el alcance.

## Evidencias

En `artifacts/personal-result/` se conservan `inicio.png`, `desglose.png`,
`inicio-compacto.png`, `desglose-compacto.png`, `pdf-propietario.png` y el PDF
sintético `propietario-sintetico.pdf`. Los informes JUnit son `results.xml`,
`presentation-results.xml`, `accounting-results.xml` y `compact-results.xml`.

```powershell
$env:QT_QPA_PLATFORM='offscreen'
.venv/Scripts/python.exe -m pytest tests/test_personal_result_presentation.py tests/test_family_pdf_design.py tests/test_family_pdf_export.py tests/test_home_structure.py tests/test_home_polish.py -q -p no:cacheprovider --basetemp=tmp/personal-result-validation
.venv/Scripts/python.exe -m pytest tests/test_personal_balance.py tests/test_product_refunds.py -k 'discount_comparison or pending_refund_is_not_cash or topup_in_another_bank or dynamic_and_personal_receipts' -q -p no:cacheprovider --basetemp=tmp/personal-result-accounting
```

## Archivos modificados

- `src/valenza/gui/app.py`: ubicación visible, botón, lenguaje del desglose.
- `src/valenza/gui/personal_result.py`: consulta y textos compartidos.
- `src/valenza/gui/family_pdf.py`: sección exclusiva del propietario.
- `src/valenza/persistence/repository.py`: exposición de `is_owner` en la consulta
  del estado de cuenta; cálculos y escrituras sin cambios.
- `tests/test_personal_result_presentation.py`: coincidencias, cifrado,
  inmutabilidad, PDF familiar previo, signos y ventana compacta.
- `tests/test_family_pdf_design.py`, `tests/test_family_pdf_export.py`: expectativas
  diferenciadas del propietario y familiares.
- `tests/test_product_refunds.py`: fixture sintética temporal cifrada.
- `tools/preview_family_reports.py`: muestras con base sintética cifrada.
- `docs/INICIO_DESGLOSE_PERSONAS.md` y este documento: alcance y entrega.
