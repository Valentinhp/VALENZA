# Valenza · Brand Experience y Warm Finance

Implementación de presentación del 13 de octubre de 2026. No modifica fórmulas,
repositorio financiero, identificadores, nombres guardados, esquema o migraciones.

## Sistema visual

`src/valenza/gui/design_system.py` instala la paleta semántica, tipografía del
sistema, controles, estados y estilo Fusion. Las superficies y gráficos específicos
permanecen en `warm_finance.py`; los botones, tablas y campos ya no duplican sus
reglas allí. Se conservan Georgia para títulos y Segoe UI para texto, sin incluir
archivos de fuentes externas.
La instalación es idempotente: reutilizar QApplication no reinstala el tema ni
recalcula estilos de ventanas cerradas que Qt aún conserva.

El estilo global cubre combos, sus vistas reales, menús y submenús, calendario,
fecha, spinboxes, campos, texto multilínea, checks, radios, pestañas, tablas,
encabezados, listas, scrollbars horizontales y verticales, tooltips, progreso,
mensajes y diálogos. El filtro de presentación aplica también el estilo al popup
real de QComboBox. La navegación y selección siguen siendo controles Qt estándar.
Los botones primarios conservan el terracota con un tono más profundo: texto claro
sobre `#a65e3e` alcanza un contraste aproximado de 4.71:1. El texto secundario
sobre el fondo cálido alcanza 4.61:1. Esto no constituye una certificación completa
de accesibilidad del producto.
Los campos que ya tienen un validador señalan entrada inválida al perder foco;
el sistema no introduce nuevas reglas de validación financiera.

Los selectores de archivos usan diálogos Qt para que respaldo, restauración,
importación y exportación compartan la presentación. Se carga la traducción
española de Qt incluida en PySide6, cuando está disponible. Las ilustraciones de
confirmación conservan su semántica estándar con colores Warm Finance.

## Identidades locales

`branding.py` reconoce alias explícitos después de normalizar mayúsculas, espacios,
acentos y signos. No utiliza coincidencias por subcadenas ni últimos dígitos.

| Identidad | Recurso |
| --- | --- |
| Spotify, YouTube / Premium, Netflix | SVG local |
| Amazon Prime, Prime Video, Apple Music | SVG local |
| Nu / Nubank, Mercado Pago, HSBC | SVG local |
| Disney+, BBVA, Santander, Banorte | Distintivo de texto neutral |
| Servicios o instituciones desconocidos | Icono genérico propio |

Los distintivos de texto son una limitación explícita: no son logotipos oficiales.
La versión revisada del catálogo no ofrece esos cuatro recursos; no se incluyen
imágenes de fuentes sin procedencia o licencias verificables.

Los nueve SVG proceden de [Simple Icons 13.21.0](https://github.com/simple-icons/simple-icons/tree/13.21.0),
un catálogo con fuentes originales por marca. Los archivos se conservan sin cambiar
su geometría. Se renderizan en el color publicado en los metadatos, con padding
uniforme y tamaños discretos. `assets/brands/manifest.json` conserva título, origen,
directrices disponibles, URL versionada y SHA-256. Se incluyen `LICENSE.md` y
`DISCLAIMER.md`: la licencia CC0 del proyecto no elimina los derechos de marca ni
implica patrocinio. Véase el [aviso del catálogo](https://github.com/simple-icons/simple-icons/blob/13.21.0/DISCLAIMER.md).

`tools/vendor_brand_icons.py` es una herramienta de desarrollo; la aplicación
no descarga ni consulta ningún recurso al ejecutarse. El paquete incluye SVG,
metadatos, avisos y controles propios mediante `pyproject.toml`.

Suscripciones muestra identidad del servicio en tabla, ficha y edición; su medio
vinculado aparece por separado. Tarjetas, Inicio y selectores muestran institución;
Pedidos y Cobros muestran el instrumento registrado cuando existe un pedido
vinculado. Importación, devolución y recompra incluyen identidad en sus selectores.
Los cobros sin asociación explícita no deducen un banco de referencias libres.

`PaymentIdentity` distingue tarjeta, línea de crédito, billetera y otro medio.
Una tarjeta llamada «Mercado Pago 1234» cuyo registro apunta a Nu sigue mostrando
Nu como institución; la billetera de Mercado Pago se presenta como billetera.

## Revisión reproducible

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe tools/preview_brand_experience.py
$env:QT_SCALE_FACTOR = '1.5'
.\.venv\Scripts\python.exe tools/preview_brand_experience.py
```

Capturas en `artifacts/brand-experience/1` y `1.5`: siete pantallas a 1080×760 y
680×480, zonas inferiores con scroll, edición de suscripción, popup de tarjetas,
galería de controles, popup de servicios, menú contextual, confirmación y selector
de archivos. Se emplea exclusivamente una base sintética cifrada temporal.
La carga de fuentes de Windows en esta herramienta corrige una limitación de
enumeración de fuentes del backend offscreen; no se distribuyen esas fuentes.

Se revisaron las capturas de controles, Suscripciones, edición, popups,
confirmaciones, archivos y vistas reducidas de Pedidos, Cobros y Tarjetas.
Las tablas anchas conservan desplazamiento horizontal. La galería verifica
controles sin uso actual en las pantallas, como radios, pestañas y progreso.
Las pruebas existentes cubren los flujos secundarios de PDF, devolución,
recompra, MSI, pagos y abonos. Esto no equivale a una revisión manual de todas
las combinaciones posibles de datos, estados y diálogos en Windows interactivo.

`tests/test_brand_experience.py` añade 17 comprobaciones de alias, integridad de
recursos, teclado en el popup, diálogo Qt e invariancia de datos con nombres de
tarjetas deliberadamente ambiguos.

Para evitar la lentitud acumulada de Qt descrita en la validación anterior,
`tools/validate_brand_experience.py` ejecuta cada módulo en un proceso independiente
y guarda logs e informes JUnit en `.brand-validation/`. El primer intento del
lanzador se corrigió para crear el directorio padre de temporales antes de pytest;
sus informes parciales no cuentan como validación final.
La compilación de wheel no se realizó: este entorno no tiene `setuptools`.
La inclusión de recursos está declarada en la configuración del paquete.

La revisión detectó y corrigió una regresión de altura: la regla de altura mínima
para campos de una línea ya no se aplica a QTextEdit / QPlainTextEdit. Así se
conserva la altura mínima del detalle de Pedidos en ventanas pequeñas.
También se añadió `WarmScrollArea` al diálogo de recompra: muestra el rectángulo
completo del campo, incluido su borde, al desplazarlo y navegar con Tab. Qt puede
usar únicamente el rectángulo del cursor en `ensureWidgetVisible`, como muestra
su [implementación de QScrollArea](https://github.com/qt/qtbase/blob/6.8/src/widgets/widgets/qscrollarea.cpp).
La corrección conserva el tamaño de la ventana, el pie fijo y los valores capturados.

## Resultado final

- **488 casos en 44 módulos: 486 aprobados, 1 omitido y 1 fallo esperado.**
- Cero fallos inesperados y cero errores en los informes finales de cada módulo.
- La omisión y el fallo esperado son los casos históricos identificados en
  `VALIDACION_ADMIN_2026-10-13.md`; no se modificaron ni se ocultaron pruebas.
- El módulo completo de previsualización de devoluciones se volvió a ejecutar
  después de corregir el scroll: **28 aprobadas**. Las tres dimensiones del
  diálogo dinámico también se verificaron por separado: **3 aprobadas**.
- Los ajustes finales de institución y ventana pequeña: **2 aprobadas**.
- **70 capturas** de pantallas y controles a 100 % y 150 %, más capturas del
  diálogo de recompra a 760×560, 640×360 y 480×280 en
  `artifacts/brand-experience/refund/`.
- `git diff --check`, compilación Python e inclusión declarada de todos los
  assets locales: correctos. Los SVG de marca suman aproximadamente 21 KB.

Los informes JUnit y `.brand-validation/summary.json` conservan los resultados
finales. La ejecución general inicial y la ejecución por módulos anterior a la
corrección del scroll no constituyen el resultado final; el informe de ese módulo
se reemplazó mediante una nueva ejecución completa y se volvió a sumar el conjunto.
