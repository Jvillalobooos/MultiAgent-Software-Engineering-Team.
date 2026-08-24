# Constitución del Autonomous Software Engineering Team

## Propósito y alcance

Esta Constitución gobierna el desarrollo Spec-Driven Development (SDD) del
**Autonomous Software Engineering Team**: un sistema agentic que recibe un
requerimiento funcional y coordina especialistas para analizarlo, diseñar una
solución, proponer o implementar cambios, revisar seguridad, ejecutar pruebas
y emitir una decisión final. No es un chatbot lineal.

## Precedencia normativa

Cuando exista conflicto, la autoridad se resuelve en el siguiente orden:

1. PDF oficial.
2. Esta Constitución.
3. Spec.
4. Plan.
5. Tasks.
6. Implementación.
7. Evidencia derivada.

## Principios

### I. Orquestación única y gobernada

El sistema DEBE usar LangGraph `StateGraph` como único orquestador del flujo
agentic. Los LLM PUEDEN recomendar acciones, pero LangGraph y código
determinístico DEBEN gobernar las transiciones, los límites, los bloqueos y
las decisiones críticas.

### II. Seis agentes core, ni más ni menos

El sistema DEBE contener exactamente estos seis agentes core: Product,
Architecture, Developer, Security, Testing y Reviewer. Ningún cambio DEBE
añadir, fusionar, sustituir o tratar como core a otro agente sin una
actualización constitucional explícita.

### III. Responsabilidad especializada y no solapada

Cada agente DEBE tener una responsabilidad primaria y una salida definida:
Product analiza la necesidad; Architecture diseña la solución; Developer
propone o implementa cambios autorizados; Security evalúa riesgos; Testing
ejecuta o evalúa pruebas; Reviewer emite la decisión final. Un agente NO DEBE
asumir la responsabilidad decisoria de otro ni aprobar su propio trabajo.

### IV. Monolito modular y límites explícitos

La solución DEBE mantenerse como monolito modular, con límites inspirados en
Clean/Hexagonal Architecture solo cuando aporten aislamiento verificable. No
DEBE introducir microservicios ni sobreingeniería fuera de una Spec aprobada.

### V. Shared EngineeringState y aislamiento de contexto

LangGraph DEBE mantener un `EngineeringState` compartido como fuente de
verdad del flujo. Cada agente DEBE recibir únicamente el contexto, las
herramientas y los artefactos estrictamente necesarios para su tarea; no DEBE
recibir el estado completo por defecto.

### VI. Instrucciones y salidas estructuradas por agente

Cada ejecución de agente DEBE incluir un system prompt y un user prompt
separados, con su rol, límites y objetivo explícitos. Toda salida que afecte
routing, aprobación, remediación, escalamiento o estado DEBE validarse con
modelos Pydantic; texto no validado NO DEBE controlar esas decisiones.

### VII. Routing condicional y determinístico

Las rutas condicionales, criterios de aprobación y transiciones DEBEN estar
definidos por reglas determinísticas verificables. El LLM NO DEBE seleccionar
arbitrariamente rutas críticas ni convertir recomendaciones en decisiones sin
validación de código y estado.

### VIII. Multi-model local determinístico (MVP+)

El MVP+ DEBE demostrar el bonus multi-model local mediante observabilidad y
evaluación. Un `ModelRegistry`/`ModelRouter`, o mecanismo determinístico
equivalente, DEBE leer IDs configurados externamente y asignar inicialmente:

| Agente | Modelo local |
| --- | --- |
| Product | DEEP_MODEL: `qwen3.5:9b` |
| Architecture | FAST_MODEL: `qwen3.5:4b` |
| Developer | CODING_MODEL: `qwen3.5:9b` |
| Security | DEEP_MODEL: `qwen3.5:9b` |
| Testing | FAST_MODEL: `qwen3.5:4b` |
| Reviewer | DEEP_MODEL: `qwen3.5:9b` |

Los agentes NO DEBEN hardcodear IDs ni elegir modelos por sí mismos. Este
bonus NO DEBE confundirse con ni sustituirse por fallback cloud.

### IX. Fallback cloud controlado y local-first

La política DEBE ser `LOCAL_FIRST`, con `MAX_LOCAL_RETRIES=1`,
`MAX_LOCAL_REPAIRS=1`,
`MAX_CLOUD_ESCALATIONS_PER_AGENT=1` y `MAX_CLOUD_ESCALATIONS_PER_RUN=3`.
Cloud SOLO PUEDE activarse por `LLM_AVAILABILITY_ERROR`, `LLM_QUALITY_ERROR`
o `SECURITY_CONFLICT` cuando corresponda, usando las asignaciones aprobadas:
Product, Architecture y Reviewer a Gemini 3.7 Flash; Developer y Security a
Groq `openai/gpt-oss-120b`; Testing a Groq `openai/gpt-oss-20b`. `TOOL_ERROR`,
`MCP_ERROR` y `RAG_ERROR` NO DEBEN activar cloud automáticamente. Las
credenciales cloud son opcionales y NUNCA DEBEN almacenarse en código.

### X. RAG con procedencia verificable

El sistema DEBE usar RAG local-first con Sentence Transformers y Chroma cuando
se requiera recuperación de conocimiento. Toda conclusión material basada en
RAG DEBE conservar provenance suficiente para identificar fuente, fragmento o
artefacto recuperado; una recuperación fallida DEBE registrarse como
`RAG_ERROR` y no inventar evidencia.

### XI. MCP de mínimo privilegio y efecto real

Repository MCP y Quality MCP DEBEN concederse con el mínimo privilegio
necesario por agente y operación. Sus resultados DEBEN incorporarse como datos
estructurados con efecto real en el estado o routing de LangGraph; no DEBEN
usarse como adorno narrativo ni ignorarse cuando contradigan una conclusión.

### XII. Remediación acotada y manejo explícito de errores

Todo error de LLM, herramienta, MCP, RAG, validación o ejecución DEBE
clasificarse, preservarse en el estado y dirigir una ruta explícita de
reintento, remediación, escalamiento o revisión humana. Los ciclos DEBEN tener
`MAX_ITERATIONS=3`; al agotarlo, el sistema DEBE emitir
`HUMAN_REVIEW_REQUIRED`, no continuar indefinidamente.

### XIII. Human-in-the-Loop ineludible

Todo hallazgo `CRITICAL` DEBE ir a HITL, independientemente de resultados
posteriores o fallback cloud. Cloud NUNCA DEBE evitar HITL ni la revisión
humana requerida al alcanzar el máximo de iteraciones.

### XIV. Observabilidad integral

Cada corrida DEBE instrumentarse end-to-end con Langfuse, incluyendo al menos
agente, modelo seleccionado, rutas, entradas y salidas estructuradas,
herramientas, errores, reintentos, evaluaciones y decisión final. La
observabilidad DEBE permitir demostrar el bonus multi-model sin exponer
secretos.

### XV. Sandbox de workspace y protección de secretos

Toda ejecución DEBE respetar el sandbox del workspace autorizado, sin acceder
ni modificar recursos fuera de su alcance. Secretos, tokens, credenciales y
datos sensibles NO DEBEN incluirse en código, prompts persistidos, logs,
trazas, fixtures ni evidencia.

### XVI. Evidencia y pruebas obligatorias

Todo cambio que altere comportamiento DEBE acompañarse de pruebas ejecutables
proporcionales, evidencia de resultado y una decisión determinística basada en
criterios definidos. Los cambios documentales o configurativos DEBEN contar
con evidencia de validación proporcional y NO DEBEN requerir pruebas
artificiales únicamente para satisfacer esta Constitución. Ninguna capacidad
funcional DEBE considerarse terminada cuando falten evidencia objetiva,
validación estructurada, controles de seguridad aplicables o resultados de
pruebas requeridos.

### XVII. SDD primero y control de cambios contractuales

Todo cambio que altere contratos, flujos, criterios, responsabilidades,
límites, modelos, herramientas o routing DEBE actualizar primero los
artefactos SDD aplicables (Constitution, Spec, Plan y/o Tasks según la
precedencia) antes de la implementación y la evidencia derivada.

## Límites vigentes

Mientras una Spec aprobada no disponga lo contrario, quedan fuera de alcance:
Parallel Agents, Memory, Auto-PR, Qdrant, n8n, microservicios y una UI
compleja. Estos límites NO DEBEN reinterpretarse como requisitos implícitos.
