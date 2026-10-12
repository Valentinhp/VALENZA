# Persistencia local: esquema propuesto y estado

> Especificación histórica con estados de distintas etapas. Para instalación,
> funciones y límites vigentes, consulta [Estado actual](ESTADO_ACTUAL.md)
> y el [README](../README.md).

## Restricción de seguridad

La especificación exige SQLCipher para datos financieros persistentes. La verificación del entorno actual encontró:

- SQLite estándar 3.49.1 no tiene opción de compilación `CIPHER` y no puede abrir
  archivos SQLCipher.
- La distribución compatible instalada para la verificación es
  `sqlcipher3==0.6.3`, con SQLCipher `4.12.0 community`, para CPython 3.13
  `win_amd64`.
- No se instaló ningún componente del sistema ni se solicitaron privilegios de
  administrador.

Si `sqlcipher3` no está disponible, `LocalDatabase.open()` rechaza toda ruta
persistente. El modo `:memory:` usa deliberadamente SQLite estándar y solo se
permite cuando el llamador activa explícitamente
`allow_synthetic_in_memory=True`. Esa ruta es exclusivamente para pruebas
sintéticas y no debe usarse con datos reales.

## Esquema propuesto

### Migración 1

- `person`
- `institution`
- `payment_instrument`
- `institution_movement`
- `initial_balance`
- `audit_event`

### Migración 2

- `user_payment`
- `receivable`
- `receipt_application`
- `match_suggestion`
- índices para instrumentos, movimientos, usuarios y cuentas por cobrar

### Migración 3

- índice único para nombres de personas normalizados con `lower(trim(name))`.

### Migración 4

- `purchase`;
- `purchase_product`;
- `purchase_allocation`;
- índice único de cuentas por cobrar por `(purchase_id, user_id)`;
- índices de consulta de compras y productos.

La compra, sus productos, asignaciones y cuentas por cobrar se guardan en una
sola transacción. Los importes se almacenan como centavos enteros.

### Migraciones 5 y 6

- `order_record` para pedidos capturados por importe total;
- `order_allocation` para reparto monetario por persona;
- columnas `order_id` y `source_type` en `receivable`;
- índices para pedidos y cuentas por cobrar de origen `ORDER`.

En la migración 6 se reconstruye `order_record` para retirar la restricción
incorrecta que vinculaba `total_to_recover_cents` con
`original_cents - discount_cents`. Los valores ya almacenados se copian sin
alterarlos. Los pedidos nuevos deben distribuir exactamente
`original_cents`; el descuento solo representa el beneficio del propietario y
reduce el cargo efectivo a la tarjeta.

Los pedidos existentes no se recalculan ni se reescriben automáticamente.

Las columnas monetarias son `INTEGER` en centavos. Las claves son `TEXT` opacas. Las claves foráneas están activadas por conexión.

## Restricciones principales

- No hay instrumentos huérfanos.
- No hay movimientos con importes negativos.
- No hay referencias externas repetidas por instrumento.
- No hay aplicaciones repetidas para el mismo cobro/cuenta.
- Una aplicación no puede exceder el cobro recibido.
- Una aplicación no puede exceder la cuenta por cobrar.
- Un cobro y una cuenta por cobrar deben pertenecer al mismo usuario.
- Las sugerencias de conciliación son únicas por par de fuentes.
- Los movimientos institucionales y cobros de usuarios son tablas distintas.
- La auditoría conserva valores anterior/nuevo serializados como JSON.

## Transacciones e idempotencia

Cada operación del repositorio usa una transacción y hace rollback ante error. Las restricciones SQL evitan reintentos duplicados por identificador o referencia externa. La aplicación de cobros valida saldos dentro de la misma transacción.

Las migraciones 1 y 2 tienen operaciones `UP` y `DOWN` para el entorno sintético. La reversión elimina las tablas y los índices de la migración correspondiente. Cada sentencia se ejecuta dentro de la transacción explícita; no se usa `executescript()`, para conservar el rollback ante un error. Las migraciones persistentes solo se ejecutan a través de la conexión SQLCipher.

## Operaciones implementadas

En `FinanceRepository` pueden guardarse y recuperarse en memoria sintética:

- personas;
- instituciones;
- instrumentos;
- movimientos institucionales;
- cobros de usuarios;
- cuentas por cobrar;
- aplicaciones de cobros;
- eventos de auditoría;
- conteos para comprobación de persistencia.

La migración 8 agrega `institution_payment` para registrar pagos explícitos
hechos por el propietario y `instrument_calendar` para conservar el historial
de días de corte y límite de pago. El resumen de Tarjetas suma
`order_record.charged_cents` y no vuelve a sumar movimientos institucionales
de tipo `CHARGE`, evitando duplicar pedidos. Los movimientos de intereses,
comisiones, ajustes, devoluciones y bonificaciones siguen separados.

Los cobros familiares permanecen exclusivamente en `user_payment` y
`receipt_application`; nunca generan un pago institucional automáticamente.

La migración 9 distingue `CASH` y `MSI` en `order_record` y persiste
`financing_plan`, `installment` e `installment_period_assignment`. Los pedidos
existentes se consideran de contado y no se reinterpretan. Las cuotas conservan
importes exactos en centavos y fechas explícitas; el principal MSI es
`charged_cents`, sin crear un cargo institucional duplicado. Si falta un
calendario confirmado, la asignación queda con `requires_review` y no se
presenta como exigible por periodo. Los pagos generales de tarjeta reducen el
saldo total, pero no reducen cuotas futuras automáticamente.

La migración 10 añade el estado lógico auditable de `order_record`
(`ACTIVE`/`CANCELLED`) y `installment_payment_application`. La anulación no
borra pedidos, planes, cuotas ni cobros; se bloquea si existen abonos
familiares aplicados o pagos aplicados a cuotas. Las aplicaciones explícitas
pueden ser parciales y solo una cobertura completa marca la cuota como
pagada. Un pago institucional general conserva siempre su saldo no asignado
hasta que el usuario lo aplique manualmente.

La migración 11 añade estados y metadatos de anulación a cobros familiares,
pagos institucionales y sus aplicaciones. Las anulaciones marcan el registro
como `CANCELLED` o la aplicación como `REVERSED`; los importes activos se
calculan únicamente con aplicaciones `ACTIVE`. Esto permite corregir el
saldo sin eliminar historial ni crear movimientos compensatorios ficticios.

Además, la interfaz de Usuarios usa la misma conexión SQLCipher y el mismo
repositorio para crear, listar, editar y desactivar personas. Cada operación
de persona escribe su evento de auditoría en la misma transacción.

La interfaz de Compras históricas conserva su alcance separado. Pedidos
permite registrar descuentos y ahora también modalidad MSI; la persistencia de
devoluciones y promociones continúa pendiente.

La interfaz de Tarjetas muestra cargos, pagos, saldo por liquidar, fechas,
compras asociadas, importe del periodo y cuotas futuras. Pedidos permite elegir
contado o MSI y capturar el vencimiento de la primera cuota y el número de
cuotas. Las fechas se calculan mes a mes respetando meses cortos y cambios de
año; una cuota sin calendario confirmado queda pendiente de confirmación.

OCR permanece completamente desconectado.

## Validación ejecutada

- Pruebas de persistencia con SQLCipher: 9 pasaron.
- Suite completa con SQLCipher: **49 pasaron** en Python 3.13.5.
- Suite en el Python global sin SQLCipher: **48 pasaron y 1 se omitió**; la
  prueba cifrada se omite y las rutas persistentes siguen rechazadas.
- Verificación SQLCipher: `PRAGMA cipher_version` devolvió `4.12.0 community`.
- Un archivo creado con la clave correcta se reabrió y conservó sus datos.
- La clave incorrecta falló con `file is not a database`.
- SQLite estándar también falló al abrir/consultar el archivo cifrado con
  `file is not a database`.
- Se verificaron claves foráneas, duplicados por referencia externa, rollback de repositorio, rollback y reaplicación de migraciones, separación entre cobros y movimientos institucionales, límites de aplicación y auditoría serializada.
- La prueba automatizada de reapertura cifrada usa una clave efímera generada
  en tiempo de prueba; no se imprime ni se almacena.
- La interfaz captura el fallo de apertura/migración cifrada y muestra un
  mensaje genérico: no asume automáticamente si se trata de contraseña
  incorrecta o corrupción. Permite reintentar o cancelar sin reemplazar el
  archivo.

## Pendientes de seguridad

- Definir KDF, parámetros de cifrado, bloqueo de sesión y recuperación.
- Cifrar adjuntos y respaldos.
- Probar restauración aislada y manipulación/corrupción.
- Añadir persistencia de cuotas MSI, devoluciones, bonificaciones y ajustes.

Hasta cerrar esos puntos no debe almacenarse información financiera real.
