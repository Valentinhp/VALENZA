# Buscador de Valenza — primera etapa

Se abre con **Ctrl+K** o con **Buscar · Ctrl+K** en la barra lateral de cualquier pantalla principal. Busca mientras escribes; Arriba/Abajo seleccionan, Enter abre, Escape cierra y también se puede abrir un resultado con clic.

| Resultados | Campos buscables | Destino |
|---|---|---|
| Pedidos | Comercio, tarjeta y descripciones vigentes de conceptos manuales o productos importados | Pedido seleccionado en Pedidos; incluye anulados |
| Compras históricas | Comercio, cuenta y descripciones de productos | Cobros, sin fingir una selección directa de la compra |
| Personas | Nombre, con coincidencias parciales y sin distinguir tildes o mayúsculas | Persona seleccionada en Usuarios |
| Tarjetas y cuentas | Nombre e institución | Cuenta seleccionada en Tarjetas |
| Pagos al banco | Cuenta, institución y referencia | Pago seleccionado en el historial de Tarjetas |
| Abonos recibidos | Persona y referencia | Abono seleccionado en el historial de Cobros |

Los resultados muestran únicamente nombre, fecha, tipo, estado y contexto descriptivo. **No muestran importes**, independientemente del estado del control de privacidad. No buscan descuentos, resultados personales ni cantidades contenidas en los repartos de los conceptos. No se guarda el historial de consultas y el texto se borra al cerrar.

La búsqueda usa el repositorio y la conexión cifrada existentes. No crea tablas, índices persistentes, archivos de datos ni otra fuente de información. Las consultas son SELECT y reutilizan los destinos existentes de la aplicación. No se añadieron dependencias.

Para evitar trabajo por cada tecla: mínimo dos caracteres, espera de 180 ms, hasta cinco términos, hasta cinco resultados por tipo y un máximo de treinta resultados. Se aplica un presupuesto de ejecución de 180 ms mediante el manejador de progreso de SQLite, que se retira al terminar. Si se agota, se conservan las coincidencias ya obtenidas y se pide una consulta más específica. No se hacen recuentos completos para mostrar resultados.

## Validación

**23 pruebas aprobadas**: doce de búsqueda, nueve de la fórmula restaurada de Inicio y dos de privacidad/comparación. Las pruebas con datos usan exclusivamente bases sintéticas cifradas.

Se comprobaron las siete pantallas principales, botón y atajo, espera al escribir, tildes/mayúsculas, consultas parciales y por varios términos, conceptos vigentes e importados, límites con 1,500 personas, interrupción por presupuesto y retirada de su manejador, consultas sin coincidencias, caracteres especiales y consultas parametrizadas.

Se verificaron clic, teclado, cambio rápido de consulta, borrado al cerrar, privacidad activada/desactivada, navegación a los identificadores correctos, pedidos anulados, registros inexistentes y la apertura honesta de Cobros para compras históricas.

Las instantáneas de tablas e historial y los contadores de cambios permanecen iguales antes y después de buscar y navegar. La traza de búsqueda contiene seis SELECT/WITH y ninguna escritura. La fórmula mensual restaurada y las reglas financieras permanecen intactas.

Capturas sintéticas: `artifacts/search/results.png` y `artifacts/search/empty.png`.

## Archivos de esta etapa

- `src/valenza/gui/app.py`: botón, atajo y navegación a vistas existentes.
- `src/valenza/gui/search.py`: ventana y controles de búsqueda.
- `src/valenza/persistence/repository.py`: método de entrada a la búsqueda.
- `src/valenza/persistence/search.py`: consultas acotadas, de solo lectura.
- `tests/test_global_search.py`: validación de la primera etapa.
- `docs/BUSCADOR_ETAPA1.md`: entrega y límites.

No se implementaron línea del tiempo, fichas de personas ni otras etapas. No se abrió la base personal ni se modificaron movimientos, saldos, calendarios, conciliaciones, PDF o esquemas.
