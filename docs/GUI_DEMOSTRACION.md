# Primera interfaz gráfica de SGCCC

## Estado

La interfaz PySide6 es una aplicación local de demostración para Windows 10
x64. La sección **Usuarios** sí es operativa: abre una base SQLCipher,
permite crear, consultar, editar y desactivar personas ficticias, y conserva
los cambios después de cerrar y volver a abrir. También permite reactivar una
persona desactivada con el mismo identificador y una auditoría adicional.

## Pantallas

La navegación lateral funciona para:

- Inicio.
- Usuarios.
- Pedidos.
- Cobros (abonos manuales por pedido, sin vencimientos).
- Suscripciones (deshabilitada).
- Configuración.

El panel de inicio muestra datos sintéticos claramente marcados:

- saldo de cuentas por cobrar;
- saldo institucional;
- movimientos recientes de demostración.

Los saldos se muestran en secciones separadas. No representan operaciones
reales ni se derivan del OCR.

## Usuarios operativos

Al abrir el programa se solicita la contraseña de la base cifrada. La
contraseña solo se usa en memoria para abrir SQLCipher y no se guarda en el
código, registros ni configuración.

Si la contraseña no permite abrir la base, se muestra un diálogo genérico que
no distingue automáticamente entre contraseña incorrecta y base dañada. El
diálogo permite reintentar o cancelar. Cancelar deja intacto el archivo
existente; no se elimina, reemplaza ni recrea ninguna base.

En Usuarios se puede:

- crear una persona ficticia;
- consultar la tabla actualizada;
- editar nombre y condición de propietario;
- desactivar la persona conservando el registro;
- reactivar la persona conservando identificador, historial y auditoría;
- rechazar nombres duplicados sin distinguir mayúsculas ni espacios
  exteriores;
- conservar una auditoría de creación, edición y desactivación.

La base se guarda en:

```text
%LOCALAPPDATA%\SGCCC\sgccc.db
```

Suscripciones e Instituciones continúan deshabilitadas y lo indican
claramente en pantalla. Cobros permite seleccionar una persona y un pedido,
registrar abonos parciales sin distribuirlos automáticamente, consultar
saldo/estado e historial, y registrar extras y comisiones separadamente. No
exige fechas de vencimiento ni recordatorios.

La pantalla de Cobros muestra todas las cuentas por persona y pedido, incluidos
los pedidos pagados. Al seleccionar una cuenta pendiente propone su saldo como
abono editable. La referencia está dentro de "Más detalles"; los extras y
comisiones están en "Otras operaciones". El historial muestra los últimos
movimientos y puede expandirse sin modificar cobros anteriores.

## Pedidos operativos

El flujo principal ahora es **Pedidos** y no exige capturar productos. Se
registran comercio, fecha, institución, instrumento, importe original y costo
cargado a la tarjeta. El descuento se calcula automáticamente como la
diferencia positiva entre ambos importes; si el cargo supera al original se
muestra una excepción de conciliación, sin inventar un descuento negativo. La
tabla de reparto muestra desde el inicio a todas las personas activas,
incluida la propietaria ("Yo"), con importe inicial de $0.00 MXN.

El sistema muestra total distribuido, diferencia pendiente, parte personal y
y cuentas por cobrar. No permite guardar si el reparto no coincide con el
`importe original`. El descuento pertenece al propietario y solo reduce el
costo cargado a la tarjeta; ambos importes se conservan separados. Las celdas
de importe se editan directamente, sin botones para agregar asignaciones.
La aplicación conserva el ID de cada persona en la fila y valida el campo
persistente `is_owner` antes de calcular o guardar. Si la persona visible como
"Yo" no coincide con el propietario persistente, muestra la inconsistencia
con IDs y bloquea el guardado; no crea ni renombra personas automáticamente.

## Reparación explícita del propietario

En **Configuración** se muestran todas las personas, su ID, estado activo e
`is_owner`. El botón **Configurar propietario** requiere seleccionar una
persona activa y confirmar la operación. La operación es transaccional,
conserva IDs, pedidos, compras, cuentas por cobrar, pagos y movimientos, y
registra auditoría. Desmarca propietarios anteriores y deja exactamente un
propietario activo. Las referencias históricas se informan y no se
reclasifican silenciosamente.

1. Seleccionar la institución e instrumento.
2. Capturar comercio, fecha, importe original y cargo real.
3. Escribir los importes directamente en la fila de cada persona.
4. Revisar el resumen actualizado y guardar el pedido.
5. Seleccionar una fila de pedidos registrados para ver sus participantes.

Los pedidos se persisten en `order_record` y `order_allocation`. Las deudas
de terceros se guardan como cuentas por cobrar de origen `ORDER`, sin duplicar
las compras anteriores.

## Compras históricas (compatibilidad)

El flujo anterior basado en productos, asignaciones y cantidades se conserva
para compatibilidad de datos, repositorios, auditoría y pruebas, pero su
formulario está oculto y ya no aparece en el menú principal. No es necesario
para crear un pedido monetario ni se mezcla con la pantalla de Pedidos.

El desglose opcional de productos para pedidos, OCR, revisión documental y
exportación Word todavía no están implementados.

## Ejecución

Desde la raíz del proyecto:

```powershell
& ".\.venv\Scripts\python.exe" -m pip install -e ".[gui]"
& ".\.venv\Scripts\python.exe" -m sgccc.gui.app
```

Las pruebas de arranque y navegación usan `QT_QPA_PLATFORM=offscreen` para no
requerir una pantalla:

```powershell
$env:QT_QPA_PLATFORM="offscreen"
& ".\.venv\Scripts\python.exe" -m pytest tests\test_gui.py
```

## Límites intencionales

- Solo se permiten datos ficticios de demostración.
- No hay conexión entre OCR y contabilidad.
- Usuarios, Pedidos y Compras simples usan SQLCipher; las demás secciones no tienen
  operaciones.
- No hay autenticación ni control de acceso todavía.
- Compras complejas (intereses, mensualidades, descuentos, devoluciones y
  promociones) y seguridad de acceso siguen pendientes.
