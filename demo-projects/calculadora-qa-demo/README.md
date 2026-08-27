# calculadora-qa-demo

Calculadora modular en Python. Proyecto de prueba para ejercitar el agente QA.

## Estructura

- `calculadora/operaciones.py` — aritmética básica y potencias.
- `calculadora/estadisticas.py` — media, mediana, moda y rango.
- `calculadora/historial.py` — registro de operaciones ejecutadas.
- `calculadora/cli.py` — interfaz de línea de comandos.

## Uso

```bash
python -m calculadora.cli sumar 2 3
python -m pytest -q
```

## Uso como escenario de chat multi-agente

Este proyecto también se usa como destino real (no simulado) para probar el
flujo de chat de punta a punta del monorepo: copia aislada, ejecución del
workflow, aprobación y Apply seguro contra el proyecto fuente.

Desde la raíz del repositorio principal:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[sample-app,rag,observability,dev]"
.\.venv\Scripts\python.exe -m pip install -e .\demo-projects\calculadora-qa-demo
.\.venv\Scripts\python.exe -m uvicorn sample_app.app.main:app --host 127.0.0.1 --port 8000
Set-Location frontend
npm.cmd install
npm.cmd run dev
```

Seleccione siempre una **copia temporal** de esta carpeta como proyecto en la
UI, nunca el original. Las trazas del run confirman que el workflow se
ejecutó; los cambios en la carpeta de workspace aislada del run confirman la
implementación; y solo un estado `applied` (junto con `test_exit_code` de la
respuesta de Apply) confirma que el proyecto fuente fue modificado y que su
propia suite de pytest sigue pasando. `tests/e2e/test_chat_apply_flow.py`, en
la raíz del repositorio, automatiza este mismo recorrido de forma
determinista sobre una copia temporal de este proyecto.
