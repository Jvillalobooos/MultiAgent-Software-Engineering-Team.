# Autonomous Software Engineering Team

Equipo de exactamente seis agentes — Product, Architecture, Developer,
Security, Testing y Reviewer — coordinado únicamente por un `LangGraph
StateGraph`. La estrategia de modelo es `CLOUD_FIRST` por defecto
(`MODEL_PRIORITY=cloud_first|local_first|cloud_only|local_only`): un proveedor
cloud aprobado es primario para las seis agentes, con Ollama local como
fallback acotado y modo offline explícito. Pydantic valida toda salida que
afecta estado o rutas; routers determinísticos controlan remediación, límites
e HITL.

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
Use `LANGFUSE_OFFLINE=true` para una ejecución local deliberada incluso cuando
las credenciales sigan configuradas; así se evita que una interrupción tardía
del exportador afecte una verificación sin red y la traza JSON local se conserva.

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

Antes de ejecutar Product, `ProjectCapabilities` detecta de forma local y
determinística el proyecto. Se admiten Python, Node/TypeScript, .NET, Java
(Maven o Gradle), Go y Rust. Cada perfil declara sus patrones nativos de
fuentes/pruebas y comandos obligatorios. Quality MCP vuelve a detectar el
proyecto y acepta únicamente el `profile fingerprint`; nunca recibe comandos
propuestos por un modelo.

Un proyecto desconocido, híbrido/ambiguo o sin comando de pruebas obligatorio
termina de forma segura como `INCOMPLETE` con `PROJECT_CAPABILITY_ERROR`, antes
de llamar a un modelo o iniciar un subprocess. El sistema no instala paquetes
ni descarga herramientas automáticamente. Testing genera únicamente archivos
de prueba compatibles con el perfil. Cada ruta propuesta debe ser única y cada
prueba debe referenciar comportamiento presente en el diff; una prueba antigua
o sobrescrita no cuenta como evidencia generada. Reviewer exige evidencia
exitosa de cada capacidad obligatoria, como `test` y, para ecosistemas
compilados, `build`.

Run against `sample_app` by default, or select another project explicitly;
all automatic writes occur only in an isolated run copy:

```powershell
nova-team
nova-team --project "C:\path\to\project"
# Explicit bundled sample target (equivalent to the default)
nova-team --project ".\sample_app"
```

### Optional global command

Windows:

```powershell
.\install-launcher.ps1
nova-team
```

macOS:

```sh
chmod +x install-launcher.sh
./install-launcher.sh
nova-team
```

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
