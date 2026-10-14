import argparse
import os

from failsight import __version__

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7317


def _up(args: argparse.Namespace) -> None:
    import uvicorn

    from failsight.server import create_app

    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"WARNING: binding to {args.host}; failsight has no authentication.")
    print(f"failsight {__version__} running at http://{args.host}:{args.port}", flush=True)
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="failsight")
    parser.add_argument("--version", action="version", version=f"failsight {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    up = sub.add_parser("up", help="start the failsight server and UI")
    up.add_argument("--host", default=os.environ.get("FAILSIGHT_HOST", DEFAULT_HOST))
    up.add_argument("--port", type=int, default=int(os.environ.get("FAILSIGHT_PORT", DEFAULT_PORT)))
    up.set_defaults(func=_up)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
