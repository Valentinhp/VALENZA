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

La interfaz comparte el sistema Warm Finance para controles, popups y diálogos. Los servicios e instituciones reconocidos usan recursos locales, incluido **Meli+** en Suscripciones; el reconocimiento no modifica nombres ni datos financieros. Consulta el [alcance del branding y la revisión visual](docs/BRAND_EXPERIENCE.md), incluidas las marcas que emplean distintivos de texto en lugar de logotipos oficiales.

> **La idea central:** que el dinero recibido de una persona, la deuda bancaria y los beneficios por descuentos nunca se traten como si fueran el mismo movimiento.

<a id="caracteristicas"></a>

## 🧩 Qué puedes hacer

| Módulo | Funcionalidades |
|:--|:--|
| **🏠 Inicio** | Indicadores personales y familiares, compromisos por mes, distribución del pendiente, calendario MSI y resultado previsto, con explicaciones de periodos y desgloses. |
| **👥 Usuarios** | Crear y editar personas, configurar al propietario y desactivar o reactivar personas conservando sus movimientos históricos. |
| **🛍️ Pedidos** | Registrar compras por conceptos y responsables; revisar importaciones de compras y recargas de Mercado Pago antes de guardarlas. |
| **↩️ Devoluciones y recompras** | Vincular reembolsos, sustituciones y compensaciones, con ajustes de reparto e historial auditable. |
| **🤝 Cobros** | Consultar pendientes e historial, editar o anular abonos y realizar **abonos globales por persona** distribuidos entre varias cuentas. Consultar un abono y editarlo son acciones separadas. |
| **💳 Tarjetas** | Separar cargos, pagos bancarios reales, consultas de saldo, instrumentos y seguimiento de MSI; consultar la programación por vencimiento y comparar manualmente con el banco. |
| **🔁 Suscripciones** | Crear, editar, pausar o cancelar previsiones en Valenza; registrar o vincular cargos reales, revisar recargos y eliminar definitivamente con vista previa y respaldo cifrado. |
| **💵 Revisar efectivo** | Contar dinero de forma independiente, marcar pedidos y parciales, guardar cortes JSON o versiones dentro de la app, consultarlos y retomarlos. |
| **🔎 Buscar** | Localizar personas, pedidos, compras históricas, tarjetas, abonos y pagos bancarios desde **Buscar · Ctrl+K**, sin mostrar importes en los resultados. |
| **📄 Reportes PDF** | Generar estados de cuenta familiares con conceptos, participaciones, abonos y devoluciones diferenciados. |
| **⚙️ Configuración** | Configurar al propietario, crear y restaurar respaldos cifrados y ejecutar un diagnóstico de integridad. |

### Cobros consolidados, sin abrir cada pedido

Selecciona una persona, consulta su pendiente, introduce el importe recibido y **revisa cómo se distribuirá** entre sus cuentas antes de confirmar. Los MSI futuros no se incluyen automáticamente; requieren una decisión explícita.

Un abono global se registra como **un ingreso con varias aplicaciones**, evitando contar varias veces una misma transferencia. Los abonos individuales siguen disponibles.

Al seleccionar un abono del historial, Valenza muestra una **consulta de solo lectura**. Para modificarlo, utiliza **Editar abono seleccionado**: se actualiza el registro original, sin crear otro ingreso. **Volver a mi selección y borrador** recupera el contexto de captura anterior.

### Contar dinero y conservar tus cortes

Desde **Inicio → Revisar efectivo**, puedes marcar pedidos completos, indicar cantidades parciales y añadir dinero propio u otro efectivo. Este conteo es independiente: **no registra abonos, pagos al banco ni cambios de deuda**.

| Acción | Qué conserva y dónde encontrarlo |
|:--|:--|
| **Guardar corte** | Crea un archivo **JSON** en la ubicación que elijas, con importes y casillas seleccionadas. |
| **Abrir corte** | Recupera un JSON compatible y actualiza sus importes, marcas y barra de avance. También admite cortes anteriores de preparación. |
| **Guardar en la app** | Conserva una versión interna del conteo para la tarjeta seleccionada. |
| **Conteos guardados** | Permite consultar versiones por fecha e importes, abrir una para continuar o exportarla a JSON. |
| **Nuevo conteo** | Comienza desde cero sin borrar los archivos ni las versiones previamente guardadas. |

La barra compara lo identificado con el dinero físico o el objetivo del corte; si no se indicó dinero físico, muestra el avance frente al total de referencia de los pedidos. Las versiones guardadas **no se suman entre sí**.

### Encontrar registros y comprobar lo guardado

**Buscar · Ctrl+K** abre el registro correspondiente; las compras históricas llevan a sus participaciones en Cobros. Los resultados no muestran cantidades, aunque los importes personales estén visibles en Inicio.

Los avisos de guardado indican dónde consultar lo registrado; al generar un PDF se muestra el nombre y la ubicación del archivo. Los borradores de gastos nuevos se conservan **mientras Valenza siga abierta**: cerrar el formulario no equivale a guardar el gasto en la base.

### Devoluciones sin perder el historial

Los movimientos de devolución, recompra y compensación se conservan separados de la compra original. Los repartos pueden corregirse mediante ajustes auditables, sin convertir automáticamente una compensación en un pago recibido o bancario.

El seguimiento distingue reembolsos pendientes y acreditados, su destino y las recompras vinculadas. No presupone que un saldo reembolsado siga disponible en Mercado Pago ni reconstruye su consumo posterior sin registros que lo demuestren.

### Suscripciones con un alcance explícito

Una previsión mensual no crea por sí sola un cargo bancario. Si el cargo ya fue importado como pedido, puedes **vincularlo** a la suscripción en lugar de registrarlo otra vez.

Al editar, revisa la opción de **quitar o reducir también los recargos de cargos ya registrados** y su vista previa: puede ajustar deuda familiar anterior sin modificar el cargo bancario ni los abonos. Pausar o cancelar la previsión conserva los pendientes existentes.

> [!IMPORTANT]
> **Cancelar una previsión en Valenza no cancela el servicio ni los cobros del proveedor.** La baja del servicio se gestiona directamente con el proveedor. **Eliminar definitivamente** es otra operación: su confirmación explica los registros vinculados que retirará y exige un respaldo cifrado.

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
| **Conteo de efectivo** | Dinero identificado manualmente durante una revisión. | Un abono registrado, un pago bancario o un saldo disponible confirmado. |

### Ejemplo: un descuento que beneficia a quien realizó la compra

Supongamos una operación **ficticia** con **$600.00 MXN** en productos, un **descuento personal de $60.00 MXN** y un **cargo real de $540.00 MXN**.

Si los productos familiares suman **$480.00 MXN** y la compra personal **$120.00 MXN**, el costo personal neto previsto es **$60.00 MXN** (`120.00 − 60.00`), sin reducir la participación familiar.

Este es un **ejemplo ilustrativo**, no un registro incluido en la aplicación.

### MSI y compromisos futuros

Los meses sin intereses se gestionan con sus periodos y aplicaciones de pago. Se distinguen cuotas anteriores, actuales, futuras y periodos todavía no confirmados. **Un compromiso previsto no equivale por sí mismo a un cargo confirmado por el banco.**

### Un mes seleccionado no convierte todos los saldos en históricos

El selector **Mes de compromisos** de Inicio cambia la programación mensual, el calendario y la gráfica mensual. **Mi parte pendiente, Cobros familiares y Deuda total** son saldos actuales; descuentos y resultado personal previsto corresponden a las operaciones activas, no exclusivamente al mes seleccionado.

**Compromisos del mes** de Inicio y la **programación mensual de Tarjetas** pueden diferir: Inicio atribuye al mes una parte de la deuda pendiente actual, separando cuotas futuras, anteriores y sin fecha; Tarjetas muestra lo programado para vencer antes de pagos y distingue las aplicaciones conocidas. Un pago sin asignar puede reducir la deuda total sin indicar qué mes cubre. Los desgloses explican estas diferencias: **no son importes que deban coincidir ni sumarse entre sí**.

Las consultas bancarias guardan una referencia manual con su tipo, fecha y alcance. Una **diferencia histórica** compara con la fotografía de Valenza al guardar la consulta, no con la deuda actual. Ninguna previsión sustituye el importe oficial que informa el banco.

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
- **Respaldos desde Configuración.** Crear respaldo conserva una copia cifrada y verificada; Restaurar respaldo requiere confirmación, reemplaza los datos activos y conserva antes una copia de seguridad.
- **Protección ante claves incorrectas.** Una contraseña equivocada no reemplaza la base existente.
- **Auditoría de correcciones.** Los ajustes financieros compatibles conservan trazabilidad de los cambios.
- **Pruebas aisladas.** Los tests utilizan datos sintéticos, fixtures anonimizados y bases temporales.

Los cortes **JSON exportados son archivos legibles y no están cifrados**. Pueden contener nombres, importes y selecciones: guárdalos como información privada. No equivalen a un respaldo completo de la base. Las versiones internas de los conteos se conservan dentro de la base cifrada.

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
| [**Claridad: etapas 1 a 3**](docs/CLARIDAD-ETAPAS-1-A-3.md) | Acciones y confirmaciones, significado de cifras, consulta de abonos y navegación. Incluye resultados de validación; las evidencias de `artifacts/` se conservan localmente y no se publican en Git. |
| [**Auditoría de claridad**](docs/AUDITORIA-CLARIDAD-VALENZA.md) | Diagnóstico, hallazgos y propuestas; las etapas 4 y 5 siguen pendientes de autorización. |
| [**Buscador**](docs/BUSCADOR_ETAPA1.md) | Alcance de búsqueda y privacidad de los resultados. |
| [**Revisión de efectivo**](docs/REVISION_EFECTIVO.md) | Conteo independiente y separación respecto a cobros y pagos. |
| [**Preparar pago y cortes**](docs/PREPARAR_PAGO.md) | Formato de cortes y antecedentes de la preparación independiente. |
| [**Total mensual de Inicio**](docs/INICIO_TOTAL_MENSUAL.md) | Alcance del indicador y separación de mensualidades. |
| [**Periodos y comparación bancaria**](docs/PERIODOS_Y_COMPARACION_BANCARIA.md) | Previsión por vencimiento, saldos actuales y consultas guardadas. |
| [**Seguimiento de reembolsos**](docs/SEGUIMIENTO-REEMBOLSO-ALTERNATIVA-A.md) | Estados, destinos, recompras y límites de trazabilidad. |
| [**Recargos de suscripciones**](docs/RECARGOS-SUSCRIPCIONES-ACTUALIZACION.md) | Reducción de recargos anteriores y efecto sobre el recuento independiente. |
| [**Eliminar suscripciones**](docs/ELIMINACION-SUSCRIPCIONES.md) | Alcance de la eliminación definitiva, restricciones y respaldo previo. |
| [**Validación de administración**](docs/VALIDACION_ADMIN_2026-10-13.md) | Pruebas de Suscripciones, Usuarios y Configuración. |
| [**Estado actual**](docs/ESTADO_ACTUAL.md) | Capacidades vigentes y límites conocidos. |
| [**Validación del 12 de octubre de 2026**](docs/VALIDACION_2026-10-12.md) | Resultados registrados de pruebas y empaquetado. |
| [**Estabilización y uso cotidiano**](docs/ESTABILIZACION.md) | Edición de cuentas, respaldos, restauración y reportes familiares. |
| [**Preparación para GitHub**](docs/GITHUB_PREPARACION.md) | Revisión y publicación privada del repositorio. |

> Los archivos de `docs/` también contienen modelos y notas históricas. **Este README describe la ejecución actual**; consulta el estado y el changelog para conocer los cambios y las limitaciones.

## 🛡️ Antes de publicar el repositorio

El archivo `.gitignore` excluye bases de datos, respaldos, claves, configuración privada, PDF personales, capturas, registros y temporales, con excepciones explícitas para fixtures binarios revisados. También excluye `artifacts/` y los cortes locales de la raíz con nombres `corte-*.json` y `preparacion-*.json`; si exportas con otro nombre o ubicación, comprueba que el archivo no se incluya en Git.

**Revisa siempre los archivos antes de subirlos:** `.gitignore` no puede detectar secretos incrustados en código o documentos. Consulta la [guía de preparación para GitHub](docs/GITHUB_PREPARACION.md).

### Punto de recuperación del código

La etiqueta `v0.1.0-pre-estabilizacion` identifica el código anterior a una serie de cambios importantes. Puedes recuperarlo en una rama independiente:

```powershell
git switch -c recuperar-base v0.1.0-pre-estabilizacion
```

Esta etiqueta **no reemplaza un respaldo cifrado de tus datos**.

---

## 📌 Alcance actual

Valenza es una herramienta local de **organización y seguimiento financiero**. Permite registrar compras, repartir gastos, llevar cobros y pagos, revisar efectivo y comparar tus cuentas con la información que consultas en el banco. Procesa los documentos localmente y distingue los saldos consultados, los compromisos previstos y los movimientos registrados para que puedas entender y comprobar tus cuentas.

<div align="center">

---

### VALENZA

**Tus compras. Tus cuentas. Cada centavo en su lugar.**

<sub>Aplicación de escritorio · Python · PySide6 · SQLCipher</sub>

</div>
