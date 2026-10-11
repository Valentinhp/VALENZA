# Valenza

Aplicación financiera local en Python, PySide6 y SQLCipher. El paquete mantiene
el nombre técnico `sgccc`. Separa participaciones personales y familiares,
abonos recibidos y pagos reales a instituciones.

## Instalación

Entorno comprobado: Windows x64 y Python 3.13. Se requiere Python 3.12 o posterior;
la disponibilidad de SQLCipher depende de la plataforma y versión de Python.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[gui,ocr,cipher,test]"
```

PyMuPDF extrae texto localmente. Para OCR de documentos escaneados, instala
Tesseract por separado y añade su ejecutable al PATH. Los PDF con texto no lo
necesitan. SQLCipher es obligatorio para archivos persistentes; SQLite sin
cifrado se limita a pruebas sintéticas explícitas en memoria.

## Ejecución

```powershell
.\.venv\Scripts\python.exe -m sgccc.gui.app
```

La clave local se solicita en la interfaz y no debe guardarse en Git. En Windows
la base habitual se encuentra en `%USERPROFILE%/AppData/Local/SGCCC/sgccc.db`.
Las migraciones de bases existentes crean y verifican un respaldo cifrado antes
de actualizar el esquema. Una clave incorrecta no reemplaza la base existente.

Para explorar sin abrir archivos de base de datos:

```powershell
.\.venv\Scripts\python.exe -m sgccc.gui.app --demo
```

`--test-database` abre una base separada `sgccc-test.db` en el directorio de datos
y muestra una identificación permanente. Nunca uses una base personal para
desarrollo. El comando instalado `sgccc-demo` conserva su nombre por
compatibilidad: sin `--demo` también abre la base habitual.

## Funciones

- Pedidos: conceptos manuales con reparto, importación revisable de compras y
  recargas de Mercado Pago, sin guardar antes de la confirmación.
- Devoluciones y recompras vinculadas: movimientos y ajustes auditables separados.
- Cobros: participaciones y abonos. Tarjetas: cargos y pagos bancarios reales.
- Inicio: indicadores separados, descuentos personales, resultado previsto y
  comparación con consultas manuales de deuda bancaria.

Los descuentos no reducen automáticamente las participaciones familiares.
Una compensación familiar no es un pago bancario; una consulta bancaria no crea
movimientos. El resultado previsto no representa dinero cobrado. Suscripciones
permanece pendiente; MSI requiere calendarios y aplicaciones de pagos confirmadas.
No existe conciliación bancaria automática ni OCR en la nube.

## Pruebas

Los tests usan datos sintéticos, fixtures anonimizados y bases temporales.
Los documentos personales originales no forman parte del proyecto.

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp=.test-run
```

`--basetemp` debe señalar un directorio desechable: pytest elimina su contenido
previo. Algunos tests OCR dependen de Tesseract; revisa los tests omitidos si no
está instalado. La suite cubre reglas financieras, SQLCipher, migraciones e interfaz.
Para regenerar los cuatro documentos sintéticos básicos:

```powershell
.\.venv\Scripts\python.exe tools/create_synthetic_documents.py
```

Los demás fixtures de importación se conservan versionados. `docs/` contiene
modelos y notas históricas de etapas anteriores; este README describe la ejecución actual.

## Git y recuperación

`.gitignore` excluye bases, respaldos, claves, configuración privada, PDFs
personales, capturas, logs y temporales. Solo los fixtures binarios revisados
tienen excepciones explícitas. Revisa los textos antes de añadir archivos nuevos:
Gitignore no detecta secretos dentro del código.

Consulta [Preparación y publicación privada](docs/GITHUB_PREPARACION.md).
La etiqueta `v0.1.0-pre-estabilizacion` identifica el código previo a los cambios
grandes. No sustituye un respaldo cifrado de datos. Para recuperar el código
en una rama separada:

```powershell
git switch -c recuperar-base v0.1.0-pre-estabilizacion
```
