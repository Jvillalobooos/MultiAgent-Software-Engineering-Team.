# Propuesta de migración incremental — frontend-branch

Estado: diseño aprobado por el usuario el 2026-08-27; implementación incremental en preparación.

## 1. Punto de partida comprobado

- Rama actual: `frontend-branch`.
- Commit de partida: `e45f1b548498efd509ce1c1ed86681ff5d6e390b`.
- HEAD, rama local y referencia local `origin/frontend-branch` coincidían. No se hizo fetch, checkout, reset ni commit.
- El árbol estaba limpio antes de esta propuesta. El último commit añade únicamente `.claude/launch.json`; los commits anteriores contienen el chat, la persistencia, el apply seguro y sus correcciones.
- Se leyó íntegramente el [objetivo original](/Users/johnbenjamincastrosanabria/.codex/attachments/29128cfc-ddfd-4a07-aab3-1e68704fa673/goal-objective.md).

Hallazgo principal: **LangGraph, MCP y Langfuse ya están integrados en el recorrido real de la API.** No hay que reemplazarlos por otro motor. La migración principal consiste en cambiar persistencia y transporte, separar responsabilidades y completar el contrato público.

Recorrido existente: `RunManager._execute_real_run` → `execute_on_project` → `build_engineering_graph(...).stream(...)`, con `MCPRepositoryClient`, `MCPQualityClient`, runtime LLM y adaptador Langfuse. Evidencia: [run_api.py:214](/Users/johnbenjamincastrosanabria/Developer/MultiAgent-Software-Engineering-Team./src/engineering_team/run_api.py:214), [apply_run.py:43](/Users/johnbenjamincastrosanabria/Developer/MultiAgent-Software-Engineering-Team./src/engineering_team/apply_run.py:43), [stategraph.py:117](/Users/johnbenjamincastrosanabria/Developer/MultiAgent-Software-Engineering-Team./src/engineering_team/graph/stategraph.py:117).

## 2. Reutilización y reemplazos concretos

| Pieza existente | Decisión |
| --- | --- |
| [ChatWorkspace](/Users/johnbenjamincastrosanabria/Developer/MultiAgent-Software-Engineering-Team./frontend/src/components/chat/ChatWorkspace.tsx), [ChatComposer](/Users/johnbenjamincastrosanabria/Developer/MultiAgent-Software-Engineering-Team./frontend/src/components/chat/ChatComposer.tsx) | Conservar estructura, composición y flujo chat-first. |
| [RunCard](/Users/johnbenjamincastrosanabria/Developer/MultiAgent-Software-Engineering-Team./frontend/src/components/chat/RunCard.tsx) | Conservar componente; consumir capacidades y progreso autoritativos del backend. |
| [AgentGraph](/Users/johnbenjamincastrosanabria/Developer/MultiAgent-Software-Engineering-Team./frontend/src/components/mission/AgentGraph.tsx), [ActionTicker](/Users/johnbenjamincastrosanabria/Developer/MultiAgent-Software-Engineering-Team./frontend/src/components/mission/ActionTicker.tsx) | Conservar visualización; conectar inicio/fin de agentes, transiciones y herramientas reales. |
| [MissionDebrief](/Users/johnbenjamincastrosanabria/Developer/MultiAgent-Software-Engineering-Team./frontend/src/components/debrief/MissionDebrief.tsx), [DiffViewer](/Users/johnbenjamincastrosanabria/Developer/MultiAgent-Software-Engineering-Team./frontend/src/components/debrief/DiffViewer.tsx) | Conservar; manejar diff vacío y distinguir cambios en workspace de cambios aplicados al origen. |
| [EvidenceTabs](/Users/johnbenjamincastrosanabria/Developer/MultiAgent-Software-Engineering-Team./frontend/src/components/debrief/EvidenceTabs.tsx), [DecisionTimeline](/Users/johnbenjamincastrosanabria/Developer/MultiAgent-Software-Engineering-Team./frontend/src/components/debrief/DecisionTimeline.tsx) | Reutilizar, sin implementar decisiones de negocio en React. |
| [usePersistentRun](/Users/johnbenjamincastrosanabria/Developer/MultiAgent-Software-Engineering-Team./frontend/src/hooks/usePersistentRun.ts) | Mantener deduplicación, snapshots, reconexión y recuperación. Solo ajustes demostrados por tests. |
| [RunClient](/Users/johnbenjamincastrosanabria/Developer/MultiAgent-Software-Engineering-Team./frontend/src/api/runClient.ts), [tipos de dominio](/Users/johnbenjamincastrosanabria/Developer/MultiAgent-Software-Engineering-Team./frontend/src/types/mission.ts) | Conservar abstracción; sustituir transporte dentro de `subscribe` y completar validación anidada. |
| [RunStore](/Users/johnbenjamincastrosanabria/Developer/MultiAgent-Software-Engineering-Team./src/engineering_team/runs/store.py) | Sustituir implementación JSON por SQLite en el mismo servicio, no crear un segundo store activo. |
| [RunManager y router](/Users/johnbenjamincastrosanabria/Developer/MultiAgent-Software-Engineering-Team./src/engineering_team/run_api.py) | Extraer la clase existente a orquestación; dejar HTTP/SSE en el router. |
| [ApplyService](/Users/johnbenjamincastrosanabria/Developer/MultiAgent-Software-Engineering-Team./src/engineering_team/apply_service.py), [workspace](/Users/johnbenjamincastrosanabria/Developer/MultiAgent-Software-Engineering-Team./src/engineering_team/workspace/isolation.py) | Conservar y reforzar invariantes mediante tests de fallos, sin una segunda implementación. |
| [MCP existente](/Users/johnbenjamincastrosanabria/Developer/MultiAgent-Software-Engineering-Team./src/engineering_team/mcp/server.py), [Langfuse existente](/Users/johnbenjamincastrosanabria/Developer/MultiAgent-Software-Engineering-Team./src/engineering_team/observability/langfuse.py) | Reutilizar clientes, servidor y SDK; completar eventos, correlación y aislamiento de fallos. |

Se mantiene el paquete `src/engineering_team`; no se crea un árbol `backend/` paralelo. Los únicos módulos nuevos de aplicación serían la composición FastAPI oficial y la extracción del orquestador, moviendo responsabilidades existentes. `runs`, `workspace`, `graph`, `agents`, `mcp`, `llm` y `observability` continúan siendo los módulos de referencia.

La aplicación oficial dejará de depender del host [Sample Bank App](/Users/johnbenjamincastrosanabria/Developer/MultiAgent-Software-Engineering-Team./sample_app/app/main.py:8). El ejemplo bancario conservará exclusivamente su responsabilidad de ejemplo; no quedarán dos backends de runs.

## 3. Decisiones propuestas

### Persistencia

Recomiendo SQLite con `sqlite3` estándar detrás de `RunStore`. La alternativa, un ORM, mantiene la misma arquitectura pero añade dependencia y superficie de migración sin una necesidad actual demostrada. No se introduce ahora.

Se preservan las operaciones conceptuales actuales: `create`, `load`, `list_summaries`, `transition`, `append_event`, `record_source_hashes`, `record_apply_result`, `events_after`, `finish` y `wait_after`. Los snapshots devueltos siguen siendo copias independientes y los eventos se consultan con `sequence > cursor`.

- Una base local, versionada; tablas para runs, eventos, reportes y resultados/intentos de apply. JSON dentro de columnas SQLite puede representar payloads tipados, pero no será otro mecanismo de persistencia.
- Clave única `(run_id, sequence)`. Secuencia e identidad del evento se asignan una sola vez al persistir; se elimina el contador independiente del adaptador.
- Transacciones para evento + actualización del run, cierre + reporte + paths, y fase de apply + resultado. Lecturas coherentes de snapshot.
- Transiciones con precondición de fase para impedir dos applies simultáneos del mismo run. Serialización por proyecto para apply/restore.
- Importador explícito, validado y transaccional de los snapshots JSON existentes, preservando IDs, secuencias, fechas y referencias a workspaces/backups. Comparación de equivalencia antes de activar SQLite. Los originales quedan como respaldo offline; no se borran automáticamente, no hay dual-write ni fallback JSON de producción.
- Los archivos de workspace y backup siguen siendo artefactos del filesystem. Las trazas offline siguen siendo observabilidad, nunca fuente de reconstrucción del run.

El runtime inspeccionado usa SQLite **3.50.4**. La primera implementación usará rollback journal y transacciones cortas con espera acotada de locks. No habilitará WAL automáticamente: la documentación oficial describe una carrera corregida en 3.51.3 y backports específicos, incluido 3.50.7. WAL podrá evaluarse después con un runtime corregido; no hace falta actualizar todo el entorno para esta migración. [SQLite: WAL-reset bug](https://sqlite.org/wal.html#walresetbug), [SQLite: transacciones](https://sqlite.org/lang_transaction.html).

### Contrato y estado

Se conservan `RunPhase`, `RunSnapshot`, `StoredEvent`, `FinalReport`, `ApplyResult` y las operaciones de `RunClient`. Los nueve estados solicitados ya existen. Se documentan sus transiciones y quién las puede iniciar.

La frontera HTTP será la siguiente, conservando los bodies existentes:

| Endpoint | Contrato |
| --- | --- |
| `POST /api/projects/pick` | Selección/cancelación local; devuelve referencia canonical del proyecto. |
| `POST /api/runs` | `{projectPath, message}` → 202 con `run_id`; snapshot queued durable antes de ejecutar. |
| `GET /api/runs` | Lista de resúmenes persistidos. |
| `GET /api/runs/{runId}` | Snapshot público; no expone hashes internos del source ni secretos. |
| `GET /api/runs/{runId}/events` | Eventos posteriores a `after`, ordenados por secuencia. |
| `GET /api/runs/{runId}/stream` | SSE con replay, snapshot y cursor durable. |
| `POST /api/runs/{runId}/apply` | `{projectPath, confirmed: true}`; fase, contenido aprobado y conflictos revalidados por backend. |
| `POST /api/runs/{runId}/restore` | `{confirmed: true}`; backup y hashes revalidados por backend. |

El contrato mantiene campos existentes y añade explícitamente lo que hoy falta:

- Identidad del run y del evento, secuencia, tipo, timestamp `at` en milisegundos Unix, agente, iteration, status, metadata segura y payload validado. `created_at`/`updated_at` conservan representación ISO 8601 UTC.
- Capacidades del backend para mostrar/habilitar apply y restore. Los endpoints siempre revalidan; una capacidad no garantiza que un conflicto no haya aparecido después del snapshot.
- Proyección pública del progreso: agente activo, transiciones y actividad de herramientas. No contiene objetos, checkpoints ni nodos internos de LangGraph.
- Reporte tipado y diff material obtenido de evidencia del workspace/MCP; los paths autorizados siguen proviniendo de escrituras MCP comprobadas, nunca de afirmaciones del modelo.
- Separación explícita entre cambios en la copia y cambios aplicados al proyecto original.

Los guards actuales no validan completamente payloads de eventos ni elementos del reporte. Se amplían en el mismo `runClient.ts`, con `unknown`, comprobaciones anidadas y tests de rechazo; no se introduce `any` para silenciar incompatibilidades. Los componentes reciben únicamente datos validados.

Los cambios aditivos del contrato público no invalidarán silenciosamente snapshots antiguos. La proyección del backend y el importador versionado reconstruirán campos de identidad/progreso solo cuando exista evidencia; no inventarán éxitos de herramientas o aprobaciones para completar datos históricos.

### SSE

`GET /api/runs/{runId}/stream` reemplaza `/ws/runs/{runId}`. `subscribe` conserva su interfaz para que el hook siga desacoplado del transporte.

- Frames SSE de evento y snapshot, `id` basado en secuencia persistida, `text/event-stream`, sin buffering y con heartbeat.
- Cursor inicial `after` y soporte de `Last-Event-ID`. Si el encabezado válido existe, tiene precedencia para reanudación; de lo contrario se usa `after`. Cursores inválidos se rechazan antes de iniciar el stream.
- Replay duradero seguido de eventos nuevos, verificación de identidad y deduplicación por secuencia. Un hueco dispara recuperación por snapshot, no inferencias de éxito.
- Se conserva un solo responsable de reconexión: el hook existente. `RunClient` cierra `EventSource` al notificar error/cierre para evitar competir con su reconexión automática.
- Al terminar un run se envían todos los eventos persistidos y el snapshot final antes de cerrar, incluyendo la carrera entre replay y transición terminal.
- Desconectar el navegador no cancela ni elimina el run. Se comprueba recuperación al recargar y al reiniciar la API.

La semántica de `Last-Event-ID`, reconexión y `close()` se basa en el [estándar SSE de WHATWG](https://html.spec.whatwg.org/multipage/server-sent-events.html).

### Aprobación, restore y recuperación

Para conservar el flujo actual, **aprobación técnica** significa review aprobado por el backend; **consentimiento humano** sigue siendo la confirmación explícita `confirmed: true` al aplicar. No se añade un endpoint `/approve` ni se convierte automáticamente `review_required` en `approved`. Si se desea adjudicación humana independiente, deberá tratarse como una ampliación explícita, no introducirse silenciosamente en esta migración.

Propongo permitir el restore explícito también después de `applied`, cuando exista backup válido y el origen siga coincidiendo con los hashes posteriores al apply. Hoy está limitado a `apply_failed`. Se reutilizan servicio, endpoint y botón existentes; la capacidad viene del backend. Nunca se sobrescriben ediciones posteriores del usuario.

Reload del navegador recupera snapshot y eventos. Reiniciar el proceso conserva la semántica actual: runs interrumpidos se reconcilian a un fallo consultable; applies incompletos se reconcilian con evidencia de backup. SQLite **no implica reanudar automáticamente una ejecución LangGraph interrumpida**. No se añade otro checkpoint store ni se promete esa funcionalidad.

### LangGraph, MCP y Langfuse

El mismo grafo sigue ejecutando Product → Architecture → Developer → Security → Testing → Reviewer, con las rutas existentes. Se instrumentan inicio y fin de agentes/tools/LLM, iteration, warnings, pruebas, review y resultado final. Hoy varias observaciones se emiten al terminar, lo que limita mostrar una operación larga mientras está activa.

Los agentes conservan sus clientes MCP existentes para listar, leer, buscar, escribir y ejecutar verificaciones. La preparación del workspace y apply/restore siguen siendo servicios de infraestructura del backend; no se trasladan al frontend ni se confían al modelo.

La publicación de eventos de dominio no dependerá del éxito del SDK de observabilidad. Se reutiliza el adaptador Langfuse como sink tolerante a fallos, correlacionando `run_id`, `trace_id`, `event_id`, agente, iteration, provider/model, retries y latencia real. Ninguna llamada a Langfuse desde React y ninguna credencial o payload sensible en la API.

## 4. Riesgos concretos que las fases deben cubrir

| Evidencia actual | Tratamiento acotado |
| --- | --- |
| `run_event_from_trace` conserva metadata con una clave sensible si su valor no coincide con los patrones de texto. Confirmado con un valor sintético, sin usar secretos reales. | Sanitización por nombre y valor en la frontera pública, antes de persistir/publicar; tests de metadata anidada y errores. |
| [DiffViewer:113](/Users/johnbenjamincastrosanabria/Developer/MultiAgent-Software-Engineering-Team./frontend/src/components/debrief/DiffViewer.tsx:113) puede seleccionar `undefined` para `files=[]` y después acceder a `file.lines`. | Test de reporte sin cambios y estado vacío dentro del mismo componente. |
| [project_picker.py:20](/Users/johnbenjamincastrosanabria/Developer/MultiAgent-Software-Engineering-Team./src/engineering_team/project_picker.py:20) rechaza macOS; el header no ofrece otro selector. Confirmado sin abrir diálogo. | Adaptar el selector existente por plataforma, preservando `FolderPicker`, el endpoint y la UI. Mantener soporte Windows y restricción local. |
| El manifiesto de backup se escribe después del bucle de escrituras; una caída intermedia requiere mejor evidencia durable. | Journal de intención/backup antes de mutar origen, pruebas de interrupción y reconciliación. SQLite no hace transaccionales las escrituras de archivos. |
| Las excepciones de verificación, cambios de workspace tras review y symlinks requieren cobertura dirigida antes del cambio. | Reproducir con tests; garantizar fallo estructurado, hashes del contenido aprobado y validación de cada path/segmento. No relajar los controles existentes. |
| El host actual crea estado de runs durante importación del módulo API. | Inicialización y recuperación en lifespan, con dependencias explícitas y sin escrituras al importar. |

Son ajustes necesarios para el contrato, la seguridad y el criterio de éxito; no autorizan un rediseño visual ni una limpieza indiscriminada del repositorio.

## 5. Fases y puertas de verificación

Cada fase deja el proyecto ejecutable. Dentro de una fase: prueba que demuestra la necesidad, cambio mínimo, pruebas relevantes y revisión independiente. No se ejecutan varias implementaciones sobre los mismos archivos en paralelo.

| Fase del objetivo | Entrega concreta | Condición para avanzar |
| --- | --- | --- |
| 1. Identificar reutilización | Inventario de esta propuesta, commit base y línea de pruebas. | Límites y componentes preservados identificados. |
| 2. Congelar dominio | Documentar REST/eventos/estados; completar modelos y guards existentes; fijar capacidades, consentimiento y semántica de diff/restore. | Contract tests positivos y negativos; tests frontend conservados; sin reglas de éxito duplicadas. |
| 3. SQLite | Reemplazar `runs/store.py`; esquema versionado, importador único, transacciones y recuperación. | Equivalencia de snapshots/importación; secuencias concurrentes; rollback ante error; reapertura desde otro proceso. |
| 4. API/orquestación | Extraer `RunManager`; host FastAPI oficial; routers finos; lifespan; reutilizar servicios; adaptar selector macOS. Actualizar dependencias de backend y launch config. | Mismo REST y mismo motor; no efectos al importar; API arrancable; selección/cancelación de proyecto. |
| 5. SSE | Implementar stream persistente y cambiar `HttpRunClient.subscribe`; retirar WebSocket/proxy al pasar las pruebas equivalentes. | Replay, dedup, gaps, desconexión, backoff único, carrera terminal y reload. |
| 6. LangGraph | Consolidar el grafo ya real; emitir ciclo de agentes/transiciones y proyección de estado; diff del workspace. | API → grafo real → reporte y eventos; ejecución aislada; ningún runner simulado nuevo. |
| 7. MCP | Conservar servidor/clientes; eventos de inicio/fin y tiempos reales; hashes/evidencia de writes y tests. Completar garantías apply/restore en el servicio existente. | Operaciones MCP stdio verificadas; modelo no autoriza paths; conflicto/backup/fallo/restauración seguros. |
| 8. Langfuse | Desacoplar sink de observabilidad; correlación y redacción completas; exportación sin autoridad sobre el estado. | Fallo/ausencia de Langfuse no cambia el resultado del workflow; telemetría correlacionada sin secretos públicos. |
| 9. Retirar obsoleto | Eliminar restos activos de store JSON, WebSocket y host de runs en sample_app; actualizar documentación y comandos. | Una API, un orquestador, un store, un transporte; CLI/evaluadores válidos no eliminados por parecer similares. |
| 10. Verificación integral | Unitarias, contratos, integración y E2E navegador sobre la UI existente; smoke real controlado. | Los 12 pasos del criterio de éxito tienen evidencia, incluyendo reload, pruebas, apply y restore. |

Las fases 6–8 son consolidación de integraciones existentes, no instalación de una segunda arquitectura. Los tests se actualizan en cada fase; la fase 10 es la regresión completa, no el primer momento de probar.

## 6. Validación y línea base

Comprobado antes de modificar código:

- `npm test -- --reporter=dot`, desde `frontend`: **31 pruebas pasan**, 4 archivos, exit 0.
- `npm run typecheck`, desde `frontend`: exit 0.
- `npm run build`, desde `frontend`: exit 0.
- Backend: selección de **190 pruebas** en `tests/unit`, `tests/graph`, `tests/mcp`, `tests/integration`, `tests/rag`, `tests/test_run_api.py` y `tests/e2e/test_chat_apply_flow.py`: **188 pasan y 2 fallan**, reproducido dos veces. Los fallos son `test_settings_default_to_approved_local_model_policy` y `test_retry_repair_and_cloud_escalation_budgets_are_independent`.
- Causa comprobada: el proceso padre del runner ya contiene política cloud y timeout diferentes de los defaults; el primer test observa esos valores y no hay cambios posteriores durante la suite. `Settings(_env_file=None)` sigue recibiendo esas variables de entorno. No es una regresión introducida por esta propuesta ni se atribuye a filtración durante la colección.
- Al retirar solamente seis variables de política en el proceso hijo, la misma selección da **189 pasan y 1 falla**: todavía queda el timeout heredado. Al aislar todas las variables que corresponden a campos/aliases de `Settings`, los **dos tests afectados pasan** y la selección completa posterior da **190 pasan, 1 advertencia, exit 0**. No se modificó `.env`, el entorno padre ni código de aplicación/tests para obtener esa línea base.
- El E2E actual de chat/apply usa FastAPI TestClient y un executor inyectado. Protege copia/apply/verificación, pero **no es un E2E de navegador ni prueba por sí solo el stack real completo**.
- No se ejecutaron los tres archivos E2E de evaluación/evidencia live restantes, no se lanzaron corridas live contra LLMs ni exportaciones de prueba a Langfuse. Los archivos históricos de evidencia no se presentan como verificaciones nuevas.

Comando reproducible para la selección backend, desde la raíz del repositorio:

```sh
.venv/bin/python -m pytest tests/unit tests/graph tests/mcp tests/integration tests/rag tests/test_run_api.py tests/e2e/test_chat_apply_flow.py -o addopts= -q --tb=short
```

El resultado de ese comando depende del entorno heredado. El aislamiento diagnóstico se realizó únicamente en procesos hijos, sin cambiar archivos. La advertencia restante observada corresponde a una deprecación de Chroma bajo Python 3.14.

Cobertura adicional requerida:

1. SQLite: reopen/restart, transacciones fallidas, writers concurrentes, unicidad/orden, importación idempotente y snapshots íntegros.
2. REST/SSE: datos malformados, identidad equivocada, eventos perdidos/duplicados, cursor inválido, stream terminal, desconexión durante apply y recuperación por snapshot.
3. Seguridad: source intacto antes de consentimiento, workspace distinto de source, symlinks/escapes, hashes de source y workspace aprobado, backup antes de escribir, crash entre archivos, pruebas que fallan o lanzan excepción, restore sin pisar ediciones posteriores.
4. Contrato frontend: capacidades recibidas, reporte vacío, eventos/reportes corruptos rechazados, distinguir workspace/source y preservar componentes/interacciones.
5. E2E de navegador: seleccionar proyecto de prueba, enviar tarea, observar agentes/tools, revisar diff, confirmar apply, ver tests, restaurar y recargar. Se usa un repositorio temporal; nunca se aplica una prueba sobre este repositorio de trabajo.
6. Integración determinista con LangGraph y MCP reales; dobles de LLM únicamente en tests. Smoke separado con provider/model configurado y tarea sintética, registrando qué fue realmente ejecutado y exportado.

El entorno no debe esconder fallos mediante cambios a la configuración personal. Los tests de defaults deben aislar sus fuentes de configuración; las pruebas del runtime deben declarar explícitamente la política que verifican.

## 7. Aprobación y ejecución

El usuario aprobó este diseño con «Apruebo» el 2026-08-27. La puerta de aprobación de `superpowers:brainstorming` está satisfecha; se inicia la implementación incremental.

Se prepara el plan granular de ejecución y se usa `superpowers:subagent-driven-development`: un implementador por unidad revisable, revisión de contrato/calidad, ciclos de corrección y verificación final. Se verificará el aislamiento del trabajo sin perder el commit base ni cambios del usuario. No se hará push, merge ni publicación sin autorización.

La aprobación recibida incluye cuatro decisiones visibles: mantener el consentimiento humano al aplicar (sin nueva pantalla de aprobación), habilitar restore seguro después de apply exitoso, habilitar el selector existente en macOS y comenzar SQLite sin WAL en el runtime actual.
