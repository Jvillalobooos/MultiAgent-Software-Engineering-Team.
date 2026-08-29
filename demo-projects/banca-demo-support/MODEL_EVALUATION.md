# Modelos y fallback: evaluación del 28 de agosto de 2026

## Criterio

Se revisaron los cambios de Claude, 59 registros de runs creados antes de las
22:00 UTC de esta fecha y pruebas nuevas contra las claves configuradas. No se
copiaron credenciales a la demo. Un modelo en el catálogo no equivale a uno que
funcione con esta cuenta, este contrato y este volumen de código.

Los porcentajes históricos de abajo miden **contratos estructurados aceptados**,
no funcionalidades correctas. Incluyen reintentos y distintas tareas; no son un
benchmark controlado ni una garantía de disponibilidad. La mediana usa únicamente
llamadas que entregaron un contrato válido, por lo que excluye el costo de fallos.

## Historial anterior a esta integración

Fuente local: `workspace/runs/_records/*.json`, eventos con `requested_model` y
`agent`. Corte por `created_at < 2026-08-28T22:00:00Z`.

| Rol | Modelo/proveedor | Contratos válidos | Mediana válida | Decisión |
|---|---|---:|---:|---|
| Product | GPT OSS 120B / Groq | 33/39 | 3.66 s | Primario |
| Architecture | Mistral Medium | 10/10 | 3.32 s | Primario |
| Architecture | GPT OSS 120B / Groq | 21/21 | 1.07 s | Primer fallback |
| Architecture | Gemini 3.6 Flash | 13/52 | 4.51 s | Fuera del default; 36 límites de cuota |
| Developer | Codestral | 12/15 | 26.67 s | Primario; además pasó aceptación nueva |
| Developer | Mistral Medium | 0/10 | — | Excluido de este rol |
| Developer | Gemini 3.5 Flash | 11/30 | 46.97 s | Último fallback; cuota y latencia inestables |
| Developer | Gemini 3.6 Flash | 8/53 | 23.79 s | Fuera del default; 36 cuotas y 8 indisponibilidades |
| Developer | GPT OSS 120B / Groq | 11/29 | 3.11 s | Primer fallback rápido; 8 rechazos de tamaño/petición |
| Developer | Qwen 3.6 27B / Groq | 0/3 | — | Excluido |
| Developer | North Mini Code free / OpenRouter | 0/3 | — | Excluido |
| Security | Nemotron 3 Super free / OpenRouter | 11/11 | 5.08 s | Primario |
| Security | GPT OSS 120B / Groq | 26/27 | 1.17 s | Primer fallback |

No se promovieron Gemini Pro, 3.7 ni aliases recientes por el nombre: las pruebas
anteriores no demostraron una ruta fiable con esta cuenta. Tampoco se reincorporó
Gemini 2.5 Flash, que había respondido 404. Estos son resultados de esta cuenta y
fecha, no afirmaciones universales sobre los modelos.

## Prueba nueva de generación de código

`probe_models.py --authorize-writes` reconstruye el mismo caso de recuperación
desde el baseline, en copias aisladas dentro de `evidence/`. Prepara Product y
Architecture de forma determinista, llama al Developer real y ejecuta tanto los
tests del código generado como la aceptación independiente. Es una comparación
aislada del Developer, **no** una sustitución de la demo de siete casos.

| Candidato | Contrato | Tests fuente + aceptación | Tiempo total | Decisión |
|---|---|---|---:|---|
| `mistral:codestral-latest` | Válido | Ambos pasan | 26.04 s | Incorporado |
| `mistral:mistral-small-latest` | Válido | Ambos pasan | 23.66 s | Incorporado como alternativa |
| `mistral:devstral-latest` | Timeout | No ejecutados | 90.32 s | No incorporado |
| `openrouter:minimax/minimax-m3:free` | Respuesta truncada | No ejecutados | 94.67 s | No incorporado |
| `openrouter:nvidia/nemotron-3-super-120b-a12b:free` | Fallo de esquema | No ejecutados | 69.98 s | No usar para Developer |
| Mismo Nemotron, salida 16k y razonamiento bajo | Contradicción del artefacto | No ejecutados | 122.99 s | Tampoco usar para Developer |
| `google:gemini-3.5-flash` | Timeout | No ejecutados | 90.26 s | Último recurso; historial mixto, no descartado como siempre fallido |

Evidencia: `evidence/models-20260828-163058/` y
`evidence/models-20260828-163608/` y `evidence/models-20260828-165717/`. Se dejaron pausas de 10 segundos entre
candidatos. Una aprobación aislada no demuestra robustez general: los siete casos
y sus reintentos se documentan por separado en `VALIDATION.md`.

Cada copia conserva el README usado en esa prueba. Durante la calibración se
aclararon prompts y fixtures; los tiempos entre campañas no constituyen una
comparación controlada con entradas idénticas.

## Cadenas activas por defecto

| Rol | Orden |
|---|---|
| Product | Groq GPT OSS 120B → Mistral Small → OpenRouter Nemotron Super free → Gemini 3.5 Flash |
| Architecture | Mistral Medium → Groq GPT OSS 120B → OpenRouter Nemotron Super free → Gemini 3.5 Flash |
| Developer | Codestral → Groq GPT OSS 120B → Mistral Small → Gemini 3.5 Flash |
| Security | OpenRouter Nemotron Super free → Groq GPT OSS 120B → Mistral Small → Gemini 3.5 Flash |
| Testing / Reviewer | Deterministas; no invocan modelos |

Los fallbacks menos usados conservan menos evidencia por rol. Se prioriza la
evidencia observada sobre distribuir artificialmente los primarios entre cuatro
proveedores. Architecture y Developer comparten Mistral; ambos salen a otro
proveedor en su primer fallback. Developer no incluye un modelo OpenRouter que
haya fallado solo para completar una columna.

En este setup los modelos deben preservar los hechos gobernados por el sistema.
Security conserva hallazgos/checklists derivados de reglas y scanners; Testing y
Reviewer usan resultados reales y reglas deterministas. Esta evaluación no prueba
que un LLM descubra por sí solo todas las vulnerabilidades posibles.

## Qué significa gratuito

- **OpenRouter:** la clave devolvió `is_free_tier=true`; el catálogo confirmó
  precios de entrada/salida iguales a cero para el Nemotron `:free` seleccionado.
  Las peticiones exigen endpoints compatibles y `max_price` de tokens a cero.
  Las cuotas y la disponibilidad upstream siguen aplicando; gratuito no significa
  ilimitado. [Límites oficiales](https://openrouter.ai/docs/api_reference/limits).
- **Mistral:** `codestral-latest`, `mistral-small-latest` y `mistral-medium-latest`
  están disponibles en el catálogo de la clave y respondieron. El modo gratuito
  depende del plan de la cuenta, no del sufijo del ID. El endpoint administrativo
  de cuotas devolvió 401: **no se pudo certificar que esta cuenta esté en modo
  gratuito**, y no se cambió su plan. Verificar en Studio antes de una exposición
  prolongada. [Activación y modo gratuito](https://docs.mistral.ai/getting-started/quickstarts/studio/activate-and-generate-api-key).
- No se habilitaron pagos, upgrades ni rutas pagadas de OpenRouter. El envío de
  código a proveedores está sujeto a sus políticas; esta demo usa datos ficticios.
  [Controles de datos de Mistral](https://docs.mistral.ai/admin/monitor-comply/privacy-data-controls).

## Protecciones incorporadas

1. Esquema JSON estricto en Mistral y en el Nemotron de OpenRouter. Para código,
   el esquema fija los caminos autorizados y hechos gobernados; el runtime valida
   además contratos, sintaxis Python y contradicciones. No predetermina el código.
   [API Mistral](https://docs.mistral.ai/api/endpoint/chat).
2. 401/402/403 deshabilitan ese proveedor durante el runtime del run; 429/503
   enfrían **solo el modelo**. Un 429 de Gemini 3.6 no demuestra que 3.5 esté caído.
   Se respeta `Retry-After` numérico o fecha HTTP; sin cabecera se usan 30 segundos.
3. Sin credencial, la ruta se omite. Una salida truncada, JSON inválido o un
   contrato contradictorio se registra y permite intentar el siguiente candidato.
4. Presupuesto compartido `CLOUD_ROLE_TIMEOUT_SECONDS=120` antes de iniciar nuevos
   intentos. En la demo se usa `LLM_TIMEOUT_SECONDS=45` y timeout local de 45 s.
   HTTPX limita inactividad, no tiempo absoluto: una respuesta que siga llegando
   puede superar esos tiempos. No se promete un límite duro de 120 segundos.
5. Los reintentos reciben el diagnóstico acotado del reviewer, incluyendo la
   excepción de tests; antes solo recibían una razón genérica. No se amplían sus
   permisos de herramientas. Se mantienen los checks de secretos antes del envío.
6. Un requisito explícitamente inseguro pasa por Security y Reviewer y se deriva
   a revisión humana sin tres reparaciones inútiles. Los errores reparables del
   scanner siguen permitiendo correcciones. Rechazar nunca autoriza aplicar código.

Las variables `CLOUD_CHAIN_*` permiten cambiar el orden. Los antiguos pools
`GEMINI_MODELS`/escape se conservan por compatibilidad, pero ya no seleccionan la
cadena. Los aliases pueden cambiar de versión; repetir esta evaluación antes de
una demo importante y conservar sus evidencias.

## Resultado de la ejecución completa

La campaña `evidence/20260828-172104/` completó los siete casos desde el baseline:
cinco aplicaciones verificadas y dos rechazos esperados. Necesitó dos reintentos
por tests generados incorrectamente; no fueron fallos de transporte ni se
aplicaron sus cambios. El fallback entre proveedores no corrige por sí solo
errores lógicos del código o de sus tests.

OpenRouter respondió 429 en varios pasos de Security y Groq permitió continuar.
En el caso 7, Groq también agotó cuota: Mistral Small cubrió Product, Developer y
Security. Developer llegó a Small después de un JSON inválido de Codestral y
omitió Groq, que seguía en enfriamiento. Esta es evidencia de recuperación real,
no solo una simulación de tests. Nemotron sigue siendo útil para Security, pero
su plan gratuito no sostiene por sí solo campañas repetidas sin agotar cuota.

La demo duró **24 min 37 s** incluyendo lectura y pausas; la ejecución acumulada
de los nueve intentos fue **9 min 55 s**. Ver [VALIDATION.md](VALIDATION.md) para
trazas, reintentos, pruebas independientes y la restauración final. Mistral
mejoró la continuidad, pero su gratuidad en esta cuenta sigue sin verificarse.
