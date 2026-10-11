# Estabilización de la aplicación existente

## Qué se reutilizó

Pedidos y sus conceptos/repartos, Cobros y sus aplicaciones de abonos, Tarjetas
y pagos institucionales, devoluciones/recompras auditadas, comparaciones de
descuentos y consultas bancarias. La persistencia mantiene SQLCipher y esquema 14.
No se agrega un módulo ni se habilitan suscripciones o nuevas funciones de MSI.

## Editar tarjetas y billeteras

1. Abre Tarjetas y selecciona la cuenta en la tabla.
2. Despliega **Administrar instituciones y tarjetas**.
3. En **Institución de la cuenta**, elige una institución existente. Modifica
   alias, terminación (solo cuatro dígitos, opcional) y descripción.
4. Pulsa **Guardar cambios**. Se conserva el identificador y se audita la edición;
   no se recrean movimientos, devoluciones, consultas ni pagos.

La naturaleza de una cuenta existente se muestra bloqueada. Una billetera
permanece como billetera. Para agregar otra cuenta, usa **Preparar nueva cuenta**
y luego **Agregar cuenta**. Instituciones se editan con **Guardar nombre**;
se rechazan nombres equivalentes con espacios o diferencias de mayúsculas ASCII.
Las fechas se editan en **Fechas de corte y pago**, para la tarjeta seleccionada
en la tabla superior. Una billetera no admite fechas de crédito.

## Respaldo y restauración

Desde Configuración:

- **Crear respaldo cifrado**: elige una ruta nueva. Se usa la autenticación de la
  sesión, sin guardar la clave en archivos ni solicitarla de nuevo. Se verifica
  reapertura, cifrado, integridad, esquema y contenido.
- **Restaurar respaldo**: selecciona un archivo y confirma. Primero se valida;
  después de confirmar se crea un respaldo cifrado de los datos actuales en
  `backups`, junto a la base. Su ubicación aparece en Configuración.
- **Diagnóstico de integridad**: comprueba almacenamiento, claves foráneas,
  metadatos y posibles participaciones repetidas. Es de solo lectura y no
  corrige saldos ni elimina registros.

La restauración usa la [API transaccional de backup de SQLite](https://www.sqlite.org/c3ref/backup_finish.html)
mediante SQLCipher, conservando el cifrado y la conexión autenticada. No se
generan copias financieras temporales sin cifrar. Cancelar o rechazar un
respaldo inválido no modifica la base activa. Un fallo de copia se informa y
la copia previa verificada permanece disponible si alcanzó a crearse.

La restauración sencilla admite **la misma clave y esquema actual**. Respaldos
con otra clave o versiones antiguas se rechazan: su migración/recuperación
requiere un procedimiento separado, no se fuerza sobre la base activa. Los
datos posteriores al respaldo y capturas sin guardar se descartan únicamente
tras la confirmación. La versión anterior queda en el respaldo de seguridad.

## Reporte PDF por persona

En Cobros, selecciona una participación y pulsa **PDF de la persona seleccionada**.
El documento reúne sus participaciones de todos los pedidos activos, los
conceptos disponibles, ajustes auditados, abonos activos aplicados y pendientes.
Los conceptos históricos no disponibles se indican; no se inventan.

Cada concepto aparece con su asignación registrada; una devolución/recompra
se explica mediante el ajuste hacia la participación vigente, sin sumar
nuevamente el costo del producto. Los abonos anulados siguen en el historial de
Cobros y no se incluyen como dinero abonado activo. El PDF es local, paginado
y no modifica la contabilidad. Contiene información financiera: guárdalo de
forma privada, fuera de los fixtures del proyecto.

## Inicio y usabilidad

**Ver cálculo**, junto al resultado personal previsto, presenta por operación:
participaciones familiares asignadas − costo efectivo. Recompras vinculadas se
incluyen una vez. Los descuentos ya están en el costo efectivo; no se vuelven
a restar de la deuda bancaria. El resultado no depende de abonos personales ni
representa cobros recibidos; excluye intereses y comisiones, como antes.

Cobros mantiene el registro de abono fuera del contenido desplazable y una
altura mínima para su tabla. Historial, fecha/referencia y extras quedan
accesibles en el contenido secundario. Tarjetas ofrece las columnas esenciales
y **Ver todas las columnas**. Importes compactos se presentan en MXN; el modelo
conserva valores completos. Los nombres largos tienen información completa al
seleccionar y herramientas de ayuda.

Nuevo gasto conserva sus controles y lógica. Escape/Cancelar conserva una
captura nueva; al cerrar la aplicación con una captura pendiente se pide
confirmación en una sesión persistente normal. Guardar solo cierra el formulario
cuando termina correctamente. Los guardados reentrantes se bloquean. Los éxitos
cotidianos aparecen en la barra de estado, sin un diálogo extra.

## Validación y límites

Las pruebas nuevas y existentes usan exclusivamente datos sintéticos. Se
comprueban cambios de institución con historial, naturaleza de billeteras,
fechas inválidas, independencia entre abonos y pagos bancarios, consultas,
reportes, restauración/reapertura, descuentos, devoluciones y recompras.
Se revisan renderizados de Qt a tamaños normales y pequeños; esto no sustituye
pruebas con lectores de pantalla, impresión física o todas las escalas DPI.

La regresión comprende 284 pruebas de 18 archivos, ejecutados en procesos
separados para evitar acumulación de ventanas de Qt. Las ventanas principales
se renderizan a 1100 × 680 y 680 × 480; Nuevo gasto a 520 × 320. También se
verifican devolución, recompra y reparto desplegados, con botones fijos, dentro
de un lienzo de 1366 × 768 y diálogos de hasta 480 × 280.

No se abre ni modifica la base personal durante el desarrollo. Tampoco se
modifican Panel Maestro, fórmulas financieras correctas ni datos existentes.
