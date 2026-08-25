# Autonomous Software Engineering Team

Equipo local-first de exactamente seis agentes — Product, Architecture,
Developer, Security, Testing y Reviewer — coordinado únicamente por un
`LangGraph StateGraph`. Pydantic valida toda salida que afecta estado o rutas;
routers determinísticos controlan remediación, límites e HITL.

## Arquitectura y stack

El monolito modular separa contratos, agentes, grafo, Ollama, RAG, MCP,
observabilidad y workspaces por corrida. Usa Python 3.10+, LangGraph, Pydantic,
Ollama, Sentence Transformers, Chroma persistente, Langfuse, pytest,
FastAPI/SQLite, Repository MCP y Quality MCP. Consulte
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
traza local correlacionada y el core continúa.

## Ejecución y evidencia

```powershell
# Suite completa
.\.venv\Scripts\python.exe -m pytest

# Cinco escenarios SC-01..SC-05 y agregado
.\.venv\Scripts\python.exe scripts/run_evaluation.py

# Corrida normal REAL con qwen3.5:4b y qwen3.5:9b
.\.venv\Scripts\python.exe scripts/run_multimodel.py
```

Los dos scripts escriben evidencia reproducible en `evaluation/reports/`.
La corrida multi-model usa la respuesta completa y validada de cada modelo
como artefacto del nodo. Las trazas locales redacted quedan en
`evaluation/reports/traces/`; Quality MCP valida la copia aislada de la corrida.
La demo completa está en `docs/demo-runbook.md`. Cloud live es opcional:
`MCP_ERROR`, `TOOL_ERROR` y `RAG_ERROR` nunca lo activan automáticamente.
