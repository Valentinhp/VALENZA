# Privacidad y comprobación de saldo

Inicio oculta descuentos y resultado personal por defecto. El ojo controla ambos
importes y el desglose; la comparación personal que permite deducir descuentos
también queda oculta. El estado solo vive en memoria de la ventana. Los PDF
conservan sus importes y presentación.

Comprobar mi saldo muestra primero la previsión mensual por periodo y permite
identificar el concepto del banco. La deuda total es una opción secundaria.
Fecha automática al guardar; fecha manual en Opciones avanzadas. Desglose,
historial y líneas compartidas siguen disponibles. Las advertencias del alcance
permanecen visibles. El pago mínimo y el pago para no generar intereses no se
declaran comparables con una previsión de cuotas.

Las nuevas fotografías solo admiten diferencia comparable para deuda TOTAL,
alcance fiable y consulta con hora dentro de cinco minutos del registro.
Una consulta antigua, sin hora o de otro tipo se guarda como referencia sin
confirmar coincidencia. No se reescriben ni reinterpretan fotografías previas.
No se alteran movimientos ni fórmulas de deuda. El diagnóstico y la corrección
de la proyección mensual se documentan en PERIODOS_Y_COMPARACION_BANCARIA.md.

Validación: bases sintéticas SQLCipher, privacidad al abrir detalle y refrescar,
activación con teclado, coincidencia y diferencias en ambas direcciones,
otro tipo de saldo, fecha antigua e historial inmutable.
