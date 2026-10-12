# Validación para preparar GitHub — 2026-10-12

## Resultado

Se verificaron **470 casos únicos** de la suite en Windows, con el entorno
virtual local y `QT_QPA_PLATFORM=offscreen`:

- 468 aprobados.
- 1 omitido: comprobante original privado, no suministrado para esta revisión.
- 1 fallo esperado estricto: aplicación heredada no revertida de un pago cancelado.
- 0 fallos inesperados y 0 errores.

La suite se ejecutó por bloques y módulos en procesos independientes, con bases
sintéticas temporales. Las primeras ejecuciones se interrumpieron por lentitud
acumulada de GUI y por una prueba que esperaba el diálogo de contraseña anterior.
Los resultados finales corresponden a las ejecuciones posteriores completas
de todos los módulos. Los 13 informes JUnit locales quedan en
`.repo-validation-reports/`, excluido de Git.

## Ajustes de pruebas

- `tests/test_gui.py`: descuento sintético de $20 para un pedido de $100 con
  cargo de $80. Se conservan las comprobaciones de deuda bancaria y cobros.
- `tests/test_users.py`: simulación de credenciales mediante `UnlockDialog`,
  en lugar de `QInputDialog`. Se verifican reintento, cancelación sin reemplazar
  el archivo y respaldo cifrado antes de una migración.

Esta preparación no cambia cálculos financieros ni abre la base personal.
El caso financiero marcado como fallo esperado está descrito en
[Estado actual](ESTADO_ACTUAL.md).

## Paquete y documentación

- Wheel `valenza-0.1.0-py3-none-any.whl` construido desde una carpeta de
  compilación limpia. Una compilación anterior contenía archivos de `sgccc`;
  se apartó el directorio generado antes de reconstruir.
- Verificados los cuatro assets de marca y los comandos `valenza` y `valenza-demo`.
- Verificada la ausencia del paquete antiguo dentro del wheel limpio.
- Arranque de una ventana de demostración usando exclusivamente el código
  extraído del wheel: correcto, incluido el icono.
- Enlaces locales de README, historial y documentos comprobados.
- `git diff --check`: sin errores de espacios.

## Selección para Git

Se revisaron los archivos candidatos y las exclusiones. Los únicos binarios
previstos son los cuatro assets de ejecución y cinco fixtures sintéticos
versionados. Se conservan las fuentes SVG de marca. `output/`, `tmp/`, entornos,
compilaciones, bases, respaldos y credenciales quedan fuera de la selección.

El commit y el push se preparan siguiendo
[la guía de GitHub](GITHUB_PREPARACION.md). Esta revisión no realiza una
publicación remota ni verifica la privacidad actual del repositorio.
