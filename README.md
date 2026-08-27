# Autonomous Software Engineering Team

Equipo local-first de exactamente seis agentes — Product, Architecture,
Developer, Security, Testing y Reviewer — coordinado únicamente por un
`LangGraph StateGraph`. Pydantic valida toda salida que afecta estado o rutas;
routers determinísticos controlan remediación, límites e HITL.

## Arquitectura y stack

El monolito modular separa contratos, agentes, grafo, Ollama, RAG, MCP,
observabilidad y workspaces por corrida. LangGraph es el único orquestador;
LangChain aporta `Document` y text splitting al RAG; Sentence Transformers
genera embeddings y Chroma los persiste. Repository y Quality se exponen como
MCP Servers reales y el grafo los consume con un MCP Client oficial por stdio.
Usa Python 3.10+, Pydantic, Ollama, Langfuse, pytest y FastAPI/SQLite. Consulte
`docs/architecture/overview.md` y los diagramas de `docs/diagrams/`.

## Instalación

El proyecto usa únicamente `pyproject.toml`; no hay un segundo gestor de
dependencias.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,rag,observability,sample-app]"
Copy-Item .env.example .env
ollama pull qwen3.5:4b
ollama pull qwen3.5:9b
ollama list
```

Modelos requeridos y routing fijo:

| Agente | Perfil | Modelo |
|---|---|---|
| Product | DEEP_MODEL | `qwen3.5:9b` |
| Architecture | FAST_MODEL | `qwen3.5:4b` |
| Developer | CODING_MODEL | `qwen3.5:9b` |
| Security | DEEP_MODEL | `qwen3.5:9b` |
| Testing | FAST_MODEL | `qwen3.5:4b` |
| Reviewer | DEEP_MODEL | `qwen3.5:9b` |

## Configuración

Copie `.env.example`. Los valores RAG aprobados son 800 tokens, overlap 160,
top_k 4, fetch_k 8 y relevancia normalizada 0.55. Cloud está desactivado por
defecto. `GEMINI_API_KEY` y `GROQ_API_KEY` son opcionales y nunca se imprimen.
Langfuse live requiere `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` y
`LANGFUSE_BASE_URL`; sin credenciales el adapter conserva una
traza local correlacionada y el core continúa. Gemini/Groq son opcionales y no
cuentan como evidencia multi-model local.

### Cloud-first (opcional)

Con `CLOUD_ENABLED=true` y `LOCAL_FIRST=false` en `.env`, el runtime se
invierte: `CloudModelRuntime` (Gemini/Groq, ruteado por rol vía `_CLOUD_MAP`
en `llm/cloud.py`) pasa a ser el runtime primario para los seis agentes, y
Ollama (`LocalModelRuntime`) queda como fallback local si una llamada cloud
falla. El límite de presupuesto de cloud (`max_cloud_escalations_per_run/agent`)
solo aplica cuando cloud es fallback; como primario no está acotado por esos
contadores, ya que atender seis agentes por corrida es el caso normal, no una
contingencia. Ambos runtimes construyen el prompt desde los mismos archivos
`prompts/<rol>/system.md` (vía `engineering_team.llm.prompting`), así que el
proveedor nunca cambia las boundaries o el contrato de salida de un agente.
Requiere `GEMINI_API_KEY` y/o `GROQ_API_KEY` configuradas.

## Run

Windows:

```powershell
.\run.ps1
```

macOS:

```sh
chmod +x run.sh
./run.sh
```

The project must already be configured before running these scripts.

### Frontend y API en tiempo real

El frontend Vite consume la aplicación FastAPI existente mediante
`POST /api/runs` y `WebSocket /ws/runs/{run_id}`. Ejecute ambos procesos desde
la raíz del repositorio, en terminales separadas.

Terminal 1 — API y workflow Python:

```powershell
.\.venv\Scripts\python.exe -m uvicorn sample_app.app.main:app --host 127.0.0.1 --port 8000 --reload
```

Terminal 2 — frontend:

```powershell
Set-Location frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Abra `http://127.0.0.1:5173`. Vite redirige `/api` y `/ws` hacia FastAPI en
el puerto 8000. Las rutas de proyecto ingresadas en la UI se resuelven desde la
raíz donde se inició FastAPI; `sample_app` funciona como escenario incluido.

Validaciones del frontend:

```powershell
Set-Location frontend
npm test
npm run typecheck
npm run lint
npm run build
```

### Escenario de demostración: calculadora QA

`demo-projects/calculadora-qa-demo` es un proyecto real e independiente
(no un mock) usado para ejercer el flujo completo desde el chat: copia
aislada, ejecución del workflow, aprobación y Apply seguro contra el
proyecto fuente. Instálelo en modo editable antes de usarlo como destino de
un chat:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[sample-app,rag,observability,dev]"
.\.venv\Scripts\python.exe -m pip install -e .\demo-projects\calculadora-qa-demo
.\.venv\Scripts\python.exe -m uvicorn sample_app.app.main:app --host 127.0.0.1 --port 8000
Set-Location frontend
npm.cmd install
npm.cmd run dev
```

Seleccione en la UI una **copia temporal** de `demo-projects/calculadora-qa-demo`
(nunca el original) y envíe un mensaje de chat acotado. Cómo verificar cada
etapa sin confiar en la sola respuesta de la UI:

- Las trazas de eventos del run (`GET /api/runs/{run_id}/events` o el panel
  de la corrida) confirman que el workflow realmente se ejecutó.
- Los archivos bajo la carpeta de workspace aislada del run (no el proyecto
  original) confirman que la implementación ocurrió antes de cualquier Apply.
- Solo tras `POST /api/runs/{run_id}/apply` con `confirmed: true` el estado
  pasa a `applied`, y únicamente entonces el proyecto fuente cambia; el
  campo `test_exit_code` de la respuesta refleja la ejecución real de
  pytest sobre el proyecto fuente ya modificado, no sobre la copia aislada.

`tests/e2e/test_chat_apply_flow.py` reproduce este mismo recorrido de forma
determinista y automatizada (sin LLM real) contra una copia temporal de
`calculadora-qa-demo`, y es la prueba de referencia para este flujo.

## Ejecución y evidencia

```powershell
# Suite completa
.\.venv\Scripts\python.exe -m pytest

# Cinco escenarios SC-01..SC-05 y agregado
.\.venv\Scripts\python.exe scripts/run_evaluation.py

# Los mismos cinco escenarios con ModelRouter/Ollama reales y Langfuse
.\.venv\Scripts\python.exe scripts/run_evaluation.py --live-models

# Corrida normal REAL con qwen3.5:4b y qwen3.5:9b
.\.venv\Scripts\python.exe scripts/run_multimodel.py
```

El modo rápido escribe `scenarios.json`/`aggregate.json`; el modo LIVE escribe
por separado `scenarios-live.json`/`aggregate-live.json` y conserva llamadas,
latencias y usage reales. Los scripts escriben evidencia en `evaluation/reports/`.
La corrida multi-model usa la respuesta completa y validada de cada modelo
como artefacto del nodo. Las trazas locales redacted quedan en
`evaluation/reports/traces/`; Quality MCP valida la copia aislada de la corrida.
La demo completa está en `docs/demo-runbook.md`. Cloud live es opcional:
`MCP_ERROR`, `TOOL_ERROR` y `RAG_ERROR` nunca lo activan automáticamente.
