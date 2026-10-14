# failsight — Product Requirements Document (v0.1)

Status: **Approved** · Owner: Tran Hoang Phuc · Last updated: 2026-10-14
Related: [DESIGN.md](DESIGN.md) (architecture & rationale) · [SPEC.md](SPEC.md) (technical contracts) · [PLAN.md](PLAN.md) (execution plan)

---

## 1. Summary

**failsight** is a local-first, open-source developer tool that lets engineers **see** what their multi-agent AI workflows are doing and **protect** them from failing.

- **See:** a live execution graph of agents, tools and LLM calls, with status, payloads, tokens and latency per step.
- **Protect:** declarative retries, timeouts, fallbacks and circuit breakers on any tool or LLM call — and the graph shows these working in real time.

Distribution: one Python package (`pip install failsight`) containing the SDK, the local server and the prebuilt web UI. Launch target: Product Hunt + GitHub, as a DevTool in "AI Observability & Fault Tolerance".

## 2. Problem

Developers building multi-agent systems face three recurring problems:

1. **Black box execution.** Hard to see which agent did what, which tools were called, where a run failed, or where it looped.
2. **Brittle execution.** A flaky tool API or an LLM rate limit breaks the whole run. Retry/fallback logic is ad-hoc, duplicated, and invisible.
3. **No cost/latency visibility per step.** Finding the slow or token-hungry step means grepping logs.

Existing tools cover parts of this: tracing platforms (Langfuse, LangSmith, Arize Phoenix, AgentOps) show what happened; LLM gateways (Portkey, LiteLLM, Helicone) add retries/fallbacks for LLM API calls only. None combine **resilience for tools and LLM calls** with a **live visual graph of that resilience**, running fully locally.

## 3. Target Users

| Persona | Description | Primary need |
|---|---|---|
| **Agent builder** (primary) | Python engineer building multi-agent apps (LangGraph or custom) | Debug failing/looping runs quickly; make tools robust without boilerplate |
| **AI architect** | Designs agent systems for a team | Understand flow, cost and latency hot spots; standardize resilience patterns |
| **OSS contributor / evaluator** | Tries tools from Product Hunt / GitHub | Working demo in under 2 minutes, no API key, no signup |

## 4. Goals & Success Metrics

**Product goals (v0.1)**
- G1. Time from `pip install` to seeing a live trace graph: **≤ 2 minutes**, no API key, no account.
- G2. Adding failsight to an existing Python agent: **≤ 5 lines of code** for basic tracing.
- G3. Resilience policies make a flaky tool succeed or degrade gracefully, and the user can **see** each retry/fallback/breaker transition on the graph.
- G4. failsight **never breaks or noticeably slows** the user's application.

**Launch metrics** — *targets to be set by the owner* (see Open Questions):
- GitHub stars at launch +7 days, Product Hunt upvotes/rank, PyPI downloads in first 30 days, number of external issues/PRs.

## 5. Scope

### 5.1 In scope (v0.1)
- Python SDK: tracing decorators, context propagation, background exporter.
- Resilience engine: retry, timeout, fallback, circuit breaker (sync + async).
- Local server: ingest, SQLite storage, REST API, live updates (SSE), serves UI.
- Web UI: trace list, live execution graph (canvas), node inspector, resilience visuals.
- LangGraph integration.
- Built-in demo with chaos injection (no API key).
- Export/import traces as JSON.
- OTLP/HTTP ingest (observe-only path for apps already emitting OpenTelemetry).
- Docs: README quickstart + docs site.

### 5.2 Out of scope (v0.1)
- Hosted/cloud service, accounts, auth, multi-user, teams.
- Editing resilience policies from the UI (UI shows policies read-only).
- Non-Python SDKs (a .NET SDK is a post-launch candidate).
- Evals, prompt management, datasets, playground.
- LLM HTTP proxy / gateway mode.
- Cost in currency (v0.1 shows tokens; price table is a stretch goal).
- Distributed tracing across processes/services.

## 6. User Stories

Priority: **P0** = required for launch · **P1** = should have · **P2** = nice to have.

### Epic A — Instrumentation (SDK)
| ID | Story | Pri |
|---|---|---|
| A1 | As an agent builder, I call `fs.init(project=...)` once and decorate functions with `@fs.agent` / `@fs.tool` / `@fs.llm` so their runs appear as a trace. | P0 |
| A2 | Nested decorated calls (sync, async, mixed) produce a correct parent/child tree without me passing anything around. | P0 |
| A3 | Inputs, outputs, errors, durations are captured automatically; I can attach token usage and custom attributes to the current span. | P0 |
| A4 | Secrets in payloads (API keys, tokens, passwords) are redacted by default; I can add my own redaction and disable payload capture. | P0 |
| A5 | If the failsight server is not running, my app runs normally (no exceptions, no hangs, negligible overhead). | P0 |
| A6 | I can disable tracing entirely via env var without code changes, while resilience policies keep working. | P0 |
| A7 | I can explicitly group work into a named trace with `with fs.trace("name"):`. | P1 |

### Epic B — Resilience
| ID | Story | Pri |
|---|---|---|
| B1 | I configure retries with fixed/exponential backoff + jitter, filtered by exception type. | P0 |
| B2 | I set per-attempt and total timeouts on any decorated call. | P0 |
| B3 | I define a fallback function used when the primary fails, times out or is short-circuited. | P0 |
| B4 | A circuit breaker trips after N consecutive failures, fails fast while open, and recovers via half-open trial. | P0 |
| B5 | Every resilience action is recorded on the span (attempt number, error, delay, breaker transitions, fallback reason). | P0 |
| B6 | Resilience errors are typed (`CircuitOpenError`, `FailsightTimeoutError`) so I can handle them. | P0 |

### Epic C — Server & Storage
| ID | Story | Pri |
|---|---|---|
| C1 | `failsight up` starts the server and UI locally on `127.0.0.1:7317`. | P0 |
| C2 | Traces persist across restarts in a local SQLite file whose location I can configure. | P0 |
| C3 | I can list/filter traces by project and status, and delete traces. | P0 |
| C4 | Apps already emitting OpenTelemetry spans can send them to failsight's OTLP endpoint and see the graph (no live in-progress state). | P1 |
| C5 | I can delete all traces or old traces to control disk use. | P1 |

### Epic D — UI
| ID | Story | Pri |
|---|---|---|
| D1 | I see a list of traces (newest first) with status, duration, span count, tokens, error indicator; it updates live. | P0 |
| D2 | Opening a trace shows its execution graph: nodes = spans (agent/tool/llm/router/chain), edges = parent→child. | P0 |
| D3 | While a trace is running, nodes appear and change status in real time (running → retrying → success/failed…). | P0 |
| D4 | Clicking a node opens an inspector: status, timing, input, output, error + stack, attributes, tokens, event timeline, applied policy. | P0 |
| D5 | Resilience is visible on the graph: retry count badge, timeout marker, fallback edge/node, breaker-open state. | P0 |
| D6 | Repeated loop iterations (e.g., reviewer → researcher ×3) are collapsible into one node with a count. | P1 |
| D7 | Large traces (1,000+ spans) stay usable (collapsed subtrees, pan/zoom, search by name). | P1 |
| D8 | Light and dark theme follow the OS setting; status is conveyed by icon + label, not color alone. | P0 |
| D9 | I can export a trace to JSON and import one shared by a teammate. | P0 |

### Epic E — Integrations & Demo
| ID | Story | Pri |
|---|---|---|
| E1 | I wrap a compiled LangGraph graph with `instrument(graph)` and get nodes, tools and LLM calls traced, including token usage. | P0 |
| E2 | `failsight demo` runs a multi-agent research workflow with mock LLM/tools, no API key, and streams it to the canvas. | P0 |
| E3 | Demo scenarios/chaos flags inject latency, timeouts, 429s and exceptions so I can watch retries, fallbacks and breakers. | P0 |
| E4 | If no server is running, `failsight demo` starts one and prints the URL. | P0 |
| E5 | Chaos can be toggled live from a UI panel. | P2 |

### Epic F — Docs & Launch
| ID | Story | Pri |
|---|---|---|
| F1 | README has a 60-second quickstart, a GIF of the live canvas, and a feature overview. | P0 |
| F2 | Docs site covers: quickstart, SDK reference, resilience guide, LangGraph guide, OTLP guide, FAQ. | P0 |
| F3 | Runnable examples in `examples/` (plain Python, async, LangGraph). | P0 |
| F4 | Release is automated: tag → CI builds UI + wheel → publishes to PyPI. | P0 |

## 7. Functional Requirements (summary)

Detailed contracts live in [SPEC.md](SPEC.md). Key requirements:

- **FR-1 SDK API** — `init`, `shutdown`, `flush`, `trace`, `agent`, `tool`, `llm`, `span`, `current_span` (SPEC §2).
- **FR-2 Decorators preserve semantics** — return values, exceptions, signatures (`functools.wraps`), sync/async nature are unchanged.
- **FR-3 Wire protocol** — span lifecycle events (`span_start`, `span_event`, `span_end`) over `POST /api/ingest` (SPEC §4).
- **FR-4 Resilience semantics** — composition order `Fallback → CircuitBreaker → Retry → Timeout → call`, exact rules in SPEC §3.
- **FR-5 Storage** — SQLite with schema migrations (SPEC §5).
- **FR-6 REST + SSE APIs** — SPEC §6–7.
- **FR-7 Export format** — versioned JSON `failsight-trace` v1 (SPEC §6.4).
- **FR-8 CLI** — `failsight up | demo | export | import | --version` (SPEC §9).

## 8. Non-Functional Requirements

| ID | Requirement | Target (proposed) |
|---|---|---|
| NFR-1 | **Safety:** instrumentation never raises into user code; internal errors are logged once and swallowed | 100% — enforced by tests |
| NFR-2 | **SDK overhead** per decorated call (excluding large-payload serialization and network) | p95 < 0.2 ms |
| NFR-3 | **Exporter** never blocks user code; bounded memory | Bounded queue (10k events), drop + count when full |
| NFR-4 | **Ingest throughput** on a developer laptop | ≥ 5,000 events/s |
| NFR-5 | **UI performance** | 1,000-span trace interactive (layout < 1 s); live updates without full re-layout flicker |
| NFR-6 | **Compatibility** | Python 3.10–3.14 · Windows/macOS/Linux · latest Chrome, Firefox, Safari, Edge |
| NFR-7 | **Privacy** | Binds to 127.0.0.1 by default; no telemetry; default secret redaction |
| NFR-8 | **Install footprint** | Core package has no heavy deps beyond FastAPI/Uvicorn; SDK path uses stdlib only |
| NFR-9 | **Quality** | CI green on all supported Pythons; ≥ 90% line coverage for `sdk/` and `resilience/` |
| NFR-10 | **Accessibility** | Keyboard navigable lists/inspector; status not conveyed by color alone; WCAG AA contrast |

## 9. Release Criteria (v0.1 "launch-ready")

1. All **P0** stories implemented and accepted.
2. Quickstart verified on clean machines (Windows, macOS, Linux): `pip install failsight` → `failsight demo` → live graph in ≤ 2 minutes.
3. NFR-1, NFR-3, NFR-6, NFR-9 verified in CI; NFR-2, NFR-4, NFR-5 verified by benchmark scripts with results recorded in `docs/benchmarks.md`.
4. Docs site published; README GIF recorded.
5. Version `0.1.0` published to PyPI via automated release.
6. No known P0/P1 bugs open.

## 10. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Crowded observability market | Low differentiation | Lead with *visible resilience* + local-first + zero-key demo |
| LangGraph API changes | Integration breaks | Pin minimum version, integration tests in CI, isolate in `integrations/` |
| Sync timeouts can't kill threads in Python | Surprising behavior | Document clearly; run sync calls in worker thread; emit `timeout` event |
| Secrets in captured payloads | Privacy incident | Default redaction, opt-out of payload capture, local-only storage |
| SQLite growth on long sessions | Disk usage | Retention command, delete-all, payload truncation |
| Scope creep before launch | Delayed launch | Strict P0 list; P1/P2 only after release criteria are met |

## 11. Decisions & Open Questions

| # | Question | Decision (2026-10-14) |
|---|---|---|
| Q1 | Should `failsight demo` require LangGraph? If yes, `pip install failsight` alone can't run the demo. | **Decided:** demo uses plain failsight decorators (works with base install); LangGraph version ships as `examples/langgraph_research/` via `pip install "failsight[langgraph]"`. |
| Q2 | Docs site tooling and hosting | **Decided:** MkDocs Material on GitHub Pages |
| Q3 | Launch metric targets (stars, PH rank, downloads) | **Open** — owner to set before M6 |
| Q4 | Publish a `0.0.1` placeholder to PyPI now to reserve the name? | **Decided:** yes, as soon as possible (owner action) |
| Q5 | Live chaos UI panel (E5) in v0.1? | **Decided:** no — CLI flags only for v0.1 |

## 12. Milestones

See [PLAN.md](PLAN.md) for tasks, dependencies and parallelization.

| # | Milestone | Exit criteria |
|---|---|---|
| M0 | Skeleton ✅ | Repo, CI, `failsight up` serves placeholder UI |
| M1 | Tracing core | Decorated calls → stored traces → trace list in UI |
| M2 | Live canvas | Graph + inspector update live via SSE |
| M3 | Resilience | All policies implemented, emitted and visualized |
| M4 | LangGraph + demo | `failsight demo` with chaos scenarios; LangGraph example |
| M5 | Polish | Export/import, OTLP ingest, data management, docs site, benchmarks |
| M6 | Launch | 0.1.0 on PyPI, README GIF, Product Hunt assets |
