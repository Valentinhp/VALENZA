# Estado actual de Valenza

Referencia del código preparado el 12 de octubre de 2026. El README contiene
los comandos de instalación y ejecución; los documentos de primeras etapas
no sustituyen esta descripción.

## Paquete y datos

El código vive en `src/valenza`. El nombre `sgccc` ya no es un import válido.
La ruta de datos heredada `SGCCC` sigue siendo compatible: el cambio de marca
no requiere mover ni duplicar bases. La aplicación usa SQLCipher para archivos
persistentes; las pruebas usan datos ficticios y directorios desechables.

## Funciones disponibles

- Usuarios, pedidos manuales e importación revisable de PDF.
- Suscripciones con cargos reales registrados o vinculados y previsiones separadas.
- MSI con cuotas, fechas y aplicaciones de pagos; calendario y proyección por mes.
- Cobros por persona, abonos, recibos globales e historial.
- Tarjetas con cargos, pagos bancarios y desglose activo.
- Inicio con indicadores, compromisos del mes, previsiones, desgloses y PDF familiar.
- Devoluciones y recompras vinculadas con evidencia y movimientos separados.

El compromiso de un mes representa sus cuotas y cargos correspondientes; el
saldo total pendiente MSI es otra perspectiva y no debe volver a sumarse.
Los descuentos previstos, los abonos familiares y los pagos al banco son
conceptos diferentes. Consultar o exportar un desglose no registra un pago.

## Límites conocidos

No hay conciliación bancaria automática ni OCR en la nube. Tesseract local es
opcional para escaneos; una previsión no confirma un movimiento bancario.

`tests/test_financial_audit.py` conserva una regresión `xfail(strict=True)`:
una aplicación heredada de un pago cancelado que no haya sido revertida puede
seguir afectando los saldos de cobro. Es un caso conocido documentado por la
auditoría; esta preparación de Git no modifica la lógica para resolverlo.

## Material versionado

Se incluyen fuentes SVG de marca en `logos/`, assets de ejecución en
`src/valenza/gui/assets/`, pruebas y fixtures sintéticos seleccionados.
`output/`, `tmp/`, capturas de revisión, bases, respaldos y credenciales quedan
fuera de Git. No es necesario borrarlos para preparar una subida limpia.

## Documentación

- [Historial de cambios](../CHANGELOG.md).
- [Importación de PDF](IMPORTAR_PDF.md).
- [Uso cotidiano y respaldos](ESTABILIZACION.md), con contexto de una etapa anterior.
- [Preparación para GitHub](GITHUB_PREPARACION.md).
