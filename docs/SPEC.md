# failsight — Technical Specification (v0.1)

Status: **Approved (2026-10-14)** · Last updated: 2026-10-14
Related: [PRD.md](PRD.md) · [DESIGN.md](DESIGN.md) · [PLAN.md](PLAN.md)

This document defines the **contracts between components**. Tasks in [PLAN.md](PLAN.md) are built in parallel against these contracts, so:

> **Agents must not change a contract in this file on their own.** If a task needs a change, stop and open a PR/issue titled `SPEC CHANGE REQUEST: …` explaining why. The owner approves, then SPEC.md is updated in its own PR.

Conventions used throughout:
- JSON field names are `snake_case` everywhere (wire, REST, SSE, export, UI types).
- Timestamps are **Unix epoch milliseconds as float** (`ts`, `started_at`, `ended_at`), e.g. `1760430000123.456`. Safe for JavaScript numbers.
- IDs are lowercase hex: `trace_id` = 32 chars, `span_id` = 16 chars (OpenTelemetry-compatible). Generated with `secrets.token_hex`.

---

## 1. Package Structure & Dependency Rules

```
src/failsight/
├─ __init__.py          # public API re-exports (see §2.1)
├─ protocol.py          # enums, event TypedDicts, PROTOCOL_VERSION — shared by SDK & server
├─ errors.py            # public exception types
├─ sdk/                 # tracing: config, context, spans, decorators, payload, exporter
├─ resilience/          # policies + executor (no tracing imports, see below)
├─ integrations/
│  └─ langgraph/
├─ server/              # FastAPI app, routes/, storage/, live (SSE broker), otlp
├─ demo/                # demo workflow, mock LLM/tools, chaos
└─ cli.py
```

Import rules (enforced in review, and by a test that inspects imports):
- `protocol.py`, `errors.py`: stdlib only.
- `resilience/`: stdlib + `protocol`/`errors` only. It reports what happens through a **hooks** object (§3.7); it never imports `sdk/`.
- `sdk/`: stdlib + `protocol`/`errors`/`resilience` only. **Never imports `fastapi`, `uvicorn`, `pydantic` or `server/`.** (Users' apps load the SDK; it must stay light.)
- `server/`: may import anything in the package except `demo/` and `integrations/`.
- `integrations/*`: may import `sdk/` and its framework; the framework is an optional extra.

## 2. SDK Public API

### 2.1 Exports (`import failsight as fs`)

```python
fs.init, fs.shutdown, fs.flush
fs.trace, fs.agent, fs.tool, fs.llm, fs.span, fs.current_span
fs.Retry, fs.Timeout, fs.CircuitBreaker, fs.Fallback
fs.CircuitOpenError, fs.FailsightTimeoutError, fs.FailsightError
fs.__version__
```

### 2.2 Configuration

```python
def init(
    project: str | None = None,            # default: env FAILSIGHT_PROJECT, else "default"
    endpoint: str | None = None,           # default: env FAILSIGHT_ENDPOINT, else "http://127.0.0.1:7317"
    *,
    enabled: bool | None = None,           # default: not env FAILSIGHT_DISABLED in ("1","true","yes")
    capture_payloads: bool = True,
    max_payload_bytes: int = 32_768,
    redact: Callable[[Any], Any] | None = None,   # applied after default redaction (§2.6)
    exporter: Exporter | None = None,      # override (tests use an in-memory exporter)
) -> None
def shutdown(timeout: float = 2.0) -> None    # flush and stop the exporter
def flush(timeout: float = 2.0) -> bool       # True if everything was sent
```

- `init()` may be called more than once; the last call wins (the old exporter is shut down).
- **Without `init()`:** tracing is a no-op **unless** `FAILSIGHT_ENDPOINT` or `FAILSIGHT_PROJECT` is set, in which case the SDK lazily auto-initializes from env on the first span.
- **When tracing is disabled or not initialized, resilience policies still work exactly the same.**
- An `atexit` handler calls `shutdown(timeout=2.0)`.

### 2.3 Decorators and context managers

```python
def trace(name: str | None = None, *, project: str | None = None)   # decorator AND context manager
def agent(name: str | None = None, *, retry=None, timeout=None, breaker=None, fallback=None)
def tool (name: str | None = None, *, retry=None, timeout=None, breaker=None, fallback=None)
def llm  (name: str | None = None, *, model: str | None = None, retry=None, timeout=None, breaker=None, fallback=None)
def span (name: str, *, kind: SpanKind = "chain")                   # context manager only
def current_span() -> Span | None
```

- Each decorator works on **sync and async functions**, used bare (`@fs.tool`) or called (`@fs.tool(...)`). Default `name` = function `__qualname__`.
- `trace` always starts a **new trace** whose root span has `kind="chain"`. Any other span started with no active span **implicitly starts a new trace** with itself as root.
- Generators/async generators are **not supported in v0.1**: decorating one raises `TypeError` at decoration time with a clear message.
- Decorated functions get attribute `__failsight__ = {"kind": ..., "name": ...}` (used by fallback detection, §3.5).
- `llm(model=...)` sets attribute `gen_ai.request.model` on the span.
- Policy arguments accept the policy objects from §3. `fallback` also accepts a plain callable (wrapped as `Fallback(fn)`).

### 2.4 Span handle

```python
class Span:
    trace_id: str; span_id: str; name: str; kind: SpanKind
    def set_attribute(self, key: str, value: AttrValue) -> None
    def set_attributes(self, attrs: Mapping[str, AttrValue]) -> None
    def add_event(self, name: str, attributes: Mapping[str, AttrValue] | None = None) -> None
    def record_llm_usage(self, *, model: str | None = None,
                         input_tokens: int | None = None, output_tokens: int | None = None) -> None
# AttrValue = str | int | float | bool | None | list[str | int | float | bool]
```

`record_llm_usage` sets `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`. Attributes set during the span are sent with `span_end`.

### 2.5 Context propagation
- Current span is held in a `contextvars.ContextVar`. Works across `await` and `asyncio` tasks (tasks copy context at creation).
- Threads started by user code do **not** inherit context (Python behaviour); spans there start new traces. Documented limitation; a helper is P2.
- The SDK's own worker threads (sync timeouts, §3.3) **do** run inside `contextvars.copy_context()`.

### 2.6 Payload capture
- **Input** = the bound arguments as a dict `{param_name: value}` (via `inspect.signature(...).bind`), excluding `self` and `cls`.
- **Output** = the return value.
- Conversion to JSON-compatible values, in order: JSON primitives as-is; `dict`/`list`/`tuple`/`set` recursively; pydantic-like objects with `model_dump()`; dataclasses via `dataclasses.asdict`; anything else → `repr(value)` truncated to 1,000 chars. Max depth 10 (deeper → `"<max depth>"`).
- **Default redaction:** any dict key matching `(?i)(api[_-]?key|token|secret|password|passwd|authorization|cookie)` → value replaced with `"[REDACTED]"`. Then the user's `redact` hook runs on the converted value.
- **Truncation:** if the JSON encoding exceeds `max_payload_bytes`, replace with `{"__truncated__": true, "size": <bytes>, "preview": "<first 1,000 chars of the JSON>"}`.
- `capture_payloads=False` → `input`/`output` are `null`.
- Any exception during capture → payload becomes `{"__capture_error__": "<exception type>"}`; never propagates.

### 2.7 Safety rules (NFR-1)
- No failsight-internal exception may escape into user code. Only the user's own exceptions and the documented resilience errors (§3.6) propagate.
- Internal errors are logged via `logging.getLogger("failsight")` at WARNING, **rate-limited to one message per error type per 60 s**.

## 3. Resilience Semantics

### 3.1 Composition order
Outermost → innermost: **`Fallback → CircuitBreaker → Retry → Timeout → call`**. Any policy may be omitted.

### 3.2 Retry
```python
Retry(attempts: int = 3, *, backoff: Literal["fixed", "exponential"] = "exponential",
      base: float = 0.5, max_delay: float = 30.0, jitter: bool = True,
      on: tuple[type[BaseException], ...] = (Exception,),
      retry_if: Callable[[BaseException], bool] | None = None)
```
- `attempts` = **total** attempts, including the first (`attempts=1` means no retry). Must be ≥ 1.
- An error is retryable if `isinstance(err, on)` and (`retry_if is None` or `retry_if(err)`). `CircuitOpenError` is never retried.
- Delay before attempt *n* (n ≥ 2): fixed → `base`; exponential → `min(max_delay, base * 2 ** (n - 2))`. With `jitter=True`: `random.uniform(0, delay)` ("full jitter").
- Sleeping uses `time.sleep` / `asyncio.sleep`, injectable for tests via the executor (§3.7).
- When all attempts fail, the **last** error propagates.

### 3.3 Timeout
```python
Timeout(seconds: float, *, total: float | None = None)
```
- `seconds` applies **per attempt** (inside Retry). `total` bounds the whole Retry loop including delays (checked before each attempt and enforced on the running attempt).
- Async: `asyncio.wait_for` (Python 3.10-compatible).
- Sync: the call runs in a shared `ThreadPoolExecutor` (`max_workers=32`, threads named `failsight-timeout-*`) inside a copied context; the caller waits with `future.result(timeout)`. On timeout the caller gets `FailsightTimeoutError`; **the worker thread cannot be killed and keeps running** (documented limitation).
- `FailsightTimeoutError` subclasses `TimeoutError`, so it is retryable by default.

### 3.4 Circuit breaker
```python
CircuitBreaker(failure_threshold: int = 5, reset_after: float = 30.0, *,
               key: str | None = None, on: tuple[type[BaseException], ...] = (Exception,))
```
- Wraps Retry, so it counts **calls** (a call that fails after all retries = 1 failure).
- States: `closed` → (consecutive failures ≥ `failure_threshold`) → `open` → (after `reset_after` s) → `half_open`.
- `open`: calls fail immediately with `CircuitOpenError` without invoking the function.
- `half_open`: exactly **one** trial call is allowed; concurrent calls during the trial get `CircuitOpenError`. Trial success → `closed` (count reset); trial failure → `open` (timer restarts).
- Only errors matching `on` count as failures; a success resets the consecutive count.
- State is **per process**, in a thread-safe global registry keyed by `key` or, by default, `f"{func.__module__}.{func.__qualname__}"`. Two decorated functions sharing a `key` share one breaker.
- `failsight.resilience.reset_breakers()` clears the registry (for tests).

### 3.5 Fallback
```python
Fallback(fn: Callable[..., Any], *, on: tuple[type[BaseException], ...] = (Exception,))
```
- Triggered when the inner chain raises an error matching `on` (including `CircuitOpenError` and `FailsightTimeoutError`).
- Called with the **same arguments** as the primary. A sync primary needs a sync fallback; an async primary may use a sync or async fallback.
- Span shape: if `fn` is failsight-decorated (`__failsight__` present), it is called directly and creates its own child span; otherwise the SDK wraps the call in a child span named `f"{parent_name}.fallback"` with the parent's kind. Either way the child gets attribute `failsight.fallback_for = <parent span_id>`.
- If the fallback raises, that error propagates; the original error is recorded in the `fallback_invoked` event.

### 3.6 Errors (`failsight/errors.py`)
```python
class FailsightError(Exception): ...
class CircuitOpenError(FailsightError):     # .key: str
class FailsightTimeoutError(FailsightError, TimeoutError):   # .seconds: float
```

### 3.7 Executor & hooks (internal contract between `resilience/` and `sdk/`)
```python
class ResilienceHooks(Protocol):
    def on_attempt_failed(self, attempt: int, max_attempts: int, error: BaseException, delay_s: float) -> None: ...
    def on_timeout(self, attempt: int, seconds: float) -> None: ...
    def on_breaker_transition(self, key: str, old: str, new: str, failures: int) -> None: ...
    def on_short_circuit(self, key: str) -> None: ...
    def on_fallback(self, error: BaseException) -> None: ...

def run_sync(fn, args, kwargs, *, policies: Policies, hooks: ResilienceHooks | None,
             sleep=time.sleep, clock=time.monotonic, rng=random.random) -> Any
async def run_async(fn, args, kwargs, *, policies: Policies, hooks: ResilienceHooks | None,
                    sleep=asyncio.sleep, clock=time.monotonic, rng=random.random) -> Any
```
- `Policies` is a frozen dataclass `(retry, timeout, breaker, fallback)`, all optional.
- `on_attempt_failed` is called only when another attempt **will** follow.
- Fallback **invocation** (calling the fallback, creating its child span) is done by `sdk/` through a callback passed in `Policies`/hooks; the resilience package only decides *when* to fall back. Exact signature is defined by T30 and reviewed in T31.
- Hooks must never raise into the executor (the executor wraps hook calls defensively).

### 3.8 Span status mapping

| Situation | Final span status |
|---|---|
| Returned normally, no fallback | `success` |
| Primary path failed, fallback returned normally | `fallback` |
| Breaker open, no fallback | `short_circuited` (raises `CircuitOpenError`) |
| Final error is `FailsightTimeoutError`, no fallback | `timed_out` |
| Any other final error | `failed` |

Live (non-final) statuses: `running` at start; `retrying` from the first `retry_attempt` event until the span ends. `pending` is reserved (not emitted in v0.1).

## 4. Wire Protocol (SDK → Server)

### 4.1 Enums (`protocol.py`)
- `SpanKind`: `agent`, `tool`, `llm`, `router`, `chain`
- `SpanStatus`: `pending`, `running`, `retrying`, `success`, `failed`, `timed_out`, `fallback`, `short_circuited`
- Final statuses: `success`, `failed`, `timed_out`, `fallback`, `short_circuited`
- Built-in event names: `retry_attempt`, `timeout`, `fallback_invoked`, `breaker_opened`, `breaker_half_open`, `breaker_closed`, `short_circuited`
- `PROTOCOL_VERSION = 1`

### 4.2 Request
`POST /api/ingest` · `Content-Type: application/json` · max body 5 MB (larger → `413`).

```json
{
  "protocol": 1,
  "sdk": {"name": "failsight-python", "version": "0.1.0"},
  "events": [
    {"type": "span_start", "trace_id": "4bf9…", "span_id": "00f0…", "parent_span_id": null,
     "project": "research-bot", "name": "web_search", "kind": "tool", "ts": 1760430000123.4,
     "input": {"query": "llm rate limits"}, "attributes": {},
     "policy": {"retry": {"attempts": 3, "backoff": "exponential", "base": 0.5}, "timeout": {"seconds": 10}}},
    {"type": "span_event", "trace_id": "4bf9…", "span_id": "00f0…", "ts": 1760430000456.7,
     "name": "retry_attempt", "status": "retrying",
     "attributes": {"attempt": 1, "max_attempts": 3, "error_type": "RateLimitError", "error_message": "429", "delay_s": 0.42}},
    {"type": "span_end", "trace_id": "4bf9…", "span_id": "00f0…", "ts": 1760430001789.0,
     "status": "success", "output": ["…"], "error": null,
     "attributes": {"gen_ai.usage.input_tokens": 120}}
  ]
}
```

| Event | Required fields | Optional |
|---|---|---|
| `span_start` | `trace_id, span_id, project, name, kind, ts` | `parent_span_id, input, attributes, policy` |
| `span_event` | `trace_id, span_id, ts, name` | `attributes, status` (live status change) |
| `span_end` | `trace_id, span_id, ts, status` (final) | `output, error, attributes` (merged into existing) |

`error` = `{"type": "RateLimitError", "message": "…", "stacktrace": "…"}` (stacktrace ≤ 16 KB).
`policy` = JSON form of the applied policies, e.g. `{"retry": {...}, "timeout": {...}, "breaker": {"failure_threshold": 5, "reset_after": 30, "key": "…"}, "fallback": {"fn": "module.qualname"}}`.

Built-in event attributes:
| Event | Attributes |
|---|---|
| `retry_attempt` | `attempt, max_attempts, error_type, error_message, delay_s` |
| `timeout` | `attempt, seconds` |
| `fallback_invoked` | `error_type, error_message` |
| `breaker_opened` / `breaker_half_open` / `breaker_closed` | `key, failures` |
| `short_circuited` | `key` |

### 4.3 Response & server rules
- `202 {"accepted": <n>, "rejected": <m>}`. Malformed JSON or wrong top-level shape → `400`. Unknown `protocol` → `400`.
- Individually invalid events are skipped and counted in `rejected` (never fail the batch).
- `span_start` is idempotent (duplicate `span_id` within a trace → ignored).
- `span_event`/`span_end` for an unknown span → the span is created as a placeholder (`name="<unknown>"`, `kind="chain"`, `started_at=ts`) and updated if `span_start` arrives later.
- `span_end` after `span_end` → ignored.
- Events within a batch are applied in order. The SDK exporter preserves order (single worker thread).

### 4.4 SDK exporter
```python
class Exporter(Protocol):
    def export(self, event: dict) -> None   # must not block; must not raise
    def flush(self, timeout: float) -> bool
    def shutdown(self, timeout: float) -> None
```
Implementations: `HttpExporter` (default), `InMemoryExporter` (tests; `.events` list), `NoopExporter`.

`HttpExporter`:
- Bounded `queue.Queue(maxsize=10_000)`; when full, the event is **dropped** and `dropped_count` incremented (warning rate-limited).
- One daemon worker thread; sends a batch when it has 200 events or 250 ms have passed.
- HTTP via **stdlib `urllib.request`**, timeout 2 s. On failure: the batch is dropped, and sending backs off exponentially (1 s → max 30 s) while the server is unreachable. One warning per 60 s: `failsight server not reachable at <endpoint>; traces are being dropped`.
- `flush(timeout)` waits until the queue is drained or timeout.

## 5. Storage (SQLite)

- File: `--db PATH` > env `FAILSIGHT_DB` > `~/.failsight/failsight.db` (directory created if missing).
- `PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;`
- Migrations: ordered list in `server/storage/migrations.py`, tracked with `PRAGMA user_version`. Never edit a released migration; add a new one.
- Access: a `Store` class with synchronous methods, one connection guarded by a `threading.Lock`. JSON columns stored as TEXT.

```sql
CREATE TABLE traces (
  trace_id         TEXT PRIMARY KEY,
  project          TEXT NOT NULL,
  name             TEXT NOT NULL,           -- root span name
  status           TEXT NOT NULL,           -- see §5.1
  root_span_id     TEXT,
  started_at       REAL NOT NULL,
  ended_at         REAL,
  last_activity_at REAL NOT NULL,
  span_count       INTEGER NOT NULL DEFAULT 0,
  error_count      INTEGER NOT NULL DEFAULT 0,  -- spans with status failed/timed_out/short_circuited
  resilience_event_count INTEGER NOT NULL DEFAULT 0,
  input_tokens     INTEGER NOT NULL DEFAULT 0,
  output_tokens    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_traces_started ON traces(started_at DESC);
CREATE INDEX idx_traces_project ON traces(project, started_at DESC);

CREATE TABLE spans (
  trace_id       TEXT NOT NULL REFERENCES traces(trace_id) ON DELETE CASCADE,
  span_id        TEXT NOT NULL,
  parent_span_id TEXT,
  seq            INTEGER NOT NULL,          -- arrival order within the trace
  name           TEXT NOT NULL,
  kind           TEXT NOT NULL,
  status         TEXT NOT NULL,
  started_at     REAL NOT NULL,
  ended_at       REAL,
  input          TEXT, output TEXT, error TEXT, attributes TEXT NOT NULL DEFAULT '{}', policy TEXT,
  PRIMARY KEY (trace_id, span_id)
);

CREATE TABLE span_events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  trace_id   TEXT NOT NULL REFERENCES traces(trace_id) ON DELETE CASCADE,
  span_id    TEXT NOT NULL,
  ts         REAL NOT NULL,
  name       TEXT NOT NULL,
  attributes TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX idx_events_span ON span_events(trace_id, span_id);
```

### 5.1 Derived trace fields
- `status`: `running` until the root span ends, then the root span's final status.
- `name`, `project`, `root_span_id`: from the span with `parent_span_id = null` (first one wins).
- `input_tokens`/`output_tokens`: sum of `gen_ai.usage.input_tokens`/`output_tokens` over the trace's spans (update on `span_end`).
- `resilience_event_count`: count of built-in resilience events (§4.1).
- `last_activity_at`: max `ts` of any event received for the trace.
- **Stale:** the UI shows a "no recent activity" badge if `status = running` and `last_activity_at` is older than 5 minutes. (No server-side mutation.)

## 6. REST API

All under `/api`. Errors use FastAPI's `{"detail": "..."}` with proper status codes.

### 6.1 Shapes
```ts
TraceSummary = { trace_id, project, name, status, root_span_id, started_at, ended_at,
                 last_activity_at, duration_ms /* null while running */, span_count,
                 error_count, resilience_event_count, input_tokens, output_tokens }
Span = { trace_id, span_id, parent_span_id, seq, name, kind, status, started_at, ended_at,
         duration_ms, input, output, error, attributes, policy }
SpanEvent = { id, trace_id, span_id, ts, name, attributes }
TraceDetail = { trace: TraceSummary, spans: Span[] /* ordered by seq */, events: SpanEvent[] /* ordered by ts, id */ }
```

### 6.2 Endpoints
| Method & path | Description | Response |
|---|---|---|
| `GET /api/health` | liveness | `{"status": "ok", "version"}` |
| `POST /api/ingest` | §4 | `202` |
| `GET /api/projects` | distinct projects, most recent first | `{"projects": ["…"]}` |
| `GET /api/traces?project=&status=&limit=50&cursor=` | list, newest first; `limit` ≤ 200; `status` may be `running`, `errors` (error_count > 0), or any final status | `{"traces": TraceSummary[], "next_cursor": string \| null}` |
| `GET /api/traces/{trace_id}` | full detail | `TraceDetail` · `404` |
| `DELETE /api/traces/{trace_id}` | delete one | `204` · `404` |
| `DELETE /api/traces?project=&before=` | bulk delete (all if no filters) | `{"deleted": n}` (P1) |
| `GET /api/traces/{trace_id}/export` | download export file (§6.4) | `200` JSON, `Content-Disposition: attachment` |
| `POST /api/import?overwrite=false` | import an export file | `201 {"trace_id"}` · `409` exists · `400` invalid |
| `POST /v1/traces` | OTLP/HTTP (§8) | per OTLP spec |

`cursor` is opaque to clients (server encodes `started_at` + `trace_id`).

### 6.3 SPA fallback
Any `GET` that is not under `/api/`, `/v1/`, or an existing static file returns `index.html` (client-side routing).

### 6.4 Export format
```json
{ "format": "failsight-trace", "version": 1, "exported_at": 1760430000000.0,
  "trace": TraceSummary, "spans": Span[], "events": SpanEvent[] }
```
Import validates `format` and `version`, and recomputes derived trace fields.

## 7. Live Updates (SSE)

`text/event-stream`. Each message has `event:` and a JSON `data:` line. A `: keepalive` comment is sent every 15 s.

| Endpoint | Messages |
|---|---|
| `GET /api/live?project=` | `trace` → `TraceSummary` whenever a trace is created/changed |
| `GET /api/traces/{trace_id}/stream` | first `snapshot` → `TraceDetail`; then `span` → `Span` (created/updated), `span_event` → `SpanEvent`, `trace` → `TraceSummary` |

- Server side: an in-process pub/sub broker (`server/live.py`); ingest publishes **after** the DB write commits.
- Per-trace `trace` messages on `/api/live` are throttled to at most 4/s (latest state wins).
- Client: on disconnect, reconnect with backoff and rely on the new `snapshot` (no event IDs/replay in v0.1).

## 8. OTLP/HTTP Ingest (observe-only)

- `POST /v1/traces`, OTLP/HTTP with `application/x-protobuf` and `application/json`.
- Mapping: OTel trace/span IDs → hex; `kind` from attributes: `gen_ai.operation.name` in (`chat`, `text_completion`, `generate_content`) → `llm`; `execute_tool` → `tool`; `invoke_agent`/`create_agent` → `agent`; otherwise `chain`. Status: OTel `ERROR` → `failed`, else `success`. `project` from resource attribute `service.name` (default `"otlp"`). Span events copied as span events.
- Spans arrive already ended: no live `running` state (documented).
- Exact OTel GenAI attribute names must be verified against the current semantic conventions during T51.

## 9. CLI

| Command | Behaviour |
|---|---|
| `failsight up [--host 127.0.0.1] [--port 7317] [--db PATH] [--open]` | Start server + UI. Non-loopback host prints a warning (no auth). `--open` opens the browser. |
| `failsight demo [--scenario NAME] [--runs N] [--chaos SPEC] [--seed N] [--endpoint URL]` | Run demo (§10). If `/api/health` at the endpoint is unreachable, start the server in a background thread in the same process and print the URL. |
| `failsight export TRACE_ID [-o FILE] [--endpoint URL]` | Save export file via the API. |
| `failsight import FILE [--overwrite] [--endpoint URL]` | Import via the API. |
| `failsight --version` | Print version. |

Env vars: `FAILSIGHT_HOST`, `FAILSIGHT_PORT`, `FAILSIGHT_DB`, `FAILSIGHT_ENDPOINT`, `FAILSIGHT_PROJECT`, `FAILSIGHT_DISABLED`.

## 10. Demo (`failsight.demo`)

Per PRD Q1: **built on plain failsight decorators** (works with the base install). A LangGraph version lives in `examples/langgraph_research/` (T55).

- Workflow: `planner → researcher (web_search, fetch_page) → writer → reviewer`, reviewer routes back to researcher up to 2 times ("needs more sources").
- Mock LLM: deterministic given `--seed`; latency 150–900 ms; synthetic token counts; `@fs.llm(model="mock-gpt")`.
- Mock tools with policies: `web_search` (retry + timeout + breaker + fallback to `backup_search`), `fetch_page` (retry + timeout).
- Scenarios: `happy` (no faults), `flaky` (30% 429s on `web_search` → retries), `outage` (`web_search` always fails → breaker opens → fallback), `slow` (timeouts), `loop` (reviewer sends back twice). Default: `flaky`.
- `--chaos` overrides, e.g. `web_search:error=0.5,latency=2.0;fetch_page:timeout=0.2`.
- The demo always finishes (no unhandled exceptions); final run summary printed.

## 11. UI

- Stack: Vite + React + TypeScript, `@xyflow/react`, `elkjs` (layered layout, top-down), React Router. Exact versions pinned in T01.
- Routes: `/` trace list · `/traces/:traceId` trace view.
- Types in `ui/src/api/types.ts` mirror §6.1 exactly; API client in `ui/src/api/client.ts`; SSE helpers in `ui/src/api/live.ts`.
- Canonical sample data: `ui/src/api/fixtures/sample-trace.json` (export format, §6.4) containing every kind, every status and every resilience event. Used by UI tests and Python import tests.
- Graph: node per span; edges parent → child; children ordered by `seq`. Node shows icon by kind, status (icon + label + color), name, duration, tokens, retry count badge, breaker/fallback markers. Fallback child connected with a dashed edge labelled "fallback".
- Loop collapsing (P1): consecutive siblings with the same `name` and `kind` collapse into one group node `name ×N`, expandable.
- Live mode: apply `span`/`span_event`/`trace` messages to local state; re-layout only when the node set changes; animate status changes.
- Inspector panel tabs: Overview (status, kind, timing, error + stack), Input, Output, Attributes, Events (timeline), Policy.
- Theme: CSS variables, light + dark via `prefers-color-scheme`.
