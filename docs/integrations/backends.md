# Backend adapters: Odysseus and compatible backends

WorkspaceGuard's core isolation and metering logic (`chat()`, quota checks,
the circuit breaker, usage recording) never talks to a specific backend
directly. Every outbound call goes through the `BackendAdapter` interface:

```python
class BackendAdapter(ABC):
    name: str

    async def health_check(self) -> bool: ...
    async def forward_chat(self, workspace_id: str, message: str) -> str: ...
```

(TypeScript: the equivalent `BackendAdapter` interface in
`src/core/types.ts`, with `healthCheck()` / `forwardChat()`.)

"Odysseus and compatible backends" means concretely: any self-hosted AI
assistant your adapter's `forward_chat()` can reach and get a response
from. WorkspaceGuard's isolation and quota semantics don't inspect or care
what's on the other side of that call -- Odysseus is the deployment this
project was originally built against, but the adapter boundary is generic.

## What actually ships today

**Only `MockAdapter` exists right now**, in both distributions
(`workspaceguard/adapters/mock.py` / `src/adapters/mock.ts`). It's an
in-memory stand-in used by the test suite and for local experimentation --
`forward_chat()` just echoes the message back (`"echo: <message>"`) and
records it in memory; nothing leaves the process.

**A real Odysseus HTTP adapter has not been built yet.** It's blocked on an
open feasibility question: does Odysseus's HTTP API expose clean
interception points for a sidecar to sit in front of, or does it
read/write some of its own state (chat history, sessions) directly to
disk/DB in a way an HTTP-level reverse-proxy adapter can't see or
influence? Building the adapter before answering that would risk shipping
something that looks like it works in a demo but silently misses real
traffic in production. This is tracked as the concrete next step for this
project, not shipped as a placeholder claim.

## Writing your own adapter

Because the interface is generic, you can write a working adapter today
for any backend you can reach programmatically, without waiting on the
Odysseus-specific work above:

```python
import httpx
from workspaceguard import BackendAdapter

class MyBackendAdapter(BackendAdapter):
    name = "my-backend"

    def __init__(self, base_url: str) -> None:
        self._client = httpx.AsyncClient(base_url=base_url)

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get("/health")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def forward_chat(self, workspace_id: str, message: str) -> str:
        resp = await self._client.post(
            "/chat", json={"workspace_id": workspace_id, "message": message}
        )
        resp.raise_for_status()
        return resp.json()["reply"]
```

Then pass an instance to `create_workspace_guard()`:

```python
guard = await create_workspace_guard(data_dir="./data", backend=MyBackendAdapter("http://localhost:8080"))
```

Everything downstream -- identity resolution, quota enforcement, the
circuit breaker, usage recording -- works identically regardless of which
adapter you pass in, since none of it depends on backend-specific
behavior. `forward_chat()` raising any exception is treated as a backend
failure by the circuit breaker (3 consecutive failures opens the circuit);
there's no special-casing required in your adapter for that.

## Trust boundary reminder

Whatever backend you point WorkspaceGuard at, the identity header trust
boundary described in [concepts.md](../concepts.md#trust-boundary) still
applies: WorkspaceGuard itself must never be directly reachable from the
network, only from behind whatever trusted proxy authenticates the caller
and sets the identity header.
