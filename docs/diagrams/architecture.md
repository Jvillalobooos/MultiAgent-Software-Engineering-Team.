# Architecture diagram

```mermaid
flowchart LR
    U[User / CLI] --> G[LangGraph StateGraph]
    G --> PC[ProjectCapabilities detector]
    PC -->|supported profile fingerprint| A
    PC -->|unknown / ambiguous / missing command| I[INCOMPLETE]
    G --> A[Six specialized agents]
    A --> R[LangChain Document + splitter]
    R --> E[Sentence Transformers + Chroma RAG]
    A --> MC[MCP Client]
    MC --> MS[Repository / Quality MCP Server via stdio]
    A --> O[Ollama 4B / 9B]
    E --> K[Local knowledge documents]
    MS --> W[Isolated run workspace / native build test lint scans]
    G --> L[Langfuse root trace]
    E --> L
    MC --> L
    O --> L
    C[Optional Gemini / Groq fallback] -. governed contingency .-> A
    C --> L
```

Conceptually: User → LangGraph → Agents → RAG / MCP → External Systems →
Langfuse. LangGraph alone owns transitions.
