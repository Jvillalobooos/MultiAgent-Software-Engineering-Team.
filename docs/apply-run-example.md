# Ejecutar el flujo completo contra un proyecto real (`run-project`)

Este comando corre el equipo completo (Product → Architecture → Developer →
Security → Testing → Reviewer) contra una carpeta de proyecto real, y — solo
si se autoriza explícitamente — aplica los cambios generados escribiendo
archivos de verdad vía Repository MCP (`create_file`/`update_file`).

`demo-projects/` es la carpeta dedicada dentro de este repo para guardar
proyectos de prueba reales sobre los que correr `run-project` (está en
`.gitignore`: cada proyecto ahí adentro conserva su propio git independiente,
sin mezclarse con el historial de este repo).

## Requisito previo

Ejecutar todo desde una terminal de VS Code parada en la raíz de **este**
proyecto (donde vive el `.venv` y el `.env` con `CLOUD_ENABLED`/`LOCAL_FIRST`/
las API keys), no en la carpeta del proyecto objetivo:

```bash
cd /Users/johnbenjamincastrosanabria/Developer/MultiAgent-Software-Engineering-Team
```

## Paso 1 — Dry-run (no escribe nada)

Genera el código propuesto sin tocar el proyecto objetivo. Revisa
`evaluation/reports/apply-run-dryrun.json` — los campos `changed_files` y
`proposed_file_contents` muestran exactamente el código que se escribiría.

```bash
.venv/bin/engineering-team run-project demo-projects/calculadora-qa-demo \
  --spec "Edita el archivo calculadora/estadisticas.py: sustituye la funcion mediana para que cuando la cantidad de elementos sea par devuelva el promedio de los dos valores centrales, y con cantidad impar el valor central." \
  --test-spec "Crea tests/test_mediana_par.py con dos funciones de prueba que verifiquen mediana([7,8,9,10])==8.5 y mediana([16,22,5,34])==19.0, importando desde calculadora.estadisticas" \
  --dry-run \
  --report-path evaluation/reports/apply-run-dryrun.json
```

## Paso 2 — Aplicar de verdad

Si el contenido propuesto en el paso 1 se ve correcto, repite el mismo
comando cambiando `--dry-run` por `--authorize-writes`. Esto satisface el
guardrail de autorización explícita para cambios destructivos
(`require_explicit_destructive_authorization`) y dispara la escritura real
de archivos en `demo-projects/calculadora-qa-demo`.

```bash
.venv/bin/engineering-team run-project demo-projects/calculadora-qa-demo \
  --spec "Edita el archivo calculadora/estadisticas.py: sustituye la funcion mediana para que cuando la cantidad de elementos sea par devuelva el promedio de los dos valores centrales, y con cantidad impar el valor central." \
  --test-spec "Crea tests/test_mediana_par.py con dos funciones de prueba que verifiquen mediana([7,8,9,10])==8.5 y mediana([16,22,5,34])==19.0, importando desde calculadora.estadisticas" \
  --authorize-writes \
  --report-path evaluation/reports/apply-run.json
```

## Restablecer el proyecto de prueba

Para volver `demo-projects/calculadora-qa-demo` a su estado original (bug de
`mediana` intacto, sin `tests/test_mediana_par.py`) entre corridas de la
demo:

```bash
.venv/bin/engineering-team reset-project demo-projects/calculadora-qa-demo
```

Detecta automáticamente cómo está guardado el proyecto y elige el modo:

- **Repo independiente** (`<proyecto>/.git` existe): `git reset --hard` al
  commit raíz de ESE repo + `git clean -fd` para borrar archivos sin
  trackear.
- **Subárbol trackeado** (sin `.git` propio — el caso actual de
  `calculadora-qa-demo`, incorporado a este repo): restaura el contenido de
  la carpeta al commit más antiguo que la agregó, con `git checkout
  <commit> -- <ruta>`; borra con `git clean -fd -- <ruta>` cualquier
  archivo nuevo sin trackear que `run-project` haya creado (como
  `tests/test_mediana_par.py`, ya que las escrituras de `create_file`/
  `update_file` nunca hacen `git add`); y si queda algo por commitear, crea
  un commit **acotado a esa ruta únicamente** (`git commit -- <ruta>`), sin
  tocar ningún otro cambio pendiente en el repo.

En ambos modos se niega a correr si `project_path` apunta a este mismo
repositorio.

Si ya commiteaste sin querer los cambios que aplicó `run-project` (como
puede pasar con el modo subárbol, ya que no tiene su propio `.git` para
aislar el `reset --hard`), no se pierde nada: seguís en el historial de
este repo, y `reset-project` corrige el estado igual, agregando un commit
nuevo que revierte esa carpeta a su línea base — nunca reescribe ni
descarta commits existentes.

## Sin `--authorize-writes`

El Developer sigue generando `file_contents` con el código completo, pero
`RepositoryMCP.create_file`/`update_file` nunca se llaman: el nodo del grafo
detecta la falta de autorización, agrega un `WorkflowError` y fuerza
`human_review_required: true` en el reporte — nada se escribe en disco.

## Qué revisar en el JSON de salida

| Campo | Qué indica |
|---|---|
| `final_status` | `APPROVED` o `HUMAN_REVIEW_REQUIRED` |
| `route_history` | Secuencia real de nodos ejecutados, incluye ciclos de remediación |
| `action_mode` | `APPLIED` cuando el Developer decidió escribir archivos |
| `changed_files` | Rutas que el Developer identificó desde el texto de la especificación |
| `proposed_file_contents` | Código completo generado por el LLM para cada archivo (visible incluso en dry-run) |
| `files_written` | Rutas efectivamente escritas en disco (solo con `--authorize-writes`) |
| `applied_diff` | Diff real (`git`-style) obtenido de `get_diff` tras escribir |
| `review` | Decisión estructurada del Reviewer (`status`, `score`, `subscores`, `problems`) |
| `destructive_authorization_blocked` | `true` si el guardrail bloqueó la escritura por falta de autorización |

## Alternativa: desde código Python

```python
from engineering_team.config import Settings
from engineering_team.apply_run import run_on_project

evidence = run_on_project(
    Settings(),
    project_path="demo-projects/calculadora-qa-demo",
    specification=(
        "Edita el archivo calculadora/estadisticas.py: sustituye la funcion "
        "mediana para que cuando la cantidad de elementos sea par devuelva el "
        "promedio de los dos valores centrales, y con cantidad impar el valor "
        "central."
    ),
    test_specification=(
        "Crea tests/test_mediana_par.py con dos funciones de prueba que "
        "verifiquen mediana([7,8,9,10])==8.5 y mediana([16,22,5,34])==19.0, "
        "importando desde calculadora.estadisticas"
    ),
    authorize_writes=True,
    report_path="evaluation/reports/apply-run.json",
)
```

`run_on_project` lee `settings.cloud_enabled`/`settings.local_first` del
`.env` de este proyecto automáticamente (cloud-first si ya está configurado
así) y la corrida queda instrumentada en Langfuse igual que el resto de
ejecuciones.
