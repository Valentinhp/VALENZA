# Gráfica de pastel: pendientes por persona

La gráfica incluye compras normales pendientes con fecha hasta el mes seleccionado. Un cambio de mes no liquida una compra anterior. Se excluyen compras posteriores y operaciones sin fecha válida.

MSI usa exclusivamente el pendiente de las cuotas del mes seleccionado que proporciona `collection_monthly_summaries`, después de la aplicación existente de cobros. No suma principal completo ni cuotas anteriores o futuras. Un MSI sin plan o fechas suficientes genera un aviso en la descripción de la gráfica; no se trata como compra de contado.

El importe de cada participación se limita a cero antes de sumar para que un saldo a favor de un pedido no se convierta en un abono inventado a otro. No se restan pagos bancarios de cuentas familiares. No se cambian deudas, participaciones, cobros ni fórmulas financieras.

Al pasar el cursor sobre una persona se muestran los pedidos y cuotas que suman su importe. El detalle de todas las personas conserva sus cifras contables totales; la gráfica muestra la selección mensual descrita aquí. Los porcentajes usan la suma de los importes de la propia gráfica, no la deuda bancaria total.

El cálculo usa saldos conocidos actualmente. Seleccionar un mes pasado no reconstruye el saldo histórico de ese momento. Las selecciones y cantidades de simulación de la checklist no cambian los valores de la gráfica.

La implementación está en `gui/home_people_month.py`; `MainWindow._refresh_people_dashboard` la utiliza solo para presentar la gráfica. Las pruebas usan datos sintéticos cifrados y comparan importes, desglose, meses, MSI, cobros parciales, la preparación actual y ausencia de escrituras.
