# Inicio · Ver desglose por persona

El panel de texto «Estado de cuenta» de Inicio se reemplazó por un acordeón
Warm Finance. «Ver desglose» permanece en su ubicación: abre una lista compacta
con nombre y saldo pendiente. Cada persona despliega sus pedidos con fecha,
importe asignado vigente, abonado y pendiente. Los pendientes se ordenan del
más reciente al más antiguo; los liquidados se consultan en un grupo cerrado
independiente. Las personas sin pedidos y las que tienen todo liquidado conservan
su fila y un mensaje breve.

La presentación está aislada en `gui/home_people_breakdown.py`. No usa QTextEdit,
tablas adicionales ni scroll interno: crece dentro del desplazamiento general
de Inicio. Los controles permiten abrir y cerrar con clic o Espacio y conservan
su estado al refrescar. Los importes se acomodan verticalmente si el espacio
disponible resulta estrecho.

El saldo de cabecera procede de `people_debt_summary`; los pedidos reutilizan
`list_collection_items`, las mismas participaciones que respaldan
`family_statement`. Se presentan `sale_cents`, `paid_cents` y `remaining_cents`
sin recalcularlos ni mezclar cargos originales, pagos bancarios o previsiones.
No se suman cuotas MSI otra vez. La participación ajustada por devoluciones y
recompras aparece una sola vez, con su importe vigente.

La tabla superior mantiene sus columnas, formato e importes. Abrir una persona
selecciona su fila para que «Generar PDF» conserve la persona elegida; se reutiliza
la exportación existente sin alterar el contenido del documento. Cobros → Cuenta
por persona y los demás componentes de Inicio mantienen su implementación.
No hay cambios en repositorio financiero, fórmulas, esquema ni migraciones nuevas.

## Validación

Las pruebas y capturas de esta actualización emplean exclusivamente bases
sintéticas temporales cifradas con SQLCipher. Las fixtures de las pruebas de
Inicio ejecutadas se adaptaron para usar archivos cifrados en lugar de SQLite
en memoria. No se abrió una base personal.

- Escenarios: varios pedidos, persona sin pedidos, persona con todo liquidado,
  MSI con abono parcial, descuentos, devolución, recompra y compensación.
- Comparaciones exactas contra `family_statement` y los totales de la tabla;
  exclusión de previsiones, sin duplicar participaciones y sin escrituras al
  consultar, expandir, contraer o refrescar.
- Selección de persona para PDF y pruebas existentes del contenido del PDF.
- Ventanas de 1080×760, 680×480 y 680×600; se conserva el mínimo existente de
  la ventana principal. Navegación con teclado y límites de los importes.
- Capturas a escalas Qt 100 %, 125 % y 150 %, sin modificar la configuración
  de escala del escritorio. Las vistas en tamaño reducido se revisaron visualmente.

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -m pytest tests/test_home_people_breakdown.py tests/test_home_structure.py tests/test_home_polish.py tests/test_people_dashboard.py -p no:cacheprovider --basetemp=.test-home-breakdown-verified
.\.venv\Scripts\python.exe tools/preview_home_people_breakdown.py
$env:QT_SCALE_FACTOR = '1.25'
.\.venv\Scripts\python.exe tools/preview_home_people_breakdown.py
$env:QT_SCALE_FACTOR = '1.5'
.\.venv\Scripts\python.exe tools/preview_home_people_breakdown.py
```

Las capturas se conservan en `artifacts/home-people-breakdown/{1,1.25,1.5}/`:
lista de personas, pendientes, liquidados, estado vacío y persona liquidada,
además del contexto de Inicio. La herramienta reutiliza los casos sintéticos de
las pruebas y comprueba que consultar no cambie datos ni saldos.

Resultado: **18 pruebas aprobadas**, sin fallos ni omisiones. Las cuatro pruebas
del acordeón también pasaron al 150 %. Se generaron **36 capturas** y se revisaron
los pendientes, liquidados, lista de personas y estados sin pedidos a las escalas
indicadas. `git diff --check` y la compilación Python resultaron correctos.
El informe JUnit está en `.home-breakdown-validation/results.xml`.
