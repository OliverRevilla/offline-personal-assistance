# packages/shared-contracts

Sigue vacío a propósito. La Fase 6 (frontend, el segundo consumidor real del protocolo WS) ya llegó, pero se decidió duplicar el contrato a mano en `apps/desktop/src/lib/protocol.ts` (TypeScript) en vez de generarlo desde acá — ver [docs/adr/0008-frontend-nativo-windows-y-stack-tauri.md](../../docs/adr/0008-frontend-nativo-windows-y-stack-tauri.md). Montar un pipeline de codegen (Pydantic → JSON Schema → TS) es infraestructura real que todavía no se justifica sin evidencia de que la duplicación manual ya causó un bug por divergencia.

Si en algún momento el protocolo diverge entre `app/api/ws.py` y `protocol.ts` de forma que cause un bug real, esa es la señal para poblar este paquete — no antes.

Owner: `integration-engineer` (coordina con `backend-engineer` y `frontend-engineer`).
