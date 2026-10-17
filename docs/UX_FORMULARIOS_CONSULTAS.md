# UX bloque 3: formularios y consultas

Cambios de presentación sobre los controles y servicios existentes. No se implementan nuevas rutas,
asistentes, pasos de confirmación, reglas de reparto ni operaciones financieras.

## Inventario de capacidades conservadas

| Área | Controles y opciones comprobados antes de reorganizar | Cambio de presentación |
| --- | --- | --- |
| Gasto manual | Comercio, fecha de compra, institución, cuenta, contado/MSI; base total o por mensualidad, plazo, primer vencimiento e intereses; conceptos, reparto, cargo, descuento y corrección auditada. | Datos y modalidad en un único grupo; campos obligatorios identificados; conceptos más cerca del inicio; acceso Resumen al desglose existente sin guardar. |
| Conceptos y participaciones | Agregar/quitar conceptos, responsable individual, Dividir, importes por persona, propietario, suma distribuida, pendiente de asignar y resumen previo al guardado. | Etiquetas y nombres accesibles en el componente compartido; propietario y MXN explícitos; etiquetas que se actualizan sin sustituir importes capturados. |
| Pedidos | Activos/anulados/todos, nueve columnas originales, selección, edición, devolución, recompra, MSI, anulación y detalle. | Estado vacío del filtro; Tab sale de la tabla para llegar a las acciones; las flechas siguen consultando registros. |
| Cobro individual | Participación, deuda, persona, importe, referencia y fecha; extras, comisiones, historial, edición y anulación. | Sección identificada como Abono individual y estado vacío del filtro. Se conserva el detalle de persona/pedido junto al registro. |
| Cobro global | Persona, importe, fecha, referencia, futuros y sin fecha; liquidación actual/total, revisión y edición de aplicaciones. | Etiquetas específicas de abono global; revisión distingue pendiente anterior, importe que puede cubrirse, aplicación y pendiente posterior. Fecha natural solo de presentación. |
| Personas | Crear, editar, propietario con confirmación, desactivar/reactivar, selección y tabla con historial intacto. | Nombre obligatorio identificado y tabla accesible por teclado; no se agregan fichas de persona. |
| Tarjetas y consultas | Cuentas, importes, previsiones, movimientos, pagos, aplicaciones, calendarios, comparación, líneas, administración y columnas avanzadas. | Ancho del nombre de la cuenta ajustado al contenido; Tab hacia acciones; mismos identificadores, columnas, valores y desgloses. |
| MSI de pedido existente | Vincular plan, tabla de cuotas, corrección de fecha y ajustes de previsión con motivo. | Fecha legible y natural mediante el delegado de fechas existente; todos los guardados inmediatos y avisos del bloque 2 se conservan. |
| Suscripciones | Nombre, importe, próxima fecha, cuenta, todos los responsables, recargos, edición, estados y cargo/vínculo real. | Campos obligatorios y fecha prevista identificados; nombre de servicio/cuenta legible en la tabla. |
| Importación | Todos los campos extraídos, revisión, evidencia y detalles, productos, asignación masiva, reparto individual/compartido, devoluciones y validaciones. | Acciones de asignación/productos se acomodan en varias filas cuando falta ancho; nombres accesibles. No se cambia extracción, revisión obligatoria ni guardado. |
| Devoluciones y recompras | Importe, estado, destino, acreditación, responsables, recompra, fecha, cuenta, sobrante y corrección de reparto. | Nombres accesibles; se reutiliza el mismo componente de reparto y su formulario adaptable. Se conserva el resumen financiero y las confirmaciones. |

Los cambios de estructura se limitan al acomodo de los mismos widgets dentro de la misma ventana.
No se destruyen ni reemplazan controles al redimensionar o actualizar etiquetas. Se conserva el
orden de captura y guardado, junto con borradores y acciones del bloque 2. Los contenedores Qt
reciben sus padres antes de reorganizar controles, conforme a la regresión de estabilidad.

## Validación y límites

- `test_ux_block3.py`: seis capturas completas de contado/MSI con bases total/por cuota y repartos
  individuales/compartidos; identidad y conservación de campos; resumen sin escrituras;
  teclado, filtros, estados vacíos, cobros individuales/globales, importación y numerosos registros.
- Bases exclusivamente sintéticas cifradas; comparación de tablas antes/después de consultas y
  previsualizaciones. Los guardados se contrastan con importes, participaciones y cuotas esperados.
- Se mantienen regresiones de los bloques 1/2, Inicio, privacidad y ciclo de vida Qt.
- Las tablas conservan desplazamiento horizontal cuando sus columnas no caben. No se eliminan
  columnas para forzar el ajuste a una ventana pequeña.
- Los calendarios financieros y las fechas persistidas no se reinterpretan: los delegados solo
  cambian el texto visible de fechas ya registradas.

Una evaluación con personas nuevas y una revisión completa con lector de pantalla siguen siendo
necesarias para certificar facilidad de aprendizaje y accesibilidad integral. No se hacen esas
afirmaciones basándose únicamente en las pruebas automatizadas.

No se implementan rediseños de devoluciones/Wallet, nuevas rutas de navegación, acceso al editor
histórico ni otros trabajos del bloque 4. Esas propuestas requieren autorización posterior.
