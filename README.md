# failsight

**See why your agents fail — and stop them from failing.**

Local-first, open-source observability and resilience for multi-agent AI workflows:
a live execution graph of your agents, tools and LLM calls, plus retries, timeouts,
fallbacks and circuit breakers you can watch in action.

> 🚧 Pre-alpha — under active development. See [docs/DESIGN.md](docs/DESIGN.md).

## Quickstart (planned)

```bash
pip install failsight
failsight up        # http://127.0.0.1:7317
```

## Development

Requirements: Python 3.10+, [uv](https://docs.astral.sh/uv/), Node.js 20+.

```bash
# UI (built into src/failsight/server/static)
cd ui && npm install && npm run build && cd ..

# Python
uv sync
uv run failsight up
uv run pytest
uv run ruff check .
```

For UI development with hot reload, run `uv run failsight up` and `npm run dev` in `ui/`
(the Vite dev server proxies `/api` to port 7317).

## License

[Apache-2.0](LICENSE)
