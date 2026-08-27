# Integración backend/frontend en tiempo real

Estado: aprobado para pasar a plan de implementación (fase 1).
Rama de trabajo: `john-frontend`, creada desde `john-branch` en `6ffe399`.

## 1. Resumen

- Crear rama `john-frontend` a partir de `john-branch` en `6ffe399` (idéntica hoy a `origin/john-branch`).
- Reutilizar selectivamente los componentes visuales de `frontend-branch` (`bebe6a5`), cuyos tests, typecheck y build pasan — verificado el 2026-08-27 (typecheck limpio, 3/3 tests, build de producción sin errores). No reutilizar su WebSocket en memoria, datos simulados (`useRunSimulation`, `src/data/scenario.ts`) ni el acoplamiento con `sample_app`.
- Mantener Langfuse como observabilidad paralela y enlace de detalle, no como fuente del estado operativo: sus APIs son de consulta y la disponibilidad puede demorarse 15–30 segundos. ([Langfuse Query API](https://langfuse.com/docs/api-and-data-platform/features/query-via-sdk))
- Arquitectura aprobada:

```text
React/Vite ── REST + SSE ── FastAPI
                              ├─ SQLite/WAL + cola serial
                              ├─ executor dedicado
                              ├─ artifact store local
                              ├─ outbox → Kafka KRaft
                              └─ proyector Kafka → SQLite + SSE
                                         │
                                      LangGraph
                                         └─ Langfuse
```

- SSE usará identificadores y reconexión automática; Kafka conservará orden por partición y entrega al menos una vez. ([SSE](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events), [Kafka delivery semantics](https://kafka.apache.org/41/design/design/))

## 2. Interfaces públicas y contratos

Endpoints nuevos:

```text
GET  /api/health
GET  /api/projects/recent
POST /api/projects/resolve
POST /api/projects/{project_id}/preflight
POST /api/runs
GET  /api/runs/{run_id}
GET  /api/runs/{run_id}/events
GET  /api/runs/{run_id}/events/{seq}/detail
POST /api/runs/{run_id}/decisions
GET  /api/runs/{run_id}/debrief
POST /api/runs/{run_id}/apply-intents
POST /api/runs/{run_id}/apply
```

- `POST /api/runs` acepta `project_id`, `specification`, `test_specification` y `execution_mode: DRY_RUN | STAGED_WRITE`; devuelve `202`, `run_id` y posición en cola.
- Estado separado en tres dimensiones:
  - `phase`: `QUEUED | PREFLIGHT | RUNNING | WAITING_HUMAN | FINALIZING | COMPLETED | FAILED | INTERRUPTED`.
  - `outcome`: `APPROVED | HUMAN_REVIEW_REQUIRED | TERMINATED | FAILED | null`.
  - `apply_status`: `NOT_ELIGIBLE | READY | APPLYING | APPLIED | CONFLICT | APPLY_FAILED`.
- `RunEventV1` contiene `schema_version`, `event_id`, `run_id`, `seq`, `trace_id`, `kind`, timestamp, agente, iteración, estado, resumen, métricas y `payload_ref`.
- Cobertura de eventos: corrida, agentes, modelos, fallback, RAG, MCP, rutas, iteraciones, archivos propuestos, Reviewer, HITL, errores, reporte final y Apply.
- Decisiones HITL únicamente `RESUME` y `TERMINATE`, con `checkpoint_version` e idempotencia.
- Tipos TypeScript generados desde OpenAPI; todo evento Kafka validado con Pydantic.

## 3. Cambios de implementación

### 3.1 Ejecución aislada y eventos

- Extraer la composición reutilizable de [`apply_run.py:41`](../../../src/engineering_team/apply_run.py) (`run_on_project`), conservando el comportamiento público del CLI `run-project`.
- Crear un executor para la API que copie el proyecto sin `.git`, `.env`, entornos, cachés ni symlinks externos, y guarde fingerprint y hashes iniciales.
- Ejecutar ambos modos (`DRY_RUN`, `STAGED_WRITE`) con escritura habilitada exclusivamente dentro del workspace aislado, permitiendo que Security, Testing y Reviewer evalúen los cambios completos.
- Añadir un `RunEventSink` al grafo, modelos, RAG y MCP. Usar `graph.stream()` y eventos explícitos de inicio/fin; no inferir el estado consultando Langfuse. ([LangGraph streaming](https://docs.langchain.com/oss/python/langgraph/streaming))
- Mantener la traza existente de [`langfuse.py:34`](../../../src/engineering_team/observability/langfuse.py) (`TraceSession`) y obtener el enlace mediante `get_trace_url()`. ([Langfuse trace URLs](https://langfuse.com/docs/observability/features/url))

### 3.2 Persistencia, Kafka y API

- Módulos separados para contratos, SQLite, artifacts, Kafka, scheduler, staging/Apply y FastAPI.
- SQLite/WAL con tablas `projects`, `runs`, `event_outbox`, `run_events`, `event_payloads`, `apply_intents` y control de versión.
- Insertar `seq` y outbox en una transacción. Publicar a `engineering.run-events.v1`, clave `run_id`, seis particiones; mensajes inválidos van a `engineering.run-dlq.v1`.
- Productor idempotente con `acks=all`; el grupo `engineering-ui-projector-v1` confirma offsets después del commit SQLite y deduplica por `(run_id, seq)`.
- Una corrida a la vez en un hilo dedicado; las restantes quedan en SQLite como `QUEUED`.
- Al reiniciar: reprocesar cola y outbox, pero marcar `RUNNING`/`WAITING_HUMAN` como `INTERRUPTED`.
- Servir el build del frontend desde FastAPI, un único origen. SSE reproduce desde `Last-Event-ID`, luego continúa en vivo con heartbeat.
- Extra de dependencias `ui` con FastAPI, Uvicorn y `confluent-kafka`; elevar LangGraph a `>=1.1,<2` y Langfuse a `>=4.7,<5`.

### 3.3 Frontend

- Portar las pantallas Launch, Mission Control y Debrief desde `frontend-branch`; traducir toda la interfaz al español.
- Sustituir `useRunSimulation` y el WebSocket simulado por cliente REST, reducer de eventos y `EventSource`.
- Launch: ruta, recientes, requerimientos, pruebas, modo y preflight real.
- Mission Control: grafo/timeline, reconexión, métricas y drawer de prompts/respuestas/herramientas cargado bajo demanda.
- HITL: panel persistente con evidencia y acciones Continuar/Terminar.
- Debrief: diff, scorecard, decisiones, pruebas, RAG/MCP, modelos, errores y enlace Langfuse.
- `Replay` solo reanima eventos guardados. `Nueva corrida` conserva proyecto/textos y vuelve a `DRY_RUN`.

### 3.4 Apply y seguridad

- `DRY_RUN` nunca es aplicable. `STAGED_WRITE` solo habilita Apply con resultado `APPROVED`.
- Apply en dos pasos, con token corto ligado a `run_id`, ruta canónica y fingerprint.
- Cualquier cambio en el original devuelve `409 CONFLICT` sin tocar archivos.
- Aplicar mediante archivos temporales, reemplazo atómico y rollback; cambios sin commit.
- Escuchar únicamente en `127.0.0.1`, sin CORS ni acceso LAN en v1.
- Restringir proyectos mediante `ENGINEERING_TEAM_PROJECT_ROOTS`; rechazar root, home, escapes, symlinks y rutas sensibles.
- Guardar payloads completos saneados y comprimidos con permisos `0600`; Kafka/SSE solo transporta resumen, hash y referencia.
- Eliminar eventos, payloads, diffs y debriefs terminales después de 30 días.
- Docker Compose con Apache Kafka `4.2.1` en KRaft, un broker ligado a loopback y retención de 30 días. ([Apache Kafka releases](https://kafka.apache.org/community/downloads/))

## 4. Plan de pruebas

- **Core**: ambos modos recorren el flujo completo en workspace; el original permanece intacto durante la corrida.
- **Eventos**: secuencia monotónica, redacción, detalles referenciados y cierre terminal aun ante excepciones.
- **Kafka**: orden por corrida, duplicados, outbox, caída/recuperación del broker, replay del projector y DLQ usando Kafka real en Docker.
- **API/SSE**: validación de rutas, cola serial, snapshots, `Last-Event-ID`, recarga, reinicio, HITL idempotente y estados 404/409.
- **Apply**: aprobación requerida, dry run bloqueado, conflicto concurrente, rollback y archivos sin commit.
- **Frontend**: formularios, preflight, reducer, reconexión, payload drawer, HITL, debrief, Replay sin nueva ejecución y Apply.
- **E2E**: flujo Launch → Mission → Debrief con modelos/MCP simulados; smoke separado y opcional con Ollama y Langfuse reales.
- Ejecutar finalmente la suite Python existente, tests API/Kafka, lint, typecheck y build del frontend.

## 5. Supuestos fijados

- Aplicación local para un operador; ruta validada y proyectos recientes, sin file picker ni upload.
- Kafka transporta eventos únicamente; los comandos y HITL permanecen en FastAPI.
- Una corrida activa; no hay cancelación ni recuperación de ejecución tras reinicio en v1.
- JSON versionado sin Schema Registry.
- Prompts y respuestas completos se consultan bajo demanda, siempre con redacción de secretos.
- No se modifica la semántica pública actual del CLI `run-project`.
- No se aplican cambios automáticamente, no se sobrescriben conflictos y no se crean branches ni commits (fuera de los explícitamente pedidos por el operador).

## 6. Validación previa a la implementación (2026-08-27)

- `john-branch` en `6ffe399`: confirmado, idéntico a `origin/john-branch`.
- `frontend-branch` en `bebe6a5`: confirmado, existe como rama real; es el resultado del prompt de Magic Patterns diseñado en una sesión anterior (`package.json` → `magic-patterns-vite-template`).
- Reutilizables verificados: `frontend/src/components/{launch,mission,debrief}/*`, `frontend/src/data/agents.ts`, `frontend/src/utils/format.ts`, `frontend/src/types/mission.ts`.
- No reutilizar: `frontend/src/hooks/useRunSimulation.ts`, `frontend/src/data/scenario.ts`, `frontend/src/data/report.ts` (datos simulados y WebSocket en memoria).
- `apply_run.py:41` (`run_on_project`) y `langfuse.py:34` (`TraceSession`) confirmados como puntos de extensión correctos.
- Hallazgo nuevo: había un `frontend/dist/` sin trackear en el working tree de `john-branch` (build previo suelto) — a limpiar/ignorar al crear `john-frontend`.

## 7. Fases de implementación

1. **Ejecución aislada y eventos** (`RunEventSink`, executor de API, workspace copy) — primera fase a planear en detalle.
2. **Persistencia, Kafka y API** (SQLite/WAL, outbox, projector, endpoints FastAPI).
3. **Frontend** (port de componentes, cliente REST/SSE, traducción a español).
4. **Apply y seguridad** (staging de dos pasos, Docker Compose de Kafka, límites de proyecto).

Cada fase se planea y ejecuta por separado vía `superpowers:writing-plans` → `superpowers:executing-plans`/`dispatching-parallel-agents`, con la suite de pruebas correspondiente pasando antes de avanzar a la siguiente.
