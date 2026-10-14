# failsight — Design Doc (Draft v0.1)

> **See why your agents fail — and stop them from failing.**
> Local-first, open-source observability and resilience for multi-agent AI workflows.

Status: **Accepted (v0.1 scope)** · License: Apache-2.0 · Last updated: 2026-10-14

> Background and rationale. For requirements see [PRD.md](PRD.md); for binding contracts see [SPEC.md](SPEC.md) (SPEC wins on conflict); for execution see [PLAN.md](PLAN.md).

---

## 1. Positioning

Existing tools split into two camps:

- **Tracing** (Langfuse, LangSmith, Arize Phoenix, AgentOps) — show what happened, after the fact.
- **LLM gateways** (Portkey, LiteLLM, Helicone) — retries/fallbacks, but only for LLM API calls.

**failsight's angle:** one tool that does both, for *tools and LLM calls*, with a **live graph that shows resilience in action** (retrying, fallback taken, breaker open) — and runs entirely on your machine with one `pip install`.

## 2. Goals & Non-Goals (v0.1 launch)

**Goals**
- 60-second quickstart: `pip install failsight` → `failsight up` → working demo on the canvas.
- Python SDK with decorators for tracing + resilience (retry, timeout, fallback, circuit breaker).
- Live execution graph with per-node status, payloads, tokens, latency.
- LangGraph integration as the showcase.
- Built-in demo app with chaos toggles that runs **without an API key**.
- Export/import traces as JSON.

**Non-goals (v0.1)**
- Hosted/cloud version, auth, multi-user.
- Editing resilience policies from the UI (control plane). UI shows policies read-only.
- Non-Python SDKs (.NET via Polly is a candidate for later).
- Evals, prompt management, dataset features.
- LLM HTTP proxy mode.

## 3. User Experience

```bash
pip install failsight
failsight up          # starts server + UI at http://127.0.0.1:7317
failsight demo        # runs the chaos demo, streams into the canvas
```

```python
import failsight as fs
from failsight import Retry, Timeout, Fallback, CircuitBreaker

fs.init(project="research-bot")   # defaults to http://127.0.0.1:<port>

def backup_search(query: str) -> list[str]: ...

@fs.tool(
    retry=Retry(attempts=3, backoff="exponential", base=0.5, on=(TimeoutError, RateLimitError)),
    timeout=Timeout(seconds=10),
    breaker=CircuitBreaker(failure_threshold=5, reset_after=30),
    fallback=Fallback(backup_search),
)
def web_search(query: str) -> list[str]: ...

@fs.agent(name="researcher")
async def researcher(state): ...
```

LangGraph:

```python
from failsight.integrations.langgraph import instrument
graph = instrument(builder.compile())   # nodes → agent spans, tools/LLM calls traced automatically
```

> The API above is a proposal — final names to be confirmed during M1.

## 4. Architecture

```
┌────────────── User's agent process ──────────────┐
│  your code / LangGraph                           │
│      │                                           │
│  failsight SDK                                   │
│   ├─ instrumentation (decorators, LangGraph)     │
│   ├─ resilience engine (retry/timeout/breaker/   │
│   │   fallback, sync + async)                    │
│   └─ exporter (batched, non-blocking, drops on   │
│       backpressure — never breaks the app)       │
└──────────────┬───────────────────────────────────┘
               │ HTTP  POST /api/ingest   (live span events)
               │ HTTP  POST /v1/traces    (standard OTLP, ended spans only)
┌──────────────▼───────────────────────────────────┐
│  failsight server (FastAPI, binds 127.0.0.1)     │
│   ├─ ingest → SQLite (WAL)                       │
│   ├─ REST: traces, spans, export/import          │
│   ├─ SSE: /api/traces/{id}/stream, /api/live     │
│   └─ serves bundled UI static files              │
└──────────────┬───────────────────────────────────┘
               │ REST + SSE
┌──────────────▼───────────────────────────────────┐
│  UI (Vite + React + React Flow, prebuilt)        │
│   trace list · live canvas · node inspector      │
└──────────────────────────────────────────────────┘
```

### Why a custom ingest endpoint *and* OTLP?
OpenTelemetry exports spans only **when they end**, so an OTLP-only pipeline can't show a node as `Running` or `Retrying` live. The SDK therefore sends lightweight lifecycle events (`span_started`, `span_event`, `span_ended`). The OTLP endpoint remains for zero-code adoption from apps already emitting OTel GenAI spans — they get the graph, just without live in-progress state.

## 5. Data Model

Aligned with OTel concepts so traces are convertible both ways.

**Trace**: `trace_id`, `project`, `name`, `started_at`, `ended_at`, `status`, `root_span_id`, totals (tokens, cost, duration).

**Span**
| Field | Notes |
|---|---|
| `span_id`, `parent_span_id`, `trace_id` | tree structure |
| `kind` | `agent` · `tool` · `llm` · `router` · `chain` |
| `name` | e.g. `web_search` |
| `status` | `pending` · `running` · `retrying` · `success` · `failed` · `timed_out` · `fallback` · `short_circuited` |
| `started_at`, `ended_at` | |
| `input`, `output` | JSON, truncated above a size limit, passed through redaction hook |
| `error` | type, message, stack |
| `attributes` | OTel GenAI semconv where possible (`gen_ai.request.model`, `gen_ai.usage.input_tokens`, …) |
| `policy` | snapshot of the resilience policy applied (read-only in UI) |

**Span events** (timeline within a span): `retry_attempt`, `timeout`, `fallback_invoked`, `breaker_opened`, `breaker_half_open`, `breaker_closed`.

**Graph rendering:** tree from `parent_span_id`, plus sequence edges between siblings. Loops (router → agent again) appear as repeated nodes, collapsible into one node with an `×N` badge.

## 6. Resilience Engine

Policy composition order (outermost → innermost):

```
Fallback → CircuitBreaker → Retry → Timeout → call
```

- **Timeout** applies per attempt. An optional `total` timeout wraps the whole thing.
- **Retry**: fixed / exponential with jitter; filter by exception type or predicate.
- **CircuitBreaker**: closed → open → half-open; state is per process, keyed by tool name (or an explicit `key`). Breaker state changes are emitted as events so the canvas can show tripped nodes.
- **Fallback**: callable or another `@fs.tool`; triggered after retries are exhausted, breaker is open, or a timeout.
- Sync and async both supported. Sync timeouts are best-effort (Python can't safely kill threads) — documented limitation.
- Implemented in-house (small, focused, emits our events), no Tenacity dependency.

**Safety rule:** the SDK must never crash or slow the user's app. Exporter failures are swallowed and logged; queues are bounded.

## 7. Demo App (`failsight demo`)

A multi-agent "research assistant" built on plain failsight decorators (no LangGraph needed; a LangGraph version ships in `examples/`): **planner → researcher (web_search, fetch_page) → writer → reviewer**, with a router loop back from reviewer to researcher.

- Uses a **mock LLM and mock tools by default** — no API key, deterministic.
- Chaos toggles (CLI flags + UI panel): inject latency, timeouts, 429s, exceptions per tool.
- Optional `--real` mode with user's own provider key.

This doubles as the Product Hunt video, the README GIF, and an end-to-end test.

## 8. Repo Layout

```
failsight/
├─ pyproject.toml               # the pip package (repo root)
├─ src/failsight/
│  ├─ sdk/                      # init, decorators, context, exporter
│  ├─ resilience/               # retry, timeout, breaker, fallback
│  ├─ integrations/langgraph/
│  ├─ server/                   # FastAPI app, storage, SSE, otlp
│  │  └─ static/                # built UI (generated, git-ignored)
│  ├─ demo/
│  └─ cli.py                    # failsight up | demo | export | import
├─ tests/
├─ ui/                          # Vite + React + React Flow frontend
├─ docs/                        # design + user docs
├─ examples/
├─ .github/workflows/           # CI: lint, test, build UI, build wheel
├─ LICENSE
└─ README.md
```

**Tooling (proposed):** Python 3.10+, `uv`, `ruff`, `pytest`, `pytest-asyncio`; UI with Vite, `npm`, TypeScript, `@xyflow/react`, `elkjs` or `dagre` for auto-layout.

## 9. Milestones

| # | Milestone | Done when |
|---|---|---|
| M0 | Skeleton | Repo, CI, `failsight up` serves a placeholder UI |
| M1 | Tracing core | Decorators emit spans → stored in SQLite → trace list in UI |
| M2 | Live canvas | Graph renders and updates live via SSE; node inspector |
| M3 | Resilience | Retry/timeout/breaker/fallback + events shown on canvas |
| M4 | LangGraph + demo | `failsight demo` with chaos toggles, no API key |
| M5 | Polish | Export/import, OTLP ingest, redaction, docs site |
| M6 | Launch prep | README GIF/video, PyPI release, PH assets, pre-launch posts |

## 10. Decisions

| Topic | Decision | Rationale |
|---|---|---|
| UI framework | **Vite + React** | Static SPA bundled into the Python package; no SSR needed |
| Resilience | **In-house** | Small surface, full control over emitted events, no extra dependency |
| License | **Apache-2.0** | Permissive, explicit patent grant, standard for dev infra |
| Default port | **7317** (configurable via `--port` / `FAILSIGHT_PORT`) | Avoids 4318 so it doesn't clash with a local OTel Collector; OTLP is still accepted at `/v1/traces` |
| Cost | **Tokens only in v0.1**; model price table is an M5 stretch goal | Price tables go stale; tokens are always accurate |
| Python | **3.10+** | Widest reach among agent developers |

## 11. Security & Privacy

- Server binds to `127.0.0.1` by default; no auth in v0.1, so binding to other interfaces requires an explicit flag with a warning.
- Payloads may contain secrets/PII: configurable redaction hook + size truncation; option to disable payload capture.
- No telemetry phoning home.
