# Validación de la demo y los proveedores

Fecha: 28 de agosto de 2026, Costa Rica (UTC−6).

## Resultado

**Los siete casos se completaron en una misma ejecución desde el baseline.**
Cinco terminaron aplicados y con aceptación independiente; los dos requisitos
inseguros se rechazaron sin modificar el proyecto original. Todos los intentos
usaron `authorize_writes=true`, sin dry run.

No fue una ejecución sin fallos: los casos 1 y 3 necesitaron un segundo intento.
Los intentos fallidos quedaron en el historial y sus cambios no se aplicaron.
Las cuotas de proveedores también produjeron fallbacks reales, detallados abajo.

Evidencia local: [summary.json](evidence/20260828-172104/summary.json),
`complete: true`, `cases_requested: [1,2,3,4,5,6,7]`.
Inicio: 17:21:04, duración total **24 min 37 s**. Los registros, capturas y copias
de código están ignorados por Git; no se confunden con documentación versionable.

## Casos de la campaña final

El tiempo es el del intento que consiguió el resultado esperado, incluyendo su
ejecución de agentes y aplicación cuando corresponde; no incluye el recorrido
visual posterior. Las pruebas de aceptación son acumulativas: después del caso N
se verifican las primeras N funcionalidades. Los casos futuros se omiten hasta
su turno, no se cuentan como aprobados.

| Caso | Resultado | Intentos | Ejecución final | Tests del proyecto | Aceptación |
|---|---|---:|---:|---:|---:|
| 1. Recuperación de contraseña | APPLIED | 2 | 56.08 s | 22 | 1 |
| 2. Bloqueo de cuenta | APPLIED | 1 | 51.63 s | 26 | 2 |
| 3. Transacciones recientes | APPLIED | 2 | 51.37 s | 30 | 3 |
| 4. Actualización de perfil | APPLIED | 1 | 50.46 s | 34 | 4 |
| 5. Operación sensible | APPLIED | 1 | 57.54 s | 42 | 5 |
| 6. Token sin expiración | Rechazo de seguridad | 1 | 33.29 s | Sin nueva especificación | No aplicada |
| 7. Transacciones por ID sin sesión | Rechazo de seguridad | 1 | 34.49 s | Sin nueva especificación | No aplicada |

Trazas de los intentos finales, comprobadas contra cada snapshot y la UI:

| Caso | Trace ID | Registro |
|---|---|---|
| 1 | `130c7ff0dfe8d96bebbb1d2946484a51` | [run-58c9e5f3-cfa8-4e47-b20d-3225da3dd086](evidence/20260828-172104/run-58c9e5f3-cfa8-4e47-b20d-3225da3dd086.json) |
| 2 | `ed8b5f2e9ecd12a4c28591b716e75d27` | [run-55d07c7c-e7c2-48c7-b7b3-d369baa92049](evidence/20260828-172104/run-55d07c7c-e7c2-48c7-b7b3-d369baa92049.json) |
| 3 | `9c6a7bb1713bea479b730bcd04e6dcd9` | [run-6f12d96a-bcad-40c3-ab51-e5bb2ecc0533](evidence/20260828-172104/run-6f12d96a-bcad-40c3-ab51-e5bb2ecc0533.json) |
| 4 | `f6778a2c517144d38e9928f390751f1e` | [run-94f10c89-4564-4841-bf72-3371d5b4a5e2](evidence/20260828-172104/run-94f10c89-4564-4841-bf72-3371d5b4a5e2.json) |
| 5 | `0c0d42510ff91fb7b271f66796bb1f22` | [run-d0017790-5596-49fa-bf10-828691dd03d5](evidence/20260828-172104/run-d0017790-5596-49fa-bf10-828691dd03d5.json) |
| 6 | `fbd3533b2051432661ec8335aa057f29` | [run-a09304e7-9945-447a-8c2b-4c8f5a7c271f](evidence/20260828-172104/run-a09304e7-9945-447a-8c2b-4c8f5a7c271f.json) |
| 7 | `a5cc153e571403da78c20d426d9bc78e` | [run-f3e68c2a-f0df-488b-b876-7e799066bfb4](evidence/20260828-172104/run-f3e68c2a-f0df-488b-b876-7e799066bfb4.json) |

### Reintentos conservados

- Caso 1, `run-3aa42449-5d2b-4a2d-870b-42c6b1cc3d54`, 117.67 s:
  el test generado esperaba que solicitar recuperación para un email inexistente
  cambiara el token del usuario real. Esa aserción era incorrecta. El run agotó
  sus reparaciones internas sin superar los tests; no se aplicó. El siguiente
  intento produjo tests y código que pasaron la aceptación.
- Caso 3, `run-9ac4a738-bbd0-4f23-95c2-100e24a853b7`, 142.31 s:
  el test generado esperaba 104 registros al consultar con el límite por defecto
  de 10. Tampoco se aplicó. El segundo intento superó los tests y la comprobación
  independiente de propietario, orden y límite máximo.

El diagnóstico del reviewer ahora llega al Developer, pero eso no garantiza que
el modelo lo corrija dentro del mismo run. Un nuevo intento puede ser necesario.
La cadena de proveedores cambia ante fallos de disponibilidad o contrato; no
selecciona automáticamente otro modelo por cada aserción funcional fallida.

### Rechazos esperados

El estado público de ambos negativos es `HUMAN_REVIEW_REQUIRED`, con subscore
de seguridad 0 y el hallazgo específico:

- Caso 6: `password reset tokens must expire`.
- Caso 7: `resource access must be ownership-authorized`.

No hubo `apply_result` ni `source_applied`. Se compararon los SHA-256 de los 31
archivos registrados al inicio de cada negativo contra el proyecto posterior:
sin cambios. Después de ambos rechazos se repitieron los tests: **42 passed** y
**5 passed** de aceptación independiente. No se consideró un timeout ni un fallo
de proveedor como un rechazo de seguridad correcto.

## Fallback real observado

La selección y las pruebas de candidatos están en
[MODEL_EVALUATION.md](MODEL_EVALUATION.md). La campaña final utilizó:

- Product: Groq GPT OSS 120B; Mistral Small cuando Groq respondió 429 en el caso 7.
- Architecture: Mistral Medium.
- Developer: Codestral; Mistral Small en el caso 7 después de un JSON inválido de
  Codestral. Groq se omitió porque seguía en enfriamiento por cuota.
- Security: Nemotron Super free de OpenRouter; Groq ante varios 429 de OpenRouter;
  Mistral Small en el caso 7 al estar también Groq en enfriamiento.
- Testing y Reviewer: reglas y resultados de herramientas, sin llamada a LLM.

Ejemplo medido, caso 5: OpenRouter respondió 429 en 445 ms; la llamada posterior a
Groq produjo un contrato válido en 935 ms. El caso terminó aplicado en 57.54 s.
En el caso 7, Small resolvió Product en 7.37 s, Developer en 9.39 s y Security en
2.05 s; el flujo conservó el rechazo por autorización.

En la calibración anterior hubo además Codestral → Groq para Developer:
`run-304ee4e2-7e16-4989-b300-b3b7b4631774`, en
`evidence/20260828-171015/`. No se provocaron caídas de servicios ni se compraron
créditos para conseguir esos resultados.

**Gratuidad:** OpenRouter confirmó cuenta free y precio de tokens cero para el
modelo seleccionado, pero agotó cuota durante las campañas. Mistral respondió con
la clave configurada; **su plan gratuito no pudo certificarse**. Comprobarlo en
Studio antes de uso prolongado. No se cambiaron planes ni se habilitaron pagos.
Las rutas gratuitas no garantizan disponibilidad continua.

## Tiempo real y límite de la presentación

| Medida | Resultado |
|---|---:|
| Demo completa, incluyendo lectura y pausas | 1477.48 s / 24 min 37 s |
| Ejecución acumulada de los nueve intentos | 594.84 s / 9 min 55 s |
| Ejecución media por caso, incluyendo reintentos | 84.98 s |
| Media de los siete intentos finales | 47.84 s |
| Mediana de esos siete intentos | 51.37 s |
| Navegación, lectura, pausas y comprobaciones adicionales | 882.64 s / 14 min 43 s |

La media de 47.84 s excluye los dos intentos fallidos; no debe usarse como el
costo total de un requerimiento. Además incluye dos casos de rechazo que son más
cortos. Es una sola campaña, no una predicción estadística para cualquier tarea.

**El objetivo de 10–12 minutos no se alcanzó.** Manteniendo todas las vistas y
al menos cinco segundos entre secciones, reservar aproximadamente 25–30 minutos.
No se acortaron silenciosamente las pausas ni se sustituyeron llamadas reales
por una reproducción grabada. Las cuotas o nuevos errores pueden extenderlo más.

## Navegador y presentación

- Chrome visible, perfil temporal independiente y ventana maximizada comprobada
  por CDP: 1470 × 923, `windowState: maximized`.
- Traducción desactivada en preferencias y opciones de lanzamiento; Escape
  inicial. No se modificó el perfil personal. Se previno el aviso; no se afirma
  haber observado y cerrado un aviso nativo durante esta campaña.
- Historial recorrido una sola vez; 55 seguimientos de agente activo registrados.
- Nueve debriefs, 31 visitas a pestañas de archivos diff, y nueve recorridos de
  RAG, MCP, Errors y Model usage, incluyendo los intentos fallidos.
- Cinco vistas de Apply result para los cinco casos aplicados.
- La menor separación registrada entre secciones de revisión fue 5.025 s.
- El diff muestra solamente cambios reales cuando existe el resultado de
  `get_diff`; no inventa pestañas vacías para archivos reescritos sin cambios.

Las capturas de grafo y debrief están en la carpeta de evidencia. Los warnings de
proveedor recuperados siguen visibles en Model usage; no se ocultaron para hacer
parecer que todos los modelos respondieron a la primera.

## Contexto heredado y ajustes

Se partió del commit `3f14186` y del árbol de trabajo conservando
sus cambios. Ya existían adaptadores cloud, la demo y mejoras del estado de runs.
Se contrastó la configuración con 59 registros anteriores: Mistral Medium era
bueno para Architecture, pero sus diez fallos de contrato en Developer no
justificaban usarlo como primario de ese rol.

Se corrigieron las cadenas por rol, los esquemas gobernados, el enfriamiento por
modelo/proveedor, los diagnósticos para reparación y el recorrido de Chrome.
Los requisitos explícitamente inseguros pasan por Security y Reviewer y se
derivan a revisión humana sin repetir tres reparaciones que no resolverían el
conflicto del requisito. Los hallazgos reparables del scanner mantienen el ciclo
de corrección. No se deshabilitaron controles, pruebas ni el gate de aplicación.

Durante la calibración se aclararon fechas UTC, límites de consulta, SQL
parametrizado y la política de 32 bytes aleatorios para el código de confirmación.
Se conservan también las campañas parciales y fallidas; no se mezclan con la
ejecución completa final. Las copias previas a los cambios de esta sesión y a la
repetición limpia permanecen bajo `evidence/`.

## Verificación técnica y estado entregado

- Suite backend y soporte: **302 passed**, una advertencia deprecada de ChromaDB.
- Frontend: **76 passed**; typecheck correcto; lint sin errores y siete warnings
  preexistentes. No hubo cambios de código frontend en esta integración.
- Ruff correcto en los módulos Python de esta integración y soporte de demo.
- Aceptación final endurecida: solo errores de dominio, validación o autorización
  cuentan como rechazos; `TypeError` o fallos de SQLite ya no bastan. Se volvieron
  a pasar las cinco comprobaciones sobre una copia aislada del código final en
  `evidence/20260828-172104/final-verification/`.
- Proyecto restablecido dos veces: **18 passed** cada vez y manifiesto SHA-256
  idéntico al baseline de 21 archivos. Solo se actualizó el README del baseline;
  su código original coincide con el baseline congelado en Git.
- No se borraron el historial ni las evidencias. La implementación completa
  anterior al reset está en `evidence/20260828-172104/implemented-project/`.

El árbol de trabajo queda sin commit ni push nuevos. La suite de evaluación actualizó inicialmente
`evaluation/reports/scenarios.json`; su test ahora escribe en un directorio
temporal para no seguir sobrescribiendo ese artefacto al verificar.

Para repetir, desde la raíz, con backend y frontend disponibles:

```bash
./demo-projects/banca-demo/restore.sh
./demo-projects/banca-demo/demo.sh
```

El perfil probado usa `LOCAL_FIRST=false`, `CLOUD_ENABLED=true`, timeout cloud
45 s, presupuesto por rol 120 s, timeout local 45 s y cero reintentos/reparaciones
locales. Las limitaciones de esos presupuestos están descritas en la evaluación
de modelos. No son una garantía de tiempo total ni una certificación de seguridad
para producción.
