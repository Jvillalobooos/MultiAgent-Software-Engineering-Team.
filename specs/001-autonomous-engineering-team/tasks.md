# Tasks: Autonomous Engineering Team

**Fuentes:** `.specify/memory/constitution.md`,
`specs/001-autonomous-engineering-team/spec.md`,
`specs/001-autonomous-engineering-team/plan.md`  
**Precedencia:** Constitution > Spec > Plan > Tasks > implementación  
**Regla:** este backlog deriva de los contratos aprobados; no redefine
arquitectura, requisitos, escenarios, modelos ni políticas.

## FASE 1 — FOUNDATION

### [X] T001 — Estructura base, configuración y entrada CLI

- **Objetivo:** Crear el esqueleto del monolito modular, configuración externa,
  `.env.example` y entrada CLI sin ejecutar aún el workflow completo.
- **FR/NFR:** FR-001, FR-002, FR-046, FR-050, FR-057, FR-058; NFR-001, NFR-002,
  NFR-003, NFR-009, NFR-017.
- **Dependencias:** Ninguna.
- **Módulos/archivos:** `src/engineering_team/{__init__.py,config.py,cli.py}`,
  `.env.example`, configuración de empaquetado y `tests/unit/test_config.py`.
- **Acciones principales:** Definir carga externa de modelos, límites, timeouts,
  rutas y switches de provider; establecer cloud y gasto pagado deshabilitados
  por defecto; validar requirement CLI y asignar `run_id`.
- **Validaciones/tests:** Python 3.10+, defaults local-first, claves cloud
  ausentes, redacción de configuración y CLI inválida/válida.
- **Evidencia esperada:** Salida CLI con `run_id`, snapshot de configuración
  saneada y reporte pytest.
- **Done When:** El paquete arranca mediante CLI sin llamar LLM/cloud y toda
  configuración sensible procede externamente.

### [X] T002 — Contratos Pydantic y enums de dominio

- **Objetivo:** Implementar todos los contratos estructurados y valores
  permitidos que usarán estado, agentes, herramientas y reportes.
- **FR/NFR:** FR-009, FR-021, FR-022, FR-027, FR-029, FR-031, FR-033, FR-037,
  FR-049, FR-070; NFR-006.
- **Dependencias:** T001.
- **Módulos/archivos:** `contracts/enums.py`, `contracts/models.py`,
  `tests/unit/test_contracts.py`.
- **Acciones principales:** Definir ProductSpecification, ArchitectureProposal,
  ImplementationResult, SecurityFinding, SecurityReview, TestResult,
  ReviewerDecision, RetrievedEvidence, ToolResult, ModelExecutionInfo,
  CloudFallbackContext, WorkflowError y FinalReport con enums estrictos.
- **Validaciones/tests:** Campos obligatorios, enums/status inválidos, extras
  prohibidos, Pydantic failure y contrato completo de FinalReport.
- **Evidencia esperada:** Reporte de schemas válidos e inválidos.
- **Done When:** Ninguna salida que afecte decisiones puede existir fuera de un
  contrato Pydantic validado.

### [X] T003 [P] — Guardrails base y protección de secretos

- **Objetivo:** Establecer validación de salidas, rutas, timeouts y secretos
  reutilizable por todos los adaptadores y nodos.
- **FR/NFR:** FR-009, FR-015, FR-058, FR-059, FR-068, FR-069; NFR-011,
  NFR-012, NFR-013, NFR-014, NFR-018.
- **Dependencias:** T001, T002.
- **Módulos/archivos:** `guardrails/{validation.py,routes.py,secrets.py,timeouts.py}`,
  `tests/unit/test_guardrails.py`.
- **Acciones principales:** Implementar allowlists, validación pre-merge,
  bloqueo/redacción de secretos, límites de timeout, rutas permitidas y
  autorización explícita para operaciones destructivas.
- **Validaciones/tests:** Secret-seeding, path/ruta inválida, timeout, output
  inválido y operación destructiva denegada.
- **Evidencia esperada:** Tool/error records saneados y reporte pytest.
- **Done When:** Las políticas pueden ser invocadas sin depender de LLM, MCP o
  LangGraph.

### [X] T004 — EngineeringState, reducers y ContextEnvelope

- **Objetivo:** Implementar estado compartido, reducers y proyecciones mínimas
  de contexto sin exponer el estado completo a agentes.
- **FR/NFR:** FR-006, FR-007, FR-008, FR-016, FR-044, FR-072; NFR-006,
  NFR-010.
- **Dependencias:** T002, T003.
- **Módulos/archivos:** `contracts/state.py`, `models/context.py`,
  `tests/unit/test_state.py`, `tests/unit/test_context.py`.
- **Acciones principales:** Definir todos los campos EngineeringState,
  contadores/reducers, ContextEnvelope y builder por rol conforme a la matriz
  del Plan; registrar fingerprint de proyección.
- **Validaciones/tests:** Append/replace reducers, aislamiento de Product,
  Developer y Reviewer, contador de ciclo y rechazo de campos prohibidos.
- **Evidencia esperada:** Snapshots de estado y assertions de contexto mínimo.
- **Done When:** Cada nodo puede recibir/devolver patches validados sin mutar
  estado in place.

## FASE 2 — MULTI-MODEL LOCAL

### [X] T005 [P] — ModelRegistry y ModelRouter determinísticos

- **Objetivo:** Fijar selección local de modelo por rol desde configuración,
  sin IDs hardcodeados dentro de agentes.
- **FR/NFR:** FR-046, FR-047, FR-050; NFR-007, NFR-010.
- **Dependencias:** T001, T002.
- **Módulos/archivos:** `llm/{registry.py,router.py}`, `tests/unit/test_model_router.py`.
- **Acciones principales:** Registrar externamente `FAST_MODEL=qwen3.5:4b`,
  `DEEP_MODEL=qwen3.5:9b` y `CODING_MODEL=qwen3.5:9b`; fijar Product y
  Reviewer a DEEP/9B, Architecture y Testing a FAST/4B, Developer a
  CODING/9B y Security a DEEP/9B; validar que ningún agente selecciona modelo.
- **Validaciones/tests:** Mapeo de los seis roles, repetibilidad, configuración
  ausente e intento de selección por agente.
- **Evidencia esperada:** Registros de decisión de router con requested model y
  profile.
- **Done When:** El router es la única autoridad de modelo local y devuelve el
  mapeo aprobado `qwen3.5:4b`/`qwen3.5:9b`.

### [X] T006 — Adaptador Ollama y ModelExecutionInfo

- **Objetivo:** Integrar generación local estructurada y registrar cada intento
  de inferencia.
- **FR/NFR:** FR-048, FR-049, FR-057, FR-061, FR-063; NFR-007, NFR-014,
  NFR-015.
- **Dependencias:** T002, T005.
- **Módulos/archivos:** `llm/ollama.py`, `llm/repair.py`,
  `tests/unit/test_ollama_adapter.py`.
- **Acciones principales:** Implementar puerto común de generación,
  serialización estructurada, captura de requested/actual model, provider,
  profile, latency_ms, usage, degraded y error.
- **Validaciones/tests:** Respuesta válida, modelo local no disponible, timeout,
  usage ausente y conservación de ModelExecutionInfo.
- **Evidencia esperada:** Registros de llamadas locales validadas.
- **Done When:** Una llamada local se puede validar y observar sin cloud.

## FASE 3 — FALLBACK CLOUD

### [X] T007 — Fallback cloud, retry/repair y CloudFallbackContext

- **Objetivo:** Implementar contingencia cloud separada, acotada y saneada.
- **FR/NFR:** FR-051–059, FR-062–064, FR-068–069, FR-077; NFR-009, NFR-012,
  NFR-014, NFR-017.
- **Dependencias:** T003, T005, T006.
- **Módulos/archivos:** `llm/cloud.py`, extensiones `llm/repair.py`,
  `tests/unit/test_cloud_fallback.py`.
- **Acciones principales:** Implementar adaptadores Google/Groq: Product,
  Architecture y Reviewer → Gemini 3.7 Flash; Developer y Security → Groq
  `openai/gpt-oss-120b`; Testing → Groq `openai/gpt-oss-20b`. Construir
  CloudFallbackContext mínimo; aplicar `MAX_LOCAL_RETRIES=1` para
  disponibilidad, `MAX_LOCAL_REPAIRS=1` para calidad,
  `MAX_CLOUD_ESCALATIONS_PER_AGENT=1` y `MAX_CLOUD_ESCALATIONS_PER_RUN=3`.
- **Validaciones/tests:** Una retry por unavailable/timeout, una repair por
  schema/Pydantic failure, mapeos de providers, cloud sin claves, 429/outage,
  sanitización y ausencia de cloud por MCP_ERROR/TOOL_ERROR/RAG_ERROR.
- **Evidencia esperada:** ModelExecutionInfo con fallback y payload cloud
  redacted.
- **Done When:** Cloud solo se invoca por trigger elegible, con presupuesto y
  sin `.env`, secretos, repo completo ni EngineeringState completo.

## FASE 4 — LANGGRAPH WALKING SKELETON

### [X] T008 [P] — StateGraph mínimo verificable

- **Objetivo:** Construir un StateGraph real con nodos stub y flujo normal
  antes de conectar LLM, RAG o MCP reales.
- **FR/NFR:** FR-003–005, FR-010–013; NFR-005, NFR-010.
- **Dependencias:** T004.
- **Módulos/archivos:** `graph/{stategraph.py,nodes.py}`, `tests/graph/test_walking_skeleton.py`.
- **Acciones principales:** Definir START, seis nodos de rol, FinalReport y END
  con patches Pydantic deterministas para probar orden y terminación.
- **Validaciones/tests:** Inspección de múltiples nodos/normal edges, orden
  Product→Architecture→Developer→Security→Testing→Reviewer y APPROVED→END.
- **Evidencia esperada:** Export/inspección de grafo y trace de skeleton.
- **Done When:** No existe cadena manual de llamadas y el path normal termina
  tras FinalReport.

### [X] T009 — Routers determinísticos, remediación, HITL y errores

- **Objetivo:** Completar conditional edges y política de transición sin que un
  LLM controle rutas.
- **FR/NFR:** FR-011–020, FR-034, FR-062–069; NFR-010, NFR-014.
- **Dependencias:** T003, T004, T008.
- **Módulos/archivos:** `graph/{routers.py,hitl.py}`, actualización de
  `graph/stategraph.py`, `tests/graph/test_routers.py`.
- **Acciones principales:** Validar ReviewerDecision, categorías y return_to;
  implementar cadenas de remediación, error routes, `MAX_ITERATIONS=3`,
  CRITICAL→HITL y HUMAN_REVIEW_REQUIRED.
- **Validaciones/tests:** Rejected→remediation→Reviewer, ruta inválida,
  tercer ciclo fallido, CRITICAL pause/resume y cada familia de error.
- **Evidencia esperada:** Historial de `iteration`, decisión HITL y rutas
  deterministas.
- **Done When:** Reviewer recomienda; routers validados seleccionan toda
  transición y terminan automatización al límite.

## FASE 5 — RAG Y MCP

### [X] T010 [P] — Corpus RAG, loaders y chunking configurado

- **Objetivo:** Crear el corpus mínimo real y pipeline de ingesta con los
  parámetros congelados por el Plan.
- **FR/NFR:** FR-035–036, FR-074, FR-081; NFR-008, NFR-014.
- **Dependencias:** T001, T002.
- **Módulos/archivos:** seis documentos `knowledge/`,
  `rag/{loaders.py,chunking.py}`, `tests/rag/test_ingestion.py`.
- **Acciones principales:** Implementar loaders, token-aware recursive
  splitting, chunk_size=800, overlap=160, metadata domain/source/section/
  version/chunk_id y configuración externa correspondiente.
- **Validaciones/tests:** Inventario de seis fuentes reales, parámetros
  configurables, metadatos completos y estrategia ES/EN.
- **Evidencia esperada:** Inventario de corpus y chunks trazables.
- **Done When:** La ingesta conserva provenance y no fija valores fuera del
  Plan.

### [X] T011 — Chroma, embeddings y retrievers especializados

- **Objetivo:** Indexar corpus con Sentence Transformers/Chroma y exponer
  evidence filtrada por dominio.
- **FR/NFR:** FR-036–040, FR-066, FR-074; NFR-008.
- **Dependencias:** T010.
- **Módulos/archivos:** `rag/{index.py,retrievers.py,provenance.py}`,
  `tests/rag/test_retrievers.py`.
- **Acciones principales:** Usar `paraphrase-multilingual-MiniLM-L12-v2`,
  Chroma, top_k=4, fetch_k=8 con MMR, RAG_MIN_RELEVANCE=0.55 y filtros para
  Architecture, Security y Testing.
- **Validaciones/tests:** Provenance completo, score/relevancia, filtros de
  tres dominios, NO_RELEVANT_DOCS/RAG_ERROR y rechazo de cita inventada.
- **Evidencia esperada:** RetrievedEvidence y trace de retrieval especializado.
- **Done When:** Solo evidencia recuperada puede llegar a agentes y un no-match
  queda explícitamente registrado.

### [X] T012 — Workspace aislado y Repository MCP

- **Objetivo:** Proveer operaciones de repositorio seguras sobre una copia por
  run con permisos mínimos.
- **FR/NFR:** FR-024–027, FR-041, FR-043–044; NFR-011–013, NFR-018.
- **Dependencias:** T003, T004.
- **Módulos/archivos:** `workspace/{isolation.py,paths.py,runs.py}`,
  `mcp/{contracts.py,repository.py,permissions.py}`, `tests/mcp/test_repository.py`.
- **Acciones principales:** Crear `workspace/runs/<run_id>`, validar rutas,
  implementar list_files/read_file/search_code/get_file_content/create_file/
  update_file/get_diff y conceder escritura solo a Developer.
- **Validaciones/tests:** Path traversal, rutas externas, allowlists,
  operaciones denegadas, ToolResult y autorización destructiva.
- **Evidencia esperada:** ToolResults estructurados y diff de run aislado.
- **Done When:** Architecture solo lee cuando corresponde y Developer trabaja
  únicamente dentro de la copia aislada.

### [X] T013 — Sample app mínima y fixtures de seguridad

- **Objetivo:** Implementar la aplicación FastAPI/SQLite mínima aprobada para
  demostrar los cinco escenarios sin vulnerabilidades intencionales.
- **FR/NFR:** FR-030, FR-045, FR-071; NFR-003, NFR-016.
- **Dependencias:** T001, T012.
- **Módulos/archivos:** `sample_app/app/`, `sample_app/tests/`, fixtures de
  `evaluation/scenarios/` y `tests/integration/test_sample_app.py`.
- **Acciones principales:** Crear recuperación de contraseña single-use de 15
  minutos, bloqueo a cinco fallos y API de últimas cinco transacciones del
  usuario autorizado; representar SC-04/SC-05 como requisitos a rechazar.
- **Validaciones/tests:** Tres comportamientos seguros, ownership/IDOR y que
  no se implemente token no expirable ni acceso arbitrario.
- **Evidencia esperada:** pytest del sample app y fixtures de escenarios.
- **Done When:** Existe un objetivo aislable suficiente para evaluación sin UI
  compleja ni tecnologías adicionales.

### [X] T014 — Quality MCP y ToolResult con efecto de grafo

- **Objetivo:** Implementar calidad/seguridad operativa y propagar resultados
  reales hacia Testing, Security y Reviewer.
- **FR/NFR:** FR-042–045, FR-065, FR-067; NFR-013–014, NFR-016.
- **Dependencias:** T003, T012, T013.
- **Módulos/archivos:** `mcp/quality.py`, actualización `mcp/contracts.py`,
  `tests/mcp/test_quality.py`, `tests/integration/test_tool_result_routing.py`.
- **Acciones principales:** Añadir run_tests/get_test_results/run_build/
  get_build_status/run_linter/scan_dependencies/run_security_scan/
  get_security_report con timeouts, schemas y roles permitidos.
- **Validaciones/tests:** MCP unavailable, tool failure, permisos, resultados
  de build/lint/scan y cadena run_tests FAILED→TestResult FAIL→Reviewer
  REJECTED→remediation.
- **Evidencia esperada:** ToolResult correlacionado con state y route.
- **Done When:** Un resultado de herramienta modifica decisión LangGraph y no
  activa cloud por sí mismo.

## FASE 6 — AGENTES Y PROMPTS

### [X] T015 — Base de agentes y renderizado de prompts

- **Objetivo:** Establecer el puerto común, ContextEnvelope builder y doce
  prompt assets separados antes de agentes concretos.
- **FR/NFR:** FR-007–009, FR-043; NFR-006, NFR-012, NFR-013.
- **Dependencias:** T003, T004, T006.
- **Módulos/archivos:** `agents/base.py`, `prompts/*/{system.md,user.md}`,
  `tests/unit/test_prompt_rendering.py`.
- **Acciones principales:** Definir ejecución base, renderizar system.md con
  role/boundaries/tools/failure behavior y user.md con envelope mínimo; impedir
  historial completo y secretos.
- **Validaciones/tests:** Separación de prompts, schema context, ToolResult/RAG
  relevante, campos prohibidos y allowed tools por rol.
- **Evidencia esperada:** Metadatos de prompt redacted y snapshot de envelopes.
- **Done When:** Los seis agentes pueden heredar un contrato uniforme sin
  compartir contexto innecesario.

### [X] T016 — Product Agent

- **Objetivo:** Implementar análisis de requerimiento y ProductSpecification.
- **FR/NFR:** FR-004, FR-021, FR-023, FR-049; NFR-006, NFR-010.
- **Dependencias:** T005, T006, T015.
- **Módulos/archivos:** `agents/product.py`, `prompts/product/*`,
  `tests/unit/test_product_agent.py`.
- **Acciones principales:** Consumir requirement/envelope mínimo, usar modelo
  DEEP local y producir objetivo, actores, reglas, restricciones, AC, NFR,
  ambigüedades y supuestos.
- **Validaciones/tests:** Output Pydantic, exclusión de repo/secrets, modelo
  correcto y repair por calidad.
- **Evidencia esperada:** ProductSpecification validada y ModelExecutionInfo.
- **Done When:** Product no usa MCP ni selecciona modelo/ruta por sí mismo.

### [X] T017 — Architecture Agent

- **Objetivo:** Implementar diseño contextual con RAG especializado y lectura
  limitada del repositorio.
- **FR/NFR:** FR-022, FR-038, FR-040, FR-049; NFR-006, NFR-013.
- **Dependencias:** T006, T011, T012, T015.
- **Módulos/archivos:** `agents/architecture.py`, `prompts/architecture/*`,
  `tests/unit/test_architecture_agent.py`.
- **Acciones principales:** Combinar ProductSpecification, evidence
  architecture/API y herramientas Repository MCP read-only para producir
  ArchitectureProposal.
- **Validaciones/tests:** Provenance obligado, no write tool, 4B/FAST profile,
  NO_RELEVANT_DOCS y grounding/repair elegible.
- **Evidencia esperada:** ArchitectureProposal con citas recuperadas y lecturas
  MCP permitidas.
- **Done When:** Architecture entrega componentes/APIs/datos/riesgos sin
  implementar ni acceder a contexto prohibido.

### [X] T018 — Developer Agent

- **Objetivo:** Implementar inspección y cambio/propuesta en workspace aislado
  con evidencia de diff y validación.
- **FR/NFR:** FR-023–027, FR-043–044, FR-049; NFR-011–013.
- **Dependencias:** T006, T012, T014, T015, T017.
- **Módulos/archivos:** `agents/developer.py`, `prompts/developer/*`,
  `tests/unit/test_developer_agent.py`.
- **Acciones principales:** Consumir specification/architecture, inspeccionar
  run copy, usar Repository MCP permitido y Quality build/lint; devolver modo
  PROPOSED/APPLIED, changed_files, diff, evidence y validation_result.
- **Validaciones/tests:** Contexto real previo, escritura solo permitida,
  seguridad de ruta, perfil CODING/9B y repair de código generado incorrecto.
- **Evidencia esperada:** ToolResults, diff y ImplementationResult validado.
- **Done When:** Developer no usa cloud por MCP/filesystem failure y declara
  si cambió superficie de seguridad.

### [X] T019 — Security Agent

- **Objetivo:** Implementar revisión de seguridad completa, scans y second
  opinion cloud gobernada.
- **FR/NFR:** FR-028–029, FR-038, FR-049, FR-055–056; NFR-012–013.
- **Dependencias:** T006, T007, T011, T014, T015, T018.
- **Módulos/archivos:** `agents/security.py`, `prompts/security/*`,
  `tests/unit/test_security_agent.py`.
- **Acciones principales:** Evaluar checklist OWASP requerido, combinar
  security RAG/Quality MCP y emitir PASS/FAIL, severity, findings,
  recommendations y sources; marcar CRITICAL para HITL.
- **Validaciones/tests:** Todas las categorías, DEEP/9B, scanner/RAG conflict,
  HIGH/CRITICAL ambiguo, no write tool y cloud solo como second opinion.
- **Evidencia esperada:** SecurityReview validada, findings trazables y ruta
  CRITICAL.
- **Done When:** Security no aprueba evidencia contradictoria ni evita HITL.

### [X] T020 — Testing Agent

- **Objetivo:** Implementar evaluación de pruebas y resultados reales con
  separación de propuesta, generación, ejecución y resultado.
- **FR/NFR:** FR-030–031, FR-038, FR-045, FR-049; NFR-013, NFR-016.
- **Dependencias:** T006, T011, T014, T015, T018.
- **Módulos/archivos:** `agents/testing.py`, `prompts/testing/*`,
  `tests/unit/test_testing_agent.py`.
- **Acciones principales:** Cubrir happy/error/edge/validation/security/
  business rules, usar testing RAG y Quality MCP, y distinguir los cuatro
  conjuntos de pruebas/resultados requeridos.
- **Validaciones/tests:** FAST/4B, syntax/collection repair, bug real sin
  cloud, failed test ToolResult y evidencia de cobertura.
- **Evidencia esperada:** TestResult validado y registros de ejecución.
- **Done When:** Testing entrega resultados actuales sin convertir un bug real
  en trigger cloud.

### [X] T021 — Reviewer Agent

- **Objetivo:** Implementar evaluación final estructurada sin autoridad para
  cambiar transiciones.
- **FR/NFR:** FR-032–034, FR-049, FR-066, FR-070, FR-073; NFR-006, NFR-010.
- **Dependencias:** T006, T015, T016–T020.
- **Módulos/archivos:** `agents/reviewer.py`, `prompts/reviewer/*`,
  `tests/unit/test_reviewer_agent.py`.
- **Acciones principales:** Evaluar los ocho ejes aprobados, evidence RAG/MCP,
  score/subscores/problemas/reason/remediation_category/return_to/confidence y
  producir ReviewerDecision para validación de router.
- **Validaciones/tests:** Campos mínimos, recomendación inválida, confidence
  bajo/contradicción, DEEP/9B y cloud elegible solo por calidad.
- **Evidencia esperada:** ReviewerDecision Pydantic y matriz de evaluación.
- **Done When:** Reviewer no invoca tools ni controla edges directamente.

## FASE 7 — INTEGRACIÓN, OBSERVABILIDAD Y GUARDRAILS

### [X] T022 — Composición CLI, nodos reales y FinalReport

- **Objetivo:** Conectar adaptadores y seis agentes al StateGraph para una
  ejecución completa local-first.
- **FR/NFR:** FR-001–020, FR-060, FR-070; NFR-002, NFR-005, NFR-009, NFR-010.
- **Dependencias:** T007, T009, T011–T021.
- **Módulos/archivos:** actualización `cli.py`, `graph/nodes.py`,
  `graph/stategraph.py`, `tests/integration/test_workflow.py`.
- **Acciones principales:** Construir dependencias, reemplazar stubs por
  agentes, formar FinalReport y mantener flujo normal/loops/HITL.
- **Validaciones/tests:** Run local sin cloud, orden de seis roles, APPROVED
  termination, REJECTED remediation y FinalReport completo.
- **Evidencia esperada:** State snapshot, FinalReport y trace interno de run.
- **Done When:** El CLI ejecuta una corrida completa sin arquitectura paralela
  ni modelos/rutas elegidos por agentes.

### [X] T023 — Integración de errores y guardrails de workflow

- **Objetivo:** Validar extremo a extremo todas las rutas de fallo y controles
  de seguridad alrededor de nodos, tools, RAG y cloud.
- **FR/NFR:** FR-015, FR-051–056, FR-062–069, FR-077; NFR-011–014, NFR-018.
- **Dependencias:** T007, T009, T011, T012, T014, T022.
- **Módulos/archivos:** actualización `graph/*`, `guardrails/*`,
  `tests/integration/test_error_paths.py`.
- **Acciones principales:** Integrar clasificación WorkflowError, retry/repair,
  cloud unavailable, MCP/RAG/tool error, invalid route/output, timeout,
  sandbox/allowlists y destructive-operation gate.
- **Validaciones/tests:** Fault injection por cada error de Spec, no cloud por
  MCP/RAG/tool, counters límites, path traversal y secret protection.
- **Evidencia esperada:** Errores normalizados con route result y trace safe.
- **Done When:** Todos los fallos definidos terminan en remediación permitida o
  HUMAN_REVIEW_REQUIRED sin exposición de secretos.

### [X] T024 — Langfuse, métricas y reporte agregado

- **Objetivo:** Instrumentar evidencia end-to-end y derivar métricas reales de
  runs/evaluaciones.
- **FR/NFR:** FR-060–061, FR-075–076, FR-083–084; NFR-014–015.
- **Dependencias:** T006, T007, T011, T014, T022.
- **Módulos/archivos:** `observability/{langfuse.py,metrics.py,evaluation.py}`,
  `tests/integration/test_observability.py`.
- **Acciones principales:** Emitir root trace/spans de agentes, prompts,
  modelos, RAG, MCP, fallback, retry/repair, routes, HITL y FinalReport;
  agregar latencias, calls, usage disponible, outcomes y errores por tipo.
- **Validaciones/tests:** Correlación por run_id, redacción, métricas no
  inventadas, usage unavailable, latencia por agent/model y fallback rate.
- **Evidencia esperada:** Trace ID verificable y aggregate report derivado.
- **Done When:** El reporte no estima métricas ausentes y permite comparar
  evidencia por modelo/agente.

## FASE 8 — EVALUACIÓN, BONUS Y DOCUMENTACIÓN

### [X] T025 — Harness de evaluación de cinco escenarios

- **Objetivo:** Ejecutar exactamente SC-01 a SC-05 y conservar los registros
  comparables requeridos.
- **FR/NFR:** FR-071–073, FR-084–085; NFR-016.
- **Dependencias:** T013, T022–T024.
- **Módulos/archivos:** `evaluation/{scenarios/,reports/}`,
  `tests/e2e/test_evaluation_scenarios.py`.
- **Acciones principales:** Ejecutar Password Recovery, Account Locking,
  Transaction History API, Non-expiring reset token y arbitrary-user-ID con
  expected statuses inmutables.
- **Validaciones/tests:** Exactamente cinco registros; SC-01/02/03 APPROVED;
  SC-04/05 REJECTED; cada record contiene expected/observed/status_match,
  security signal/findings, score, iteration, models, RAG, tools, trace_id y
  pass. REJECTED es pass cuando expected==observed.
- **Evidencia esperada:** Evaluation report y cinco scenario records.
- **Done When:** Los dos REJECTED demuestran controles security/IDOR sin cambiar
  outcomes para hacer pasar pruebas.

### [X] T026 — Evaluación E2E del bonus Multi-model local

- **Objetivo:** Demostrar el único bonus MVP+ mediante una corrida normal local
  de seis agentes y comparación 4B vs 9B.
- **FR/NFR:** FR-047–049, FR-075–076; NFR-007, NFR-009, NFR-015.
- **Dependencias:** T022, T024, T025.
- **Módulos/archivos:** actualización `observability/evaluation.py`,
  `tests/e2e/test_multimodel_evidence.py`, artefactos `evaluation/reports/`.
- **Acciones principales:** Ejecutar todos los roles con mapeo fijo y recopilar
  por agent/model latency, usage cuando exista, structured-output success,
  expected-vs-observed, calidad observable y fallback.
- **Validaciones/tests:** Evidencia real de `qwen3.5:4b` y `qwen3.5:9b`, seis
  spans, cloud excluido como prueba principal y comparación agrupada.
- **Evidencia esperada:** Trace Langfuse y reporte Multi-model local.
- **Done When:** El reporte prueba el bonus con ambos modelos Ollama, no con
  fallback cloud.

### [X] T027 — Documentación, diagramas y demo reproducible

- **Objetivo:** Entregar documentación de operación, gobernanza, evidencia y
  una demo observable de extremo a extremo.
- **FR/NFR:** FR-074, FR-078–086; NFR-016.
- **Dependencias:** T024–T026.
- **Módulos/archivos:** `README.md`, `docs/architecture/`,
  `docs/diagrams/{architecture.md,langgraph.md}`, `docs/{rag.md,mcp.md,evaluation.md}`,
  `scripts/`, `tests/integration/test_documentation.py`.
- **Acciones principales:** Documentar instalación/configuración/CLI/Ollama/
  cloud opcional, límites y dependencias; crear diagramas requeridos; explicar
  RAG/MCP/HITL y registrar demo requirement→Product→Architecture→RAG→Developer
  →Repository MCP→Security→Quality MCP→Testing→Reviewer→remediation cuando
  aplique→Langfuse→FinalReport.
- **Validaciones/tests:** Comandos reproducibles, completitud README/RAG/MCP/
  evaluation, ambos HITL, trace verificable y presencia de documentación de
  métricas/escenarios/modelos.
- **Evidencia esperada:** Runbook, diagramas, trace ID y transcript de demo.
- **Done When:** Un operador puede reproducir la demostración sin introducir
  UI compleja, bonus adicionales ni cambios de contratos SDD.

## FASE 9 — REMEDIACIÓN FINAL DE CUMPLIMIENTO

### [X] T028 — Servidores y cliente MCP mediante protocolo real

- **Objetivo:** Exponer Repository y Quality como MCP Servers reales y
  consumir sus tools desde el grafo mediante una sesión oficial MCP por stdio.
- **FR/NFR:** FR-025, FR-041–045, FR-065, FR-067; NFR-011–014, NFR-018.
- **Dependencias:** T012, T014, T022–T023.
- **Módulos/archivos:** `mcp/` server bootstrap/client adapter, composición del
  grafo y pruebas `tests/mcp/`/`tests/integration/`.
- **Validaciones/tests:** RED/GREEN para sesión/protocolo real, discovery,
  list/read/run_tests, allowlists, traversal y cadena FAILED→REJECTED→remediation.
- **Done When:** La evidencia principal atraviesa cliente, protocolo y server
  MCP reales; una falla cambia estado/routing.

### [X] T029 — LangChain productivo en el pipeline RAG

- **Objetivo:** Usar las abstracciones oficiales LangChain Document y text
  splitter dentro de la ingesta real, preservando embeddings y Chroma actuales.
- **FR/NFR:** FR-035–040, FR-074; NFR-004, NFR-008.
- **Dependencias:** T010–T011.
- **Módulos/archivos:** `rag/loaders.py`, dependencias oficiales
  mínimas y pruebas RAG.
- **Validaciones/tests:** RED/GREEN que demuestre el componente LangChain real,
  metadata/provenance, match, NO_RELEVANT_DOCS y persistencia Chroma.
- **Done When:** LangChain tiene responsabilidad productiva verificable sin
  reemplazar LangGraph, Sentence Transformers ni Chroma.

### [X] T030 — Propuesta técnica Developer detallada y segura

- **Objetivo:** Producir un candidate determinístico rico y evidence-backed
  para PROPOSED sin permitir archivos o evidencia inventados.
- **FR/NFR:** FR-023–027, FR-044, FR-049; NFR-006, NFR-011–013.
- **Dependencias:** T018, T028.
- **Módulos/archivos:** `agents/developer.py`, semantic guard relacionado y
  pruebas Developer.
- **Validaciones/tests:** RED/GREEN para propuesta no vacía, paths inspeccionados,
  pseudodiff, evidencia, validación, superficie security y facts gobernados.
- **Done When:** Un resultado normal no queda vacío y cualquier no-op está
  específicamente justificado.

### [X] T031 — Evaluación LIVE local de cinco escenarios y métricas

- **Objetivo:** Añadir un modo reproducible separado que ejecute SC-01–SC-05
  mediante ModelRouter/LocalModelRuntime reales y derive métricas observadas.
- **FR/NFR:** FR-048–049, FR-071–076; NFR-007, NFR-009, NFR-015–016.
- **Dependencias:** T024–T026, T030.
- **Módulos/archivos:** evaluación, script CLI, pruebas E2E y reportes LIVE
  separados.
- **Validaciones/tests:** Cinco outcomes inmutables, LLM calls > 0, latencias
  por agente/modelo, 3 APPROVED/2 REJECTED, multi-model local sin cloud.
- **Done When:** Reportes LIVE contienen solo métricas derivadas de ejecuciones
  reales y no sobrescriben los reportes determinísticos.

### [X] T032 — Prompts, evidencia y documentación de remediación

- **Objetivo:** Fortalecer concisamente los seis system prompts y documentar
  MCP protocol, LangChain RAG, evaluación LIVE y evidencia sanitizada.
- **FR/NFR:** FR-008, FR-078–085; NFR-012, NFR-015–016.
- **Dependencias:** T028–T031.
- **Módulos/archivos:** prompts, README, docs/diagramas/runbook y
  `docs/evidence/final-audit.md`.
- **Validaciones/tests:** Contenido contractual mínimo, comandos reproducibles,
  run_id/trace_id reales y ausencia de secretos.
- **Done When:** La documentación distingue LangGraph/LangChain/RAG/MCP y
  permite reproducir la evidencia final.

### [X] T033 — Regresión y acceptance final

- **Objetivo:** Ejecutar todos los gates focalizados, suite completa, Ruff y
  smokes LIVE requeridos sin regresiones ni evidencia falsa.
- **FR/NFR:** Todos los afectados por T028–T032.
- **Dependencias:** T028–T032.
- **Validaciones/tests:** MCP, RAG/LangChain, Developer, graph/integration, E2E,
  Ruff, pytest completo, MCP LIVE, 4B/9B LIVE, cinco escenarios y Langfuse LIVE.
- **Done When:** Todos los gates de Definition of Done pasan, secretos/caches
  quedan fuera de Git y el commit aprobado se publica en el branch actual.

## FASE 10 — HARDENING FINAL POST-AUDITORÍA

### [X] T034 — Frontera de secretos y errores operativos

- **Objetivo:** Excluir secret paths de Repository MCP y propagar
  `MCP_ERROR`, `TOOL_ERROR` y `AGENT_TIMEOUT` con efecto de grafo y Langfuse.
- **FR/NFR:** FR-044, FR-065, FR-067, FR-069; NFR-012, NFR-014; AC-027–028.
- **Validaciones/tests:** Sentinels ficticios, MCP unavailable, tool FAIL,
  timeout controlado y disponibilidad no-timeout.
- **Done When:** Un MCP requerido indisponible no puede terminar APPROVED y
  ningún error operativo activa cloud fuera de su política.

### [X] T035 — Sesión MCP persistente y diff real

- **Objetivo:** Mantener lifecycle stdio explícito y estado real entre calls.
- **FR/NFR:** FR-041–044; NFR-011, NFR-013–014.
- **Validaciones/tests:** run/get para tests, build y security; update/create
  seguidos de unified diff; cierre sin procesos huérfanos.
- **Done When:** Getters y diff funcionan mediante MCP Client/Server real.

### [X] T036 — Developer relevante y detallado

- **Objetivo:** Seleccionar 2–4 paths por evidencia, buscar/leer contenido y
  producir propuesta concreta sin paths ni símbolos inventados.
- **FR/NFR:** FR-023–027, FR-044; NFR-006, NFR-011–013; AC-014.
- **Validaciones/tests:** Primeros paths irrelevantes y módulo de transacciones
  relevante, inspección MCP, pseudodiff, API/data, validación y seguridad.
- **Done When:** Developer deja de seleccionar `safe_paths[:3]` y toda
  propuesta normal queda respaldada por search/read MCP.

### [X] T037 — Calidad del corpus RAG

- **Objetivo:** Fortalecer los seis documentos existentes con secciones y
  reglas diferenciadas sin alterar LangChain/Sentence Transformers/Chroma.
- **FR/NFR:** FR-035–040, FR-074; NFR-004, NFR-008.
- **Validaciones/tests:** Contenido sustantivo, retrieval especializado y
  provenance intacta para Architecture, Security y Testing.
- **Done When:** El corpus es útil y las consultas recuperan fuentes/secciones
  pertinentes.

### [X] T038 — Documentación, evidencia y regresión final

- **Objetivo:** Corregir drift, ejecutar gates y preservar la evidencia LIVE
  local/cloud ya validada sin repetir consumos o corridas largas.
- **FR/NFR:** FR-060–061, FR-071–086; NFR-012, NFR-015–017.
- **Validaciones/tests:** Suites focalizadas/completas, Ruff y secret scan;
  consistencia de la evidencia Multi-model, escenarios y Langfuse existente.
- **Done When:** Código, documentación y evidencia final son consistentes.

## MATRIZ DE TRAZABILIDAD FR/NFR → TASK(S)

| FR/NFR | Task(s) |
| --- | --- |
| FR-001–002 | T001, T022 |
| FR-003–005 | T008, T022 |
| FR-006–009 | T002–T004, T015 |
| FR-010–020 | T008–T009, T022–T023 |
| FR-021–022 | T002, T016–T017 |
| FR-023–027 | T012, T018, T030, T036 |
| FR-028–029 | T002, T019 |
| FR-030–031 | T002, T013, T020 |
| FR-032–034 | T002, T009, T021 |
| FR-035–040 | T010–T011, T017, T019–T020, T029, T037 |
| FR-041 | T012, T028, T035 |
| FR-042 | T014, T028 |
| FR-043–045 | T012, T014, T018–T020, T023, T028, T034–T035 |
| FR-046–050 | T001, T005–T006, T016–T021, T026 |
| FR-051–059 | T001, T003, T007, T023 |
| FR-060–061 | T006, T024 |
| FR-062–069 | T003, T006–T007, T009, T023, T034 |
| FR-070 | T002, T021–T022 |
| FR-071–073 | T013, T025, T031 |
| FR-074 | T010–T011, T027, T029 |
| FR-075–076 | T024–T027, T031 |
| FR-077 | T007, T023 |
| FR-078–086 | T024–T027, T032 |
| Remediación MCP/LangChain/Developer/LIVE | T028–T038 |
| NFR-001–003 | T001, T013 |
| NFR-004 | T006, T011, T022, T029 |
| NFR-005–006 | T002–T004, T008–T009 |
| NFR-007–010 | T005–T007, T022, T026 |
| NFR-011–014 | T003, T007, T012, T014, T023, T034–T036 |
| NFR-015 | T024, T026 |
| NFR-016 | T013–T014, T025, T027 |
| NFR-017–018 | T001, T003, T007, T012, T023 |

## MATRIZ DE TRAZABILIDAD PLAN COMPONENT → TASK(S)

| Componente del Plan | Task(s) |
| --- | --- |
| Estructura, configuración y CLI | T001, T022 |
| Contratos, EngineeringState y ContextEnvelope | T002, T004, T015 |
| ModelRegistry, Router, Ollama y cloud | T005–T007 |
| StateGraph, routers, remediation y HITL | T008–T009, T022–T023 |
| Seis agentes y prompts | T015–T021 |
| Corpus, Chroma y retrievers RAG | T010–T011, T037 |
| Workspace, Repository MCP y Quality MCP | T012–T014, T034–T035 |
| Langfuse, métricas y reportes | T024–T026 |
| Sample app, escenarios y E2E | T013, T025–T026 |
| Documentación, diagramas y demo | T027, T038 |
| MCP protocol, LangChain RAG y evaluación LIVE | T028–T038 |

## REQUISITOS SIN COBERTURA

Ninguno.

## SELF-REVIEW

- Las 38 Tasks derivan de Constitution, Spec y Plan; no introducen requisitos
  ni decisiones de arquitectura nuevas.
- Todas las Tasks incluyen validación, evidencia y condición de terminación.
- Multi-model local tiene implementación explícita (T005–T006) y prueba E2E
  real (T026); cloud fallback queda separado en T007.
- Retry y repair se verifican por separado en T007 y T023.
- RAG, Repository MCP, Quality MCP, Langfuse, HITL, cinco escenarios,
  documentación y demo tienen cobertura explícita.
- SC-04 y SC-05 siguen siendo REJECTED; ninguna Task cambia outcomes.
- Constitution, Spec y Plan no se modifican; esta ejecución crea solo Tasks.
