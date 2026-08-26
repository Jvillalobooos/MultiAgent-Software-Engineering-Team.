# Ejecuciones autónomas sobre Sample App

## Propósito

Esta arquitectura hace que las ejecuciones normales se orienten a `sample_app`
y concluyan con un resultado automático explícito.
La meta es que el equipo pueda aplicar y validar requerimientos viables sin
quedarse bloqueado en `HUMAN_REVIEW_REQUIRED` cuando una iteración no produce
progreso.

## Alcance

- El destino predeterminado de `run.ps1`, `run.sh` y `nova-team run` será
  `<raíz-del-repositorio>/sample_app`.
- `--project <ruta>` se conserva como una anulación explícita para trabajar
  sobre otra carpeta existente.
- Cada ejecución seguirá creando una copia aislada del destino bajo
  `workspace/runs/<run_id>`; la carpeta origen nunca se modifica.
- Product y Architecture escribirán documentación de sus decisiones dentro de
  la copia aislada.
- Las salidas normales terminarán como `APPROVED` o `INCOMPLETE`.

## Selección de destino

La resolución del destino tendrá esta prioridad:

1. El valor suministrado mediante `--project <ruta>`.
2. La carpeta `sample_app` incluida en el repositorio.

El reporte JSON conservará tanto `target_project` como `workspace`, para que
sea posible distinguir el proyecto fuente de la copia que recibió los cambios.

## Resultado de la ejecución

| Estado | Significado | Acción posterior |
| --- | --- | --- |
| `APPROVED` | El Developer aplicó cambios mediante MCP, las validaciones requeridas terminaron y Reviewer aprobó la entrega. | Usar el diff y los artefactos de la copia aislada. |
| `INCOMPLETE` | No fue posible completar el requerimiento de forma segura: no hubo progreso, se agotaron los ciclos de remediación, hubo una ruta inválida o faltó una dependencia obligatoria. | Revisar `final_report`, `errors`, `route_history` y `tools_used`; ajustar el requerimiento o el proyecto y ejecutar otra corrida. |

`HUMAN_REVIEW_REQUIRED` dejará de ser el estado final de las ejecuciones no
interactivas. Los límites de reintento permanecen: evitan bucles indefinidos,
pero su salida será `INCOMPLETE` y conservará toda la evidencia diagnóstica.

## Escrituras del Developer

Developer podrá crear o actualizar archivos solamente por medio de Repository
MCP y solamente dentro del workspace de la corrida. Antes de escribir, el
archivo debe haber sido inspeccionado y debe ser una ruta segura, relativa y no
secreta. Una implementación se considerará aplicada únicamente si:

1. el Developer entrega mutaciones concretas para archivos inspeccionados;
2. Repository MCP confirma al menos una escritura satisfactoria; y
3. `get_diff` devuelve un diff no vacío.

Si no existe un cambio viable o falta evidencia suficiente para escribir, el
motor no inventará una mutación. Tras las remediaciones permitidas finalizará
como `INCOMPLETE` con el motivo correspondiente.

## Documentación generada por los agentes

En cada workspace se crearán estos archivos:

| Agente | Archivo | Contenido |
| --- | --- | --- |
| Product | `docs/decisions/product-specification.md` | Requerimiento fuente, objetivo, actores, reglas, restricciones, criterios de aceptación, ambigüedades y supuestos. |
| Architecture | `docs/decisions/architecture-decisions.md` | Componentes, APIs, cambios de datos, integraciones, dependencias, decisiones, riesgos e información de evidencia. |

Los archivos se generan a partir de artefactos Pydantic ya validados. Si no
pueden escribirse, se registrará un error de workflow y la ejecución terminará
como `INCOMPLETE`; nunca se informará una aprobación sin esos artefactos.

## Verificación prevista

La verificación cubre la selección predeterminada de `sample_app`, la anulación
con `--project`, el resultado `INCOMPLETE`, las dos piezas de documentación
generada y una mutación real de Developer en una copia aislada. La prueba
funcional usa el requisito “crea una forma para poder cambiar la contraseña”
contra `sample_app` y comprueba que el resultado final no sea
`HUMAN_REVIEW_REQUIRED`.
