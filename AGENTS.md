# AGENTS.md — Guide for coding agents

failsight is a local-first, open-source tool for **observing** and **hardening** multi-agent AI workflows: a Python SDK (tracing + retries/timeouts/fallbacks/circuit breakers), a FastAPI server with SQLite, and a React UI with a live execution graph — shipped as one pip package.

## Read before you start

1. [docs/PLAN.md](docs/PLAN.md) — find your task: what you **own**, what you **may touch**, acceptance criteria.
2. [docs/SPEC.md](docs/SPEC.md) — the contracts (APIs, wire protocol, DB schema, semantics). **Source of truth.**
3. [docs/PRD.md](docs/PRD.md) — why the feature exists and who it is for.
4. [docs/DESIGN.md](docs/DESIGN.md) — background and rationale.

If the task, SPEC or code disagree or are ambiguous: **stop and ask** (or describe the issue in your final message). Do not guess requirements.

## Repository layout

```
pyproject.toml            Python package (repo root), hatchling build
src/failsight/
  protocol.py, errors.py  shared contracts
  sdk/                    tracing SDK — stdlib only, never imports server/fastapi/pydantic
  resilience/             policies + executor — never imports sdk/
  integrations/           optional framework integrations (extras)
  server/                 FastAPI app, routes/, storage/, live.py
    static/               built UI (generated, git-ignored)
  demo/                   demo workflow, mocks, chaos
  cli.py                  `failsight` command
tests/                    pytest, mirrors src/ layout
ui/                       Vite + React + TypeScript frontend
docs/                     PRD, SPEC, PLAN, DESIGN
```

## Commands

```bash
# Python (from repo root)
uv sync                          # install deps
uv run pytest                    # tests
uv run pytest --cov=failsight    # with coverage
uv run ruff check .              # lint
uv run ruff format .             # format
uv run failsight up              # run server at http://127.0.0.1:7317

# UI (from ui/)
npm install
npm run dev                      # dev server, proxies /api to :7317
npm run lint
npm test
npm run build                    # outputs to src/failsight/server/static

# Package
uv build                         # sdist + wheel (build the UI first)
```

## Conventions

**General**
- Smallest change that satisfies the task. Follow existing style and structure.
- Do not add dependencies unless the task says so. **Verify that any package/version you add actually exists**, and never invent APIs — check the library's docs or installed source.
- Comments only where the code is not self-explanatory. No large commented-out blocks.
- No secrets, tokens or personal data in code, tests, fixtures or logs.

**Python**
- Python 3.10+ syntax (`X | None`, `match` ok). Type hints on all public functions.
- ruff for lint and format (config in `pyproject.toml`, line length 100).
- Public API is only what `failsight/__init__.py` exports; everything else may change.
- SDK code must follow SPEC §2.7: **never let an internal error reach user code**; log via `logging.getLogger("failsight")`, rate-limited.
- Tests: pytest, `pytest-asyncio` for async. No real network, no real sleeping in unit tests (inject `sleep`/`clock`), use `tmp_path` for files/DBs.

**UI**
- TypeScript strict; types for API data come from `ui/src/api/types.ts` (mirrors SPEC §6.1 — don't redefine).
- Pure logic (graph building, layout, reducers) lives outside React components and has unit tests.
- Colors via CSS variables; support light and dark; status never shown by color alone.

**Contracts**
- Never change behaviour defined in SPEC.md within a feature PR. Raise a `SPEC CHANGE REQUEST` instead.

## Git & PR workflow

- Branch: `task/<TASK-ID>-<short-slug>` from latest `main`. One task per branch/PR.
- Stay within the files your task **owns**; only small additive edits to **may touch** files.
- Rebase on `main` before opening the PR; regenerate lockfiles (`uv lock`, `npm install`) rather than hand-merging.
- Commit messages: imperative summary line (≤ 72 chars), optional body explaining *why*.
- PR title: `<TASK-ID>: <title>`. PR description: each acceptance criterion with how it was verified.
- Never commit generated files (`src/failsight/server/static/`, `dist/`, `node_modules/`, `.venv/`) or `.env` files.

## Definition of Done

- [ ] All acceptance criteria of the task are met and listed in the PR with evidence.
- [ ] `uv run ruff check .` and `uv run ruff format --check .` pass.
- [ ] `uv run pytest` passes; new code is tested (coverage targets per task).
- [ ] If UI changed: `npm run lint`, `npm test`, `npm run build` pass.
- [ ] No contract in SPEC.md changed without an approved change request.
- [ ] Public behaviour changes are reflected in docs (README / docs site) when the task requires it.
- [ ] CI is green.
