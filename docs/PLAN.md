# failsight — Project Plan (v0.1)

Status: **Approved** · Last updated: 2026-10-14
Related: [PRD.md](PRD.md) (what & why) · [SPEC.md](SPEC.md) (contracts) · [../AGENTS.md](../AGENTS.md) (how agents work in this repo)

This plan splits v0.1 into **tasks sized for one coding agent each** (one branch, one PR). Tasks are grouped into **waves**: tasks in the same wave can run **in parallel**; a wave starts when the tasks it depends on are merged.

---

## 1. How to Use This Plan

**For the owner (assigning work)**
1. Complete **T00** (approve SPEC and answer PRD open questions) before Wave 1. Parallel work depends on stable contracts.
2. Pick tasks whose dependencies are merged. Prefer starting a whole wave at once.
3. Assign with the prompt template in §5. One agent per task.
4. Review the PR against the task's acceptance criteria and the Definition of Done in [AGENTS.md](../AGENTS.md). Merge in dependency order.
5. Tick the task in the tracker (§4).

**Conflict avoidance rules**
- Each task lists the paths it **owns**. Two parallel tasks never own the same file.
- "**May touch**" files (shared registration points like `server/app.py`, `__init__.py`, `cli.py`, `pyproject.toml`, `ui/package.json`, `ui/src/App.tsx`) allow **small, additive edits only**. Rebase on `main` before opening the PR; regenerate lockfiles (`uv lock`, `npm install`) instead of hand-merging them.
- Contract changes go through a `SPEC CHANGE REQUEST` (see SPEC.md header). Never change a contract inside a feature PR.

**Sizes:** S ≈ a few hours · M ≈ 1–2 days · L ≈ 3–5 days (human-equivalent effort; for planning only).

## 2. Dependency Overview

```
Wave 0   T00 (owner) ──► T01 Foundations
                              │
Wave 1   ┌──────────┬────────┼─────────┬──────────┐
         T10 SDK    T11      T12       T14 UI     T30 Resilience
         core       Exporter Storage+  shell+list engine
                             ingest
Wave 2   T31 Resilience wiring (T10,T30)   T13 Read API (T12)   T20 SSE (T12)   T21 Canvas (T14)
Wave 3   T15 E2E tracing (T10,T11,T13)   T22 Inspector (T21)   T23 Live UI (T20,T21)
         T40 LangGraph (T10,T11)   T41 Demo mocks+chaos (T31)
Wave 4   T32 Resilience visuals (T22,T31)   T42 Demo app+CLI (T41,T13)   T50 Export/Import (T13,T14)
         T51 OTLP ingest (T12)   T52 Data management (T13)
Wave 5   T24 Loop collapse + large traces (T21,T22)   T53 Docs site   T54 Benchmarks   T55 Examples (T40,T42)
Wave 6   T60 Release pipeline   T61 README + GIF   T63 Cross-platform QA   T62 Launch (owner)
```

Critical path: **T01 → T10 → T31 → T41 → T42 → T61 → T62**.

## 3. Tasks

---

### T00 — Approve contracts & decisions *(owner, not an agent)*
- **Milestone:** M1 · **Priority:** P0 · **Size:** S · **Depends on:** —
- **Do:** review [SPEC.md](SPEC.md) and [PRD.md](PRD.md); answer PRD §11 open questions (Q1 demo dependency, Q2 docs tooling, Q4 PyPI placeholder); change SPEC status to **Approved**.
- **Done when:** SPEC.md says Approved and PRD Q1/Q2 are resolved.

---

### T01 — Foundations: shared types, package skeleton, test & UI tooling
- **Milestone:** M1 · **Priority:** P0 · **Size:** M · **Depends on:** T00 · **Parallel with:** — (runs alone)
- **Read first:** SPEC §1, §3.6, §4.1, §6.1, §6.3, §6.4, §11
- **Owns:** `src/failsight/protocol.py`, `src/failsight/errors.py`, `src/failsight/sdk/exporter.py`, package `__init__.py` files for `sdk/`, `resilience/`, `integrations/`, `demo/`, `server/routes/`, `server/storage/`; `server/app.py`; `tests/conftest.py`; `tests/test_imports.py`; `ui/src/api/types.ts`; `ui/src/api/fixtures/sample-trace.json`; UI test setup; `.github/workflows/ci.yml`; `.gitattributes`
- **Goal:** put every shared contract and tool in place so Wave 1 can run 5 agents in parallel without touching the same files.
- **Deliverables**
  - `protocol.py`: `SpanKind`, `SpanStatus`, final-status set, event-name constants, `TypedDict`s for the three wire events, `PROTOCOL_VERSION = 1`.
  - `errors.py`: `FailsightError`, `CircuitOpenError`, `FailsightTimeoutError` exactly per SPEC §3.6.
  - `sdk/exporter.py`: the `Exporter` Protocol plus `NoopExporter` and `InMemoryExporter` (SPEC §4.4) — small, so T10 and T11 can both build on it in parallel.
  - Empty subpackages with `__init__.py`.
  - `server/app.py`: router registration pattern (each feature adds `app.include_router(...)` from `server/routes/<feature>.py`) and **SPA fallback** (SPEC §6.3) with a test.
  - `tests/test_imports.py`: enforces SPEC §1 import rules (e.g. importing `failsight.sdk` must not import `fastapi`, `pydantic`, `uvicorn`).
  - Dev deps: `pytest-asyncio`, `pytest-cov`. Coverage report in CI.
  - UI deps: `@xyflow/react`, `elkjs`, `react-router`; dev: `vitest`, `@testing-library/react`, `jsdom`. **Verify each package and version exists on npm before adding.** Add `npm test` script and run it in CI.
  - `ui/src/api/types.ts` mirroring SPEC §6.1 + enums.
  - `sample-trace.json` (export format) — a realistic multi-agent trace (~25 spans) containing every `kind`, every final status, a `retrying` history, a fallback child, breaker events, LLM token attributes, a truncated payload and a redacted field. A Python test validates it against `protocol.py` enums.
  - `.gitattributes` with `* text=auto eol=lf`.
- **Acceptance criteria**
  - [ ] CI green: ruff, pytest (with coverage), UI lint, `npm test`, UI build, wheel build.
  - [ ] `GET /traces/abc` returns the UI `index.html`; `GET /api/unknown` returns 404 JSON.
  - [ ] Import-rule test fails if `sdk` imports `fastapi` (verify by temporarily adding one locally).
  - [ ] No feature logic implemented beyond the above.

---

### T10 — SDK core: config, context, spans, decorators, payload capture
- **Milestone:** M1 · **Priority:** P0 · **Size:** L · **Depends on:** T01 · **Parallel with:** T11, T12, T14, T30
- **Read first:** SPEC §2, §3.8, §4.2
- **Owns:** `src/failsight/sdk/{config,context,spans,decorators,payload}.py`, `tests/sdk/` (except exporter tests)
- **May touch:** `src/failsight/__init__.py` (exports)
- **Goal:** decorated functions emit correct `span_start` / `span_event` / `span_end` events to an `Exporter`.
- **Deliverables**
  - `init/shutdown/flush` (SPEC §2.2) against the `Exporter` Protocol from T01; lazy env auto-init; `NoopExporter` when disabled. Tests use `InMemoryExporter`. The default exporter is imported lazily from `sdk/http_exporter.py` (T11); until T11 merges, fall back to `NoopExporter`.
  - `trace`, `agent`, `tool`, `llm`, `span`, `current_span`, `Span` handle (SPEC §2.3–2.4), sync + async, bare and called forms.
  - Context propagation via `ContextVar` (SPEC §2.5).
  - Payload capture, default redaction, user redaction hook, truncation, capture errors (SPEC §2.6).
  - Safety: internal errors swallowed, rate-limited logging (SPEC §2.7).
  - Decorators accept policy kwargs and store them (JSON form in `span_start.policy`) but **do not execute them** — wiring is T31.
- **Acceptance criteria**
  - [ ] Nested sync, async, and mixed calls produce correct `parent_span_id` and one `trace_id`; concurrent `asyncio.gather` children share the parent.
  - [ ] Exceptions from user code propagate unchanged (same object); span ends `failed` with `error.type/message/stacktrace`.
  - [ ] `functools.wraps` preserved; `inspect.iscoroutinefunction` true for async wrappers; generators rejected with `TypeError`.
  - [ ] Redaction, truncation, `capture_payloads=False`, unserializable objects all tested.
  - [ ] An exporter that raises on `export` does not affect user code (test).
  - [ ] Without `init()` and without env vars, no events are produced and nothing is logged above DEBUG.
  - [ ] Coverage ≥ 90% for owned files.
- **Out of scope:** HTTP sending (T11), executing policies (T31).

---

### T11 — SDK exporter: HTTP batching, backpressure, shutdown
- **Milestone:** M1 · **Priority:** P0 · **Size:** M · **Depends on:** T01 · **Parallel with:** T10, T12, T14, T30
- **Read first:** SPEC §4.2–4.4
- **Owns:** `src/failsight/sdk/http_exporter.py`, `tests/sdk/test_http_exporter.py`
- **Deliverables:** `HttpExporter` implementing the `Exporter` Protocol (from T01) exactly per SPEC §4.4, using stdlib `urllib` only.
- **Acceptance criteria**
  - [ ] Batches by size (200) and time (250 ms); preserves order; payload matches SPEC §4.2 envelope.
  - [ ] Server down: `export()` never blocks or raises; backoff 1 s → 30 s; one warning per 60 s; events dropped and counted.
  - [ ] Queue full → drop + count, no blocking (test with tiny queue).
  - [ ] `flush()` returns True when drained, False on timeout; `shutdown()` is idempotent and bounded by its timeout.
  - [ ] Tests use a local `http.server` in a thread (no network).

---

### T12 — Server: storage layer + ingest endpoint
- **Milestone:** M1 · **Priority:** P0 · **Size:** L · **Depends on:** T01 · **Parallel with:** T10, T11, T14, T30
- **Read first:** SPEC §4.2–4.3, §5
- **Owns:** `src/failsight/server/storage/`, `src/failsight/server/routes/ingest.py`, `tests/server/test_storage.py`, `tests/server/test_ingest.py`
- **May touch:** `server/app.py` (register router; create `Store` on startup), `cli.py` (`--db` flag)
- **Deliverables:** `Store` class (SPEC §5) with migrations, apply-event methods, derived trace fields (§5.1), read methods needed by T13 (`list_traces`, `get_trace_detail`, `delete_trace`, `list_projects`); `POST /api/ingest` with all server rules in SPEC §4.3. Provide a `publish` hook point (no-op callable) that T20 will connect to the SSE broker.
- **Acceptance criteria**
  - [ ] All §4.3 rules tested: idempotent start, out-of-order end (placeholder span), double end ignored, invalid events counted, 400/413 cases.
  - [ ] Derived fields correct (status, counts, tokens, last_activity_at).
  - [ ] DB path precedence (`--db` > env > default) tested with `tmp_path`.
  - [ ] Migration from empty DB sets `user_version`; reopening an existing DB is a no-op.
  - [ ] Ingest of 10,000 events completes in < 2 s on CI (smoke perf test, marked `slow` if needed).

---

### T13 — Server: read API (list, detail, delete, projects)
- **Milestone:** M1 · **Priority:** P0 · **Size:** M · **Depends on:** T12 · **Parallel with:** T20, T21, T31
- **Read first:** SPEC §6.1–6.2
- **Owns:** `src/failsight/server/routes/traces.py`, `tests/server/test_traces_api.py`
- **May touch:** `server/app.py` (register router), `server/storage/` (read helpers only, coordinate if T12 still open)
- **Acceptance criteria**
  - [ ] Response shapes match SPEC §6.1 exactly (field names, `duration_ms` null while running).
  - [ ] Filters `project`, `status` (incl. `running`, `errors`), `limit` (max 200), cursor pagination tested across pages without duplicates.
  - [ ] `404` for unknown trace; `204` delete cascades spans/events.
  - [ ] Loading `sample-trace.json` via `Store` and fetching it returns equivalent data (round-trip test).

---

### T14 — UI: app shell, routing, API client, trace list
- **Milestone:** M1 · **Priority:** P0 · **Size:** M · **Depends on:** T01 · **Parallel with:** T10, T11, T12, T30
- **Read first:** SPEC §6.1–6.2, §11; PRD D1, D8
- **Owns:** `ui/src/App.tsx`, `ui/src/main.tsx`, `ui/src/api/client.ts`, `ui/src/pages/TraceListPage.tsx`, `ui/src/components/layout/`, `ui/src/components/status/` (StatusBadge, KindIcon), `ui/src/styles/`
- **Deliverables:** layout (header with project selector), routes `/` and `/traces/:traceId` (placeholder page owned by T21), typed API client, trace list table (status, name, project, started, duration, spans, tokens, errors), filters (project, status), "load more" pagination, empty state ("Run `failsight demo` to see your first trace"), stale badge (SPEC §5.1).
- **Acceptance criteria**
  - [ ] Works against fixtures (MSW or a fake client) and against a real server.
  - [ ] `StatusBadge` shows icon + label + color for every `SpanStatus`; contrast AA in light and dark.
  - [ ] Keyboard: list rows focusable, Enter opens trace.
  - [ ] Vitest tests for client and list rendering.
- **Out of scope:** live updates (T23).

---

### T15 — End-to-end tracing test (SDK → server → API)
- **Milestone:** M1 · **Priority:** P0 · **Size:** S · **Depends on:** T10, T11, T13 · **Parallel with:** T22, T23, T40, T41
- **Owns:** `tests/e2e/`
- **Deliverables:** pytest fixture that starts the real server on a free port with a temp DB; tests that run decorated sync/async workflows with the real `HttpExporter`, `fs.flush()`, then assert via REST.
- **Acceptance criteria**
  - [ ] Tree shape, statuses, payloads, tokens verified end-to-end.
  - [ ] "Server down" scenario: workflow still completes, no exceptions.
  - [ ] Runs in CI on all OSes in under 60 s.

---

### T20 — Server: live updates (SSE broker & endpoints)
- **Milestone:** M2 · **Priority:** P0 · **Size:** M · **Depends on:** T12 · **Parallel with:** T13, T21, T31
- **Read first:** SPEC §7
- **Owns:** `src/failsight/server/live.py`, `src/failsight/server/routes/live.py`, `tests/server/test_live.py`
- **May touch:** `server/app.py`, ingest publish hook (connect only)
- **Acceptance criteria**
  - [ ] `/api/traces/{id}/stream` sends `snapshot` first, then `span`/`span_event`/`trace` messages in order after DB commit.
  - [ ] `/api/live` throttles per-trace messages to ≤ 4/s, latest state wins.
  - [ ] Keepalive every 15 s (configurable for tests); client disconnects clean up subscriptions (no leak — test).
  - [ ] Slow subscriber cannot block ingest (bounded per-subscriber queue, drop oldest).

---

### T21 — UI: execution graph canvas
- **Milestone:** M2 · **Priority:** P0 · **Size:** L · **Depends on:** T14 · **Parallel with:** T13, T20, T31
- **Read first:** SPEC §11; PRD D2, D5
- **Owns:** `ui/src/pages/TracePage.tsx`, `ui/src/components/canvas/`, `ui/src/graph/` (span tree → nodes/edges, elkjs layout)
- **Deliverables:** trace page with header (name, status, duration, tokens), React Flow canvas, custom node per kind, parent→child edges ordered by `seq`, fallback dashed edge, fit-view, minimap, zoom controls, node selection state (exposes `selectedSpanId` for the inspector slot — render an empty right panel placeholder that T22 fills).
- **Acceptance criteria**
  - [ ] Renders `sample-trace.json` correctly; snapshot/DOM tests for graph building (pure functions in `ui/src/graph/` have unit tests).
  - [ ] Layout of a generated 1,000-span trace < 1 s in a unit benchmark.
  - [ ] Pure layout/graph code has no React dependency.

---

### T22 — UI: node inspector panel
- **Milestone:** M2 · **Priority:** P0 · **Size:** M · **Depends on:** T21 · **Parallel with:** T23, T15
- **Owns:** `ui/src/components/inspector/`
- **May touch:** `TracePage.tsx` (mount the panel)
- **Deliverables:** tabs Overview / Input / Output / Attributes / Events / Policy (SPEC §11); collapsible JSON viewer; truncated/redacted payload rendering; error with stacktrace; copy-to-clipboard.
- **Acceptance criteria**
  - [ ] Every span in `sample-trace.json` renders without errors; tests cover truncated, redacted, error and LLM spans.
  - [ ] Keyboard accessible tabs; Esc closes panel.

---

### T23 — UI: live updates
- **Milestone:** M2 · **Priority:** P0 · **Size:** M · **Depends on:** T20, T21 · **Parallel with:** T22
- **Owns:** `ui/src/api/live.ts`, `ui/src/state/` (trace reducer)
- **May touch:** `TraceListPage.tsx`, `TracePage.tsx` (subscribe)
- **Acceptance criteria**
  - [ ] Pure reducer applies `snapshot`/`span`/`span_event`/`trace` messages; unit-tested with a scripted message sequence.
  - [ ] Graph re-layouts only when the node set changes; status changes animate without layout jumps.
  - [ ] Reconnect with backoff; "Live" / "Reconnecting…" indicator.
  - [ ] Trace list updates live (new traces appear at top).

---

### T24 — UI: loop collapsing & large traces *(P1)*
- **Milestone:** M5 · **Priority:** P1 · **Size:** M · **Depends on:** T21, T22
- **Owns:** `ui/src/graph/collapse.ts`, `ui/src/components/canvas/GroupNode.tsx`, search box component
- **Acceptance criteria:** consecutive same-name siblings collapse to `name ×N` (expandable); subtrees auto-collapse above 500 spans; search by span name highlights and centers nodes; 5,000-span trace stays interactive.

---

### T30 — Resilience engine (policies + executor)
- **Milestone:** M3 · **Priority:** P0 · **Size:** L · **Depends on:** T01 · **Parallel with:** T10, T11, T12, T14
- **Read first:** SPEC §3 (all)
- **Owns:** `src/failsight/resilience/`, `tests/resilience/`
- **Deliverables:** `Retry`, `Timeout`, `CircuitBreaker`, `Fallback`, `Policies`, breaker registry + `reset_breakers()`, `run_sync`, `run_async`, `ResilienceHooks` Protocol, JSON serialization of policies (`to_dict()`) for `span_start.policy`. Define and document the fallback-invocation callback signature (SPEC §3.7).
- **Acceptance criteria**
  - [ ] Every rule in SPEC §3.2–3.5 has a test, using injected `sleep`/`clock`/`rng` (no real sleeping in unit tests).
  - [ ] Breaker half-open allows exactly one concurrent trial (threaded and asyncio tests).
  - [ ] Sync timeout returns control on time while the worker keeps running; context is copied into the worker.
  - [ ] Hooks called with correct arguments; a raising hook doesn't break the executor.
  - [ ] No imports from `failsight.sdk` (import test).
  - [ ] Coverage ≥ 95%.

---

### T31 — Wire resilience into the SDK
- **Milestone:** M3 · **Priority:** P0 · **Size:** M · **Depends on:** T10, T30 · **Parallel with:** T13, T20, T21
- **Read first:** SPEC §3.5, §3.7, §3.8, §4.2
- **Owns:** `src/failsight/sdk/resilience_bridge.py`, `tests/sdk/test_resilience_spans.py`
- **May touch:** `sdk/decorators.py` (call the executor)
- **Deliverables:** decorators execute policies via `run_sync`/`run_async`; hooks translate into `span_event`s with live `status`; fallback child spans; final status mapping (SPEC §3.8); policies still apply when tracing is disabled.
- **Acceptance criteria**
  - [ ] Each row of SPEC §3.8 covered by a test asserting emitted events and final status.
  - [ ] `retry_attempt` events carry `status: "retrying"`; breaker transitions emitted on the span that observed them.
  - [ ] With `FAILSIGHT_DISABLED=1`, retries/timeouts/breakers/fallbacks behave identically (test).

---

### T32 — UI: resilience visuals
- **Milestone:** M3 · **Priority:** P0 · **Size:** M · **Depends on:** T22, T31 (real data) · can start on fixtures after T22
- **Owns:** `ui/src/components/canvas/badges/`, `ui/src/components/inspector/PolicyTab.tsx`, `ui/src/components/inspector/EventsTimeline.tsx`
- **Acceptance criteria**
  - [ ] Retry count badge, timeout marker, breaker-open marker, fallback edge label on nodes; legend explaining markers.
  - [ ] Events timeline shows attempts with errors and delays; Policy tab renders the policy JSON human-readably ("3 attempts, exponential from 0.5 s, max 30 s").
  - [ ] Live: a node visibly switches to `retrying` and back.

---

### T40 — LangGraph integration
- **Milestone:** M4 · **Priority:** P0 · **Size:** L · **Depends on:** T10, T11 · **Parallel with:** T41, T15, T22, T23
- **Owns:** `src/failsight/integrations/langgraph/`, `tests/integrations/test_langgraph.py`
- **May touch:** `pyproject.toml` (optional extra `langgraph`; CI job installing it)
- **Deliverables:** `instrument(compiled_graph)` → object with the same `invoke/ainvoke/stream/astream` API; each run is a trace; graph nodes → `agent` spans; tool calls → `tool` spans; chat model calls → `llm` spans with model and token usage. **Research the current LangGraph/LangChain callback API and pin a minimum version; do not guess method names.**
- **Acceptance criteria**
  - [ ] Test graph with fake chat model (no API key) produces the expected tree including a conditional loop.
  - [ ] Works with sync and async invocation and streaming.
  - [ ] Importing `failsight` without LangGraph installed still works; `instrument` raises a helpful `ImportError` if missing.

---

### T41 — Demo building blocks: mock LLM, mock tools, chaos
- **Milestone:** M4 · **Priority:** P0 · **Size:** M · **Depends on:** T31 · **Parallel with:** T40, T15
- **Read first:** SPEC §10
- **Owns:** `src/failsight/demo/{mock_llm,mock_tools,chaos}.py`, `tests/demo/`
- **Acceptance criteria**
  - [ ] Deterministic with a seed; chaos spec parser (`web_search:error=0.5,latency=2.0;...`) with clear errors on bad input.
  - [ ] Mock errors include a `RateLimitError` (429) type; latencies realistic (150–900 ms) but scalable to 0 for tests.

---

### T42 — Demo workflow + `failsight demo` CLI
- **Milestone:** M4 · **Priority:** P0 · **Size:** M · **Depends on:** T41, T13 · **Parallel with:** T32, T50, T51
- **Owns:** `src/failsight/demo/{workflow,scenarios,runner}.py`, `tests/demo/test_workflow.py`
- **May touch:** `cli.py` (add `demo` subcommand)
- **Acceptance criteria**
  - [ ] All scenarios in SPEC §10 run to completion and produce the expected statuses/events (tests run with latency scale 0).
  - [ ] If no server is reachable, the CLI starts one in-process and prints the URL; if one is running, it uses it.
  - [ ] Fresh venv: `pip install <wheel>` → `failsight demo` → trace visible in UI (manual check documented in PR).

---

### T50 — Export / import (API, CLI, UI)
- **Milestone:** M5 · **Priority:** P0 · **Size:** M · **Depends on:** T13, T14
- **Owns:** `src/failsight/server/routes/transfer.py`, `tests/server/test_transfer.py`, `ui/src/components/transfer/`
- **May touch:** `cli.py` (`export`, `import`), `TracePage.tsx` / `TraceListPage.tsx` (buttons)
- **Acceptance criteria:** export → import round-trip equality; `409` on conflict, `overwrite=true` replaces; invalid files → `400` with reason; `sample-trace.json` imports cleanly; UI download/upload buttons.

---

### T51 — OTLP/HTTP ingest *(P1)*
- **Milestone:** M5 · **Priority:** P1 · **Size:** M · **Depends on:** T12
- **Owns:** `src/failsight/server/otlp.py`, `src/failsight/server/routes/otlp.py`, `tests/server/test_otlp.py`
- **May touch:** `pyproject.toml` (protobuf dependency — prefer `opentelemetry-proto`; verify it exists and its size)
- **Acceptance criteria:** JSON and protobuf payloads accepted; mapping per SPEC §8 (verify current GenAI semconv names and update SPEC via change request if they differ); a test using the official OTel Python SDK exporter end-to-end.

---

### T52 — Data management *(P1)*
- **Milestone:** M5 · **Priority:** P1 · **Size:** S · **Depends on:** T13
- **Owns:** bulk-delete route in `server/routes/traces.py` (coordinate: T13 must be merged), `ui/src/components/settings/`
- **Acceptance criteria:** `DELETE /api/traces?project=&before=`; UI "Clear traces" with confirmation; DB path shown in UI footer.

---

### T53 — Documentation site
- **Milestone:** M5 · **Priority:** P0 · **Size:** M · **Depends on:** content from T31, T40, T42
- **Owns:** `docs/site/`, `mkdocs.yml` (MkDocs Material, per PRD Q2), `.github/workflows/docs.yml` (deploy to GitHub Pages)
- **Acceptance criteria:** pages per PRD F2; every code sample runs (snippets tested or taken from `examples/`); deployed to GitHub Pages from `main`.

---

### T54 — Benchmarks & performance verification
- **Milestone:** M5 · **Priority:** P0 · **Size:** M · **Depends on:** T31, T12, T21
- **Owns:** `benchmarks/`, `docs/benchmarks.md`
- **Acceptance criteria:** scripts measure NFR-2 (decorator overhead), NFR-4 (ingest throughput), NFR-5 (UI layout of 1k spans); results recorded with machine specs; any miss filed as an issue with a profile.

---

### T55 — Examples
- **Milestone:** M5 · **Priority:** P0 · **Size:** S · **Depends on:** T31, T40, T42
- **Owns:** `examples/` (`basic_sync/`, `async_agents/`, `langgraph_research/`), `tests/test_examples.py`
- **Acceptance criteria:** each example has a README and runs without API keys by default; CI runs them as smoke tests.

---

### T60 — Release pipeline
- **Milestone:** M6 · **Priority:** P0 · **Size:** S · **Depends on:** T01
- **Owns:** `.github/workflows/release.yml`, `CHANGELOG.md`, `docs/RELEASING.md`
- **Acceptance criteria:** pushing tag `vX.Y.Z` builds UI + sdist + wheel, verifies the UI is inside both, and publishes to PyPI via **Trusted Publishing** (owner configures PyPI side); version comes from a single source; dry-run to TestPyPI documented.

---

### T61 — README, GIF, launch-ready repo
- **Milestone:** M6 · **Priority:** P0 · **Size:** S · **Depends on:** T42, T32, T23
- **Owns:** `README.md`, `docs/assets/`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `.github/ISSUE_TEMPLATE/`, `.github/PULL_REQUEST_TEMPLATE.md`
- **Acceptance criteria:** 60-second quickstart verified; GIF of `failsight demo --scenario outage` showing breaker + fallback live; badges (CI, PyPI, license); contributor docs.

---

### T63 — Cross-platform QA
- **Milestone:** M6 · **Priority:** P0 · **Size:** S · **Depends on:** T42, T50, T60
- **Owns:** `docs/qa-checklist.md`; bug issues
- **Acceptance criteria:** release criteria PRD §9 item 2 executed on Windows, macOS, Linux from a TestPyPI build; results recorded.

---

### T62 — Launch *(owner)*
- **Depends on:** all P0 tasks · **Do:** publish 0.1.0, Product Hunt listing, pre-launch posts, monitor issues.

## 4. Tracker

| Task | Title | Wave | Depends on | Status |
|---|---|---|---|---|
| T00 | Approve contracts & decisions (owner) | 0 | — | ☑ |
| T01 | Foundations | 0 | T00 | ☐ |
| T10 | SDK core | 1 | T01 | ☐ |
| T11 | SDK exporter | 1 | T01 | ☐ |
| T12 | Storage + ingest | 1 | T01 | ☐ |
| T14 | UI shell + trace list | 1 | T01 | ☐ |
| T30 | Resilience engine | 1 | T01 | ☐ |
| T13 | Read API | 2 | T12 | ☐ |
| T20 | SSE live | 2 | T12 | ☐ |
| T21 | Canvas | 2 | T14 | ☐ |
| T31 | Resilience wiring | 2 | T10, T30 | ☐ |
| T15 | E2E tracing test | 3 | T10, T11, T13 | ☐ |
| T22 | Inspector | 3 | T21 | ☐ |
| T23 | Live UI | 3 | T20, T21 | ☐ |
| T40 | LangGraph integration | 3 | T10, T11 | ☐ |
| T41 | Demo mocks + chaos | 3 | T31 | ☐ |
| T32 | Resilience visuals | 4 | T22, T31 | ☐ |
| T42 | Demo workflow + CLI | 4 | T41, T13 | ☐ |
| T50 | Export / import | 4 | T13, T14 | ☐ |
| T51 | OTLP ingest (P1) | 4 | T12 | ☐ |
| T52 | Data management (P1) | 4 | T13 | ☐ |
| T24 | Loop collapse + large traces (P1) | 5 | T21, T22 | ☐ |
| T53 | Docs site | 5 | T00, T31, T40, T42 | ☐ |
| T54 | Benchmarks | 5 | T12, T21, T31 | ☐ |
| T55 | Examples | 5 | T31, T40, T42 | ☐ |
| T60 | Release pipeline | 6 | T01 | ☐ |
| T61 | README + GIF | 6 | T23, T32, T42 | ☐ |
| T63 | Cross-platform QA | 6 | T42, T50, T60 | ☐ |
| T62 | Launch (owner) | 6 | all P0 | ☐ |

Maximum useful parallelism: **5 agents** (Wave 1), 4 in Waves 2–4.

## 5. Prompt Template for Assigning a Task

```text
You are working on the failsight repository. Your task is <TASK ID> — <TITLE>.

1. Read AGENTS.md, then docs/PLAN.md (section for <TASK ID>), then the SPEC.md sections it lists.
2. Create branch task/<TASK ID>-<short-slug> from the latest main.
3. Only modify files the task "Owns"; make small additive edits to "May touch" files.
4. Do not change contracts in docs/SPEC.md. If you believe one must change, stop and
   describe a "SPEC CHANGE REQUEST" in your final message instead of implementing it.
5. Meet every acceptance criterion and the Definition of Done in AGENTS.md.
6. Open a PR titled "<TASK ID>: <TITLE>" whose description lists each acceptance
   criterion with how it was verified.
```
