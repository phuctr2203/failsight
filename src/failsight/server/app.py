from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from failsight import __version__

STATIC_DIR = Path(__file__).parent / "static"

_UI_MISSING = """<!doctype html>
<title>failsight</title>
<p>failsight server is running, but the UI has not been built.</p>
<p>Run <code>npm run build</code> in <code>ui/</code>.</p>
"""


def create_app(static_dir: Path = STATIC_DIR) -> FastAPI:
    app = FastAPI(title="failsight", version=__version__)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    if (static_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="ui")
    else:

        @app.get("/", response_class=HTMLResponse)
        def ui_missing() -> str:
            return _UI_MISSING

    return app
