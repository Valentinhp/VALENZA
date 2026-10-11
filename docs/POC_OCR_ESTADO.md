# Estado del POC OCR local

## Alcance implementado

El incremento inicial implementa:

- Modelo de salida canónico en estado `proposed`.
- Parseo local de texto para comprobantes de Mercado Pago y capturas/resúmenes de Nu.
- Conversión monetaria con `Decimal` e importes enteros en centavos.
- Conservación de filas repetidas; no se deduplican por fecha e importe.
- Detección de `WALLET_BALANCE` para `Dinero en Mercado Pago`.
- Huella SHA-256 de archivos.
- Adaptadores opcionales para texto nativo de PDF con PyMuPDF y OCR local con Tesseract.
- Fixtures sintéticos únicamente.

## Dependencias verificadas

- Python 3.13.5 x64.
- PyMuPDF 1.28.2 instalado en el entorno del proyecto.
- Pillow 10.4.0 para generar PNG/JPEG sintéticos.
- pytest 8.4.2.
- psutil 6.1.1 para la medición aproximada de RSS del proceso.
- Tesseract OCR 5.4.0.20240606 para Windows x64, instalado en `C:\Program Files\Tesseract-OCR`.
- Leptonica 1.84.1.

La instalación de Tesseract se verificó con `tesseract --version`. No se modificó ninguna configuración de red ni se enviaron documentos.

No existe todavía:

- Escritura contable.
- Base de datos o migraciones.
- Interfaz gráfica.
- Conciliación automática.
- Envío a servicios externos.
- Validación contra capturas o documentos reales.

## Validación ejecutada

El 10 de octubre de 2026 se ejecutaron quince pruebas automatizadas con Python 3.13.5:

```text
15 passed in 7.03s
```

Las pruebas cubren importes en centavos, fechas que no deben interpretarse como importes, repetición de cargos, wallet de Mercado Pago, captura parcial de Nu, campos desconocidos y huella de archivo.

También cubren extracción de PDF digital, OCR de PNG y JPEG, PDF corrupto, imagen ausente, extensión no soportada, imagen ilegible y ejecutable Tesseract no configurado.

## Medición inicial

Medición local del 10 de octubre de 2026 con procesos separados de Python:

| Caso | Tiempo | RSS máximo aproximado |
|---|---:|---:|
| PDF digital Mercado Pago | 1881.11 ms | 44.61 MB |
| PNG OCR Mercado Pago | 2656.09 ms | 17.41 MB |
| JPEG OCR Nu | 2826.66 ms | 17.39 MB |

Estas cifras son una línea base del proceso de prueba, no un benchmark formal del equipo i7-7600U. El entorno reportado por la sesión no permite demostrar que la ejecución se realizó en ese CPU concreto; por tanto EV-02 continúa pendiente.

Este resultado no valida la exactitud OCR exigida por D-032. Para ello aún se necesita un corpus autorizado de Nu y Mercado Pago y medir las cuatro variantes: Nu PDF, Nu captura, Mercado Pago PDF y Mercado Pago captura.

## Próximo paso

Validar con un corpus autorizado de documentos reales anonimizados, repetir el benchmark en el equipo objetivo y evaluar la integración de una vista previa editable. Todo resultado seguirá siendo una propuesta hasta revisión humana.
