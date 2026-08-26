# LangGraph diagram

```mermaid
flowchart TD
    S([START]) --> P[Product]
    P --> A[Architecture]
    A --> D[Developer]
    D -->|full or security changed| SEC[Security]
    D -->|testing-only and no security change| T[Testing]
    SEC -->|non-critical| T
    SEC -->|CRITICAL| SH[security_hitl]
    T --> R[Reviewer]
    R -->|APPROVED| F[FinalReport]
    R -->|Architecture issue| A
    R -->|Implementation / Security issue| D
    R -->|Testing caused by code| D
    R -->|third rejection / invalid route| I[INCOMPLETE]
    SEC -->|CRITICAL, non-interactive| I
    SH --> E([END])
    I --> E
    F --> E
```

The Reviewer recommends; deterministic validation selects the edge. Iteration
increments exactly once per accepted rejection. Iterations 1 and 2 may loop;
the third rejection terminates automation as `INCOMPLETE`, so a fourth cycle
cannot start. LLM availability/quality errors use bounded retry/repair/fallback
routes; MCP, tool and RAG errors keep dedicated non-cloud paths and terminate
as `INCOMPLETE` when no recovery path remains. Interactive security HITL still
uses `security_hitl` with a checkpointer.
