# Herramientas de la demo bancaria

Esta carpeta está **fuera del proyecto que modifican los agentes**. Conserva el
baseline, el controlador Playwright y pruebas independientes de aceptación.

- `baseline.json`: contenido original y SHA-256 por archivo. No regenerarlo a
  partir de una demo ya ejecutada: eso convertiría la solución en el punto inicial.
- `support.py`: lectura de prompts desde el README, clasificación de resultados,
  restablecimiento acotado a la carpeta marcada `banca-demo` y comprobación de base.
- `demo.py`: navegador Chrome con perfil temporal, selección de proyecto y siete
  solicitudes reales, en serie. Usa la API solo para comprobar el estado persistido;
  la creación de runs y la navegación se hacen mediante la UI.
- `test_acceptance.py`: comprobaciones independientes del código generado, con
  SQLite en memoria. Verifica aislamiento entre usuarios, autenticación, expiración,
  uso único y que las operaciones pendientes no modifiquen transacciones.
- `evidence/`: capturas, snapshots, intentos y resultados de pruebas. Está ignorado
  por Git y no se borra al restaurar la demo. Puede contener código de la demo;
  revisar antes de compartir.

## Pruebas de las herramientas

Desde la raíz del repositorio:

```sh
.venv/bin/python -m pip install -r demo-projects/banca-demo-support/requirements.txt
.venv/bin/python -m pytest demo-projects/banca-demo-support/test_support.py -q
```

Chrome debe estar instalado. Playwright lo lanza con un perfil separado y no toca
las pestañas ni sesiones personales.

## Resultados y reintentos

Un positivo exige `applied`, aprobación del reviewer, `test_exit_code=0`, archivos
realmente escritos y pruebas en la carpeta original. Un rechazo esperado exige
hallazgos de seguridad y proyecto original intacto. Un error de proveedor, timeout,
fallo de formato o interrupción **no es un rechazo de seguridad exitoso**.

Los intentos no relacionados con seguridad tienen un máximo configurable (3 por
defecto), con enfriamiento entre solicitudes. Un bloqueo de seguridad o un problema
al aplicar detiene la demo para inspección; no se deshabilitan los controles.
El deadline nunca dispara otro run mientras el anterior sigue activo.

`summary.json` distingue `complete: false` de una secuencia completada y conserva
los run IDs, trace IDs, fases y duraciones. Una ejecución con `--cases 1` solo valida
ese subconjunto; **no** significa que se validaron los siete casos.

## Qué explicar durante la presentación

| Vista | Qué demuestra |
|---|---|
| Run history | Instrucciones anteriores agrupadas y sus reintentos; no se borra al restaurar el banco. |
| Grafo | El agente activo y el orden real de trabajo. Un reintento puede volver a Developer. |
| Trace ID | Identidad de la traza, comprobada contra el snapshot persistido. |
| Code changes | Cambios del workspace y aplicación al proyecto; los archivos sin hunks pueden ser destinos solicitados sin cambios textuales. |
| Reviewer scorecard | Decisión y evidencias de los controles configurados, no una certificación de seguridad exhaustiva. |
| RAG documents cited | Documentos reales recuperados para cada función, con fuente y fragmento. |
| MCP tools executed | Lecturas, escrituras, scans y pruebas ejecutadas; la demo recorre el panel completo. |
| Errors / Model usage | Errores del flujo y advertencias de proveedor. Un fallback exitoso no borra el intento fallido. |
| Apply result | `APPLIED` y pruebas en el proyecto original; en un rechazo, verificar que no se aplicó. |

El setup tiene seis agentes, pero Testing y Reviewer son puertas deterministas:
ejecutan/evalúan evidencia de herramientas y no hacen una llamada a un modelo por
cada paso. Product, Architecture, Developer y Security sí usan el runtime de
modelos. Security combina reglas locales y evidencia de scanners/RAG con un
artefacto gobernado: los dos rechazos de la demo no son una evaluación ciega de
razonamiento de un LLM. La aceptación independiente comprueba comportamiento real
además de la puntuación del reviewer.

Las pruebas de calibración detectaron un límite de tamaño para Groq en Developer;
por eso no se requiere habilitar ese escape para ejecutar la demo. Consultar el
modelo que realmente respondió en Model usage, no asumir que siempre fue el
primero de la cadena. Las métricas de tokens ausentes no significan consumo cero.

Para ejecutar pruebas del sistema mientras su backend está abierto, aislar los
registros de pruebas del historial activo:

```sh
WORKSPACE_ROOT=/tmp/banca-isolated-tests .venv/bin/python -m pytest tests/unit tests/test_run_api.py -q
```
