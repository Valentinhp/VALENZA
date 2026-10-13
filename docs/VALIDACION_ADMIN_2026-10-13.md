# Administración Warm Finance — 2026-10-13

Suscripciones, Usuarios y Configuración reutilizan el tema y las tarjetas de
`warm_finance.py`. Los cambios de producción están limitados a `gui/app.py`.
No se modificaron repositorio, fórmulas financieras, esquema ni migraciones.

## Presentación

- Suscripciones: encabezado y acción principal; resumen de suscripciones activas,
  gasto mensual previsto, fecha del siguiente cargo previsto y participación
  familiar prevista, incluidos los recargos. Estos valores no se suman a deuda.
- La tabla muestra estado y reparto; la ficha conserva por separado el pendiente
  familiar de cargos ya registrados. Editar, pausar/reactivar, cancelar y registrar
  o vincular se habilitan según selección y estado.
- Alta y edición agrupan servicio/calendario y reparto. Los responsables inactivos
  existentes se muestran sin descartar sus importes; la validación existente exige
  reactivarlos antes de guardar. El pie del diálogo permanece accesible al desplazar.
- Usuarios: resumen activo/inactivo, tipo propietario/familiar, editor y acciones
  compactas. Cambiar la marca de propietario requiere confirmación. Desactivar
  explica conservación de identificadores, historial y deudas, sin reasignaciones.
- Configuración: propietario actual y selector de personas activas, respaldos
  diferenciados, diagnóstico con resultados plegables que se abren al recibir texto.
- Se conservan barra lateral, marca Valenza y operaciones existentes de respaldo,
  restauración, diagnóstico, cargos reales y vinculación.

## Verificación visual

`tools/preview_admin.py` abre solamente una base temporal SQLCipher con datos y
clave sintéticos; comprueba `database.encrypted` y elimina el archivo al terminar.
Se revisaron capturas Qt offscreen con Segoe UI y factores de escala `1`, `1.25`
y `1.5`. No se cambió la configuración de escala del escritorio de Windows.

Las capturas están en `artifacts/admin-preview/{1,1.25,1.5}/` (archivos locales
excluidos de Git). Cada escala contiene los tres módulos a 1080×760 y 680×480
píxeles lógicos, estado vacío de Suscripciones y diálogos de alta, edición y cargo.
En ventanas pequeñas, los módulos ofrecen desplazamiento vertical y la tabla
ofrece desplazamiento horizontal para conservar todas las columnas.

Ejemplo de reproducción:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:QT_SCALE_FACTOR = '1.25'
.\.venv\Scripts\python.exe tools/preview_admin.py
```

## Pruebas

Suite completa: **471 casos únicos en 43 módulos**, con **469 aprobados,
1 omitido y 1 fallo esperado**. Cero fallos inesperados y cero errores.
La omisión corresponde al comprobante privado no suministrado; el fallo
esperado estricto corresponde a la aplicación heredada de un pago cancelado,
ya descrita en `ESTADO_ACTUAL.md`.

- Bloque de Usuarios, Suscripciones, interfaz general y nueva prueba de
  administración: **38 aprobadas**.
- Después de los ajustes de disposición, administración y Suscripciones:
  **14 aprobadas**.
- Previsualización de devoluciones, comprobada de manera aislada:
  **28 aprobadas**.
- La prueba nueva utiliza una base temporal cifrada y verifica el estado vacío,
  la exclusión de previsiones pausadas, la habilitación de acciones, la selección
  explícita de propietario, resultados del diagnóstico, errores de formulario,
  confirmaciones rechazadas y conservación de responsables inactivos. Crear o
  editar una previsión no genera pedidos ni cuentas por cobrar.
- `git diff --check`: correcto.

La suite histórica también incluye casos sintéticos SQLite en memoria para
validar reglas y restricciones de seguridad. No se abrió ninguna base personal.
Las ejecuciones generales en un único proceso se descartaron: la primera
incluía una aserción de prueba ya corregida y la segunda sufría la lentitud
acumulada de GUI descrita en `VALIDACION_2026-10-12.md`. Los resultados finales
se obtienen ejecutando cada módulo en un proceso independiente. Los informes
JUnit locales de cada módulo están en `.admin-validation/`, excluidos de Git.
