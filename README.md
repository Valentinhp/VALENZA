<div align="center">

# VALENZA

### Finanzas personales y familiares, con cada movimiento en su lugar.

**Una aplicación de escritorio para administrar compras, participaciones, cobros, tarjetas y compromisos financieros con claridad, trazabilidad y control local.**

<br>

![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![PySide6](https://img.shields.io/badge/Interfaz-PySide6-41CD52?style=for-the-badge&logo=qt&logoColor=white)
![SQLCipher](https://img.shields.io/badge/Datos-SQLCipher-36454F?style=for-the-badge&logo=sqlite&logoColor=white)
![Windows](https://img.shields.io/badge/Plataforma-Windows%20x64-0078D4?style=for-the-badge&logo=windows&logoColor=white)

<br>

**Local primero** · **Datos cifrados** · **Repartos auditables** · **Control financiero claro**

[Características](#caracteristicas) · [Instalación](#instalacion) · [Modelo financiero](#modelo-financiero) · [Seguridad](#seguridad) · [Documentación](#documentacion)

</div>

---

## ✨ Una forma más clara de llevar tus cuentas

Cuando una compra incluye productos de varias personas, descuentos, pagos a meses, devoluciones o una recompra, una sola cifra deja de contar toda la historia.

**Valenza** organiza esas piezas sin confundirlas. Permite saber **qué se compró**, **a quién le corresponde**, **cuánto se cargó realmente a la tarjeta**, **qué dinero ya se recibió** y **qué falta por pagar**.

Su interfaz de escritorio utiliza el lenguaje visual **Warm Finance**, con información agrupada, indicadores legibles y operaciones que requieren confirmación antes de afectar los registros.

La interfaz comparte el sistema Warm Finance para controles, popups y diálogos. Los servicios e instituciones reconocidos usan recursos locales; el reconocimiento no modifica nombres ni datos financieros. Consulta el [alcance del branding y la revisión visual](docs/BRAND_EXPERIENCE.md), incluidas las marcas que emplean distintivos de texto en lugar de logotipos oficiales.

> **La idea central:** que el dinero recibido de una persona, la deuda bancaria y los beneficios por descuentos nunca se traten como si fueran el mismo movimiento.

<a id="caracteristicas"></a>

## 🧩 Qué puedes hacer

| Módulo | Funcionalidades |
|:--|:--|
| **🏠 Inicio** | Indicadores personales y familiares, compromisos por mes, distribución del pendiente, calendario MSI y resultado previsto. |
| **🛍️ Pedidos** | Registrar compras por conceptos y responsables; revisar importaciones de compras y recargas de Mercado Pago antes de guardarlas. |
| **↩️ Devoluciones y recompras** | Vincular reembolsos, sustituciones y compensaciones, con ajustes de reparto e historial auditable. |
| **🤝 Cobros** | Consultar pendientes, registrar abonos individuales y realizar **abonos globales por persona** distribuidos entre varias cuentas. |
| **💳 Tarjetas** | Separar cargos, pagos bancarios reales, consultas de saldo, instrumentos y seguimiento de MSI. |
| **🔁 Suscripciones** | Crear, editar, pausar o cancelar suscripciones; registrar o vincular cargos reales sin convertir previsiones en deuda bancaria. |
| **📄 Reportes PDF** | Generar estados de cuenta familiares con conceptos, participaciones, abonos y devoluciones diferenciados. |

### Cobros consolidados, sin abrir cada pedido

Selecciona una persona, consulta su pendiente, introduce el importe recibido y **revisa cómo se distribuirá** entre sus cuentas antes de confirmar. Los MSI futuros no se incluyen automáticamente; requieren una decisión explícita.

Un abono global se registra como **un ingreso con varias aplicaciones**, evitando contar varias veces una misma transferencia. Los abonos individuales siguen disponibles.

### Devoluciones sin perder el historial

Los movimientos de devolución, recompra y compensación se conservan separados de la compra original. Los repartos pueden corregirse mediante ajustes auditables, sin convertir automáticamente una compensación en un pago recibido o bancario.

---

<a id="modelo-financiero"></a>

## ⚖️ Una regla fundamental: cada cosa en su lugar

Valenza distingue conceptos que en una hoja de cálculo suelen mezclarse:

| Concepto | Qué representa | Qué **no** representa |
|:--|:--|:--|
| **Participación familiar** | Lo que corresponde pagar a una persona por sus compras. | El cargo real a la tarjeta. |
| **Descuento personal** | Un beneficio aplicado al costo de la operación. | Un abono hecho por un familiar. |
| **Cargo real** | El importe efectivamente cargado al instrumento bancario. | La suma necesariamente exigible a la familia. |
| **Abono recibido** | Dinero entregado por una persona para cubrir su pendiente. | Un pago automático al banco. |
| **Pago bancario** | Dinero pagado efectivamente a una institución. | Un cobro familiar. |
| **Consulta bancaria** | Una referencia de saldo informada o capturada. | Un movimiento que cambie la deuda calculada. |
| **Previsión** | Un compromiso o resultado esperado. | Dinero cobrado o cargo bancario confirmado. |

### Ejemplo: un descuento que beneficia a quien realizó la compra

Supongamos una operación **ficticia** con **$600.00 MXN** en productos, un **descuento personal de $60.00 MXN** y un **cargo real de $540.00 MXN**.

Si los productos familiares suman **$480.00 MXN** y la compra personal **$120.00 MXN**, el costo personal neto previsto es **$60.00 MXN** (`120.00 − 60.00`), sin reducir la participación familiar.

Este es un **ejemplo ilustrativo**, no un registro incluido en la aplicación.

### MSI y compromisos futuros

Los meses sin intereses se gestionan con sus periodos y aplicaciones de pago. Se distinguen cuotas anteriores, actuales, futuras y periodos todavía no confirmados. **Un compromiso previsto no equivale por sí mismo a un cargo confirmado por el banco.**

---

<a id="instalacion"></a>

## 🚀 Instalación

### Requisitos

- **Windows x64**, entorno comprobado para el proyecto.
- **Python 3.12 o superior**; la configuración verificada utiliza **Python 3.13**.
- Disponibilidad de las dependencias de **SQLCipher** para tu plataforma y versión de Python.
- **Tesseract OCR** *(opcional)* para documentos escaneados que requieran reconocimiento de texto.

> [!IMPORTANT]
> SQLCipher es obligatorio para las bases persistentes. El uso de SQLite sin cifrado está limitado a pruebas sintéticas explícitas en memoria.

### 1. Preparar el entorno

Desde PowerShell, en la carpeta del proyecto:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[gui,ocr,cipher,test]"
```

Si utilizas otra versión compatible de Python, adapta el primer comando.

### 2. Iniciar Valenza

```powershell
.\.venv\Scripts\python.exe -m valenza.gui.app
```

También puedes ejecutar **`Abrir-Valenza.cmd`** desde la carpeta del proyecto, una vez preparado el entorno. El comando instalado `valenza` inicia la aplicación.

### 3. Explorar con datos sintéticos

¿Quieres conocer la interfaz sin abrir una base personal?

```powershell
.\.venv\Scripts\python.exe -m valenza.gui.app --demo
```

El comando `valenza-demo --demo` también permite explorar el entorno de demostración.

> [!TIP]
> La opción `--test-database` utiliza una base separada (`valenza-test.db`) e incorpora una identificación visual permanente. **No utilices una base personal para desarrollo o pruebas.**

### Importación de documentos

**PyMuPDF** permite extraer texto de PDF de manera local. Para archivos escaneados, instala **Tesseract** por separado y añade su ejecutable al `PATH`. Los PDF que ya contienen texto no lo necesitan.

---

<a id="seguridad"></a>

## 🔐 Privacidad y protección de datos

Valenza está pensado para trabajar con información financiera local y separar los datos personales de los entornos de prueba.

- **Base persistente cifrada con SQLCipher.** La clave se solicita en la interfaz y no debe almacenarse en Git.
- **Sin OCR en la nube.** El procesamiento documental descrito se realiza localmente.
- **Migraciones con respaldo.** Las migraciones de bases existentes crean y verifican un respaldo cifrado antes de actualizar el esquema.
- **Protección ante claves incorrectas.** Una contraseña equivocada no reemplaza la base existente.
- **Auditoría de correcciones.** Los ajustes financieros compatibles conservan trazabilidad de los cambios.
- **Pruebas aisladas.** Los tests utilizan datos sintéticos, fixtures anonimizados y bases temporales.

**Ubicación habitual de la base en Windows:**

```text
%USERPROFILE%\AppData\Local\Valenza\valenza.db
```

Si existe una base de una instalación anterior de **SGCCC**, Valenza continúa utilizándola en su ubicación original, sin moverla ni duplicarla. La misma compatibilidad de ubicación aplica a la base de pruebas.

> [!CAUTION]
> El cifrado no sustituye una política de respaldos ni la protección del equipo y de la contraseña. No publiques bases de datos, claves, documentos personales o archivos de configuración privada.

---

## 🧪 Desarrollo y pruebas

La suite de pruebas cubre reglas financieras, persistencia cifrada, migraciones e interfaz. Para ejecutar las pruebas Qt sin una ventana visible:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp=.test-run
```

> [!WARNING]
> `--basetemp` debe apuntar a un directorio **desechable**: pytest elimina su contenido anterior. Algunas pruebas OCR pueden omitirse cuando Tesseract no está instalado.

Para regenerar los cuatro documentos sintéticos básicos:

```powershell
.\.venv\Scripts\python.exe tools/create_synthetic_documents.py
```

Los demás fixtures de importación se conservan versionados. Los documentos personales originales no forman parte del proyecto.

### Tecnologías

| Componente | Tecnología |
|:--|:--|
| Aplicación | Python |
| Interfaz de escritorio | PySide6 / Qt |
| Persistencia cifrada | SQLCipher |
| Lectura de PDF | PyMuPDF |
| OCR opcional | Tesseract |
| Pruebas automatizadas | pytest |

---

<a id="documentacion"></a>

## 📚 Documentación

| Recurso | Contenido |
|:--|:--|
| [**CHANGELOG.md**](CHANGELOG.md) | Historial de actualizaciones. |
| [**Brand Experience**](docs/BRAND_EXPERIENCE.md) | Sistema Warm Finance, recursos locales y validación visual. |
| [**Desglose por persona en Inicio**](docs/INICIO_DESGLOSE_PERSONAS.md) | Personas desplegables, pedidos pendientes y liquidados. |
| [**Validación de administración**](docs/VALIDACION_ADMIN_2026-10-13.md) | Pruebas de Suscripciones, Usuarios y Configuración. |
| [**Estado actual**](docs/ESTADO_ACTUAL.md) | Capacidades vigentes y límites conocidos. |
| [**Validación del 12 de octubre de 2026**](docs/VALIDACION_2026-10-12.md) | Resultados registrados de pruebas y empaquetado. |
| [**Estabilización y uso cotidiano**](docs/ESTABILIZACION.md) | Edición de cuentas, respaldos, restauración y reportes familiares. |
| [**Preparación para GitHub**](docs/GITHUB_PREPARACION.md) | Revisión y publicación privada del repositorio. |

> Los archivos de `docs/` también contienen modelos y notas históricas. **Este README describe la ejecución actual**; consulta el estado y el changelog para conocer los cambios y las limitaciones.

## 🛡️ Antes de publicar el repositorio

El archivo `.gitignore` excluye bases de datos, respaldos, claves, configuración privada, PDF personales, capturas, registros y temporales, con excepciones explícitas para fixtures binarios revisados.

**Revisa siempre los archivos antes de subirlos:** `.gitignore` no puede detectar secretos incrustados en código o documentos. Consulta la [guía de preparación para GitHub](docs/GITHUB_PREPARACION.md).

### Punto de recuperación del código

La etiqueta `v0.1.0-pre-estabilizacion` identifica el código anterior a una serie de cambios importantes. Puedes recuperarlo en una rama independiente:

```powershell
git switch -c recuperar-base v0.1.0-pre-estabilizacion
```

Esta etiqueta **no reemplaza un respaldo cifrado de tus datos**.

---

## 📌 Alcance actual

Valenza es una herramienta de **organización y seguimiento financiero**, no un servicio bancario. Actualmente **no realiza conciliación bancaria automática ni OCR en la nube**. Los saldos consultados manualmente y los compromisos previstos se mantienen diferenciados de los movimientos confirmados.

<div align="center">

---

### VALENZA

**Tus compras. Tus cuentas. Cada centavo en su lugar.**

<sub>Aplicación de escritorio · Python · PySide6 · SQLCipher</sub>

</div>
