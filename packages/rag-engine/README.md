# packages/rag-engine

Todavía no hay código acá. En la Fase 2 el chunking/embeddings/indexación/búsqueda se implementó directamente en `apps/orchestrator/app/rag/` (único consumidor hoy, y evita la complejidad de un build de Docker que dependa de un paquete local fuera del contexto de build del orchestrator).

Extraer esa lógica a este paquete solo tiene sentido si aparece un segundo consumidor real (ej. un CLI de benchmarks de recall/latencia corrido fuera del orchestrator) — no antes.

Owner: `lead-ai-engineer`.
