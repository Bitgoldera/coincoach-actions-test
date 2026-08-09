from __future__ import annotations

import argparse
import asyncio
import json

import uvicorn

from .config import load_config
from .cycle import run_cycle


def main() -> None:
    parser = argparse.ArgumentParser(description="CoinCoach Signal Cloud")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("cycle", help="Run one full-market dry-run cycle")
    subparsers.add_parser("free-cloud", help="Run one GitHub/free-cloud preview cycle")
    api_parser = subparsers.add_parser("api", help="Run the control API")
    api_parser.add_argument("--host", default="0.0.0.0")
    api_parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    if args.command == "cycle":
        preview = asyncio.run(run_cycle(load_config()))
        print(json.dumps({
            "candidate_count": preview["candidate_count"],
            "signal_count": preview["signal_count"],
            "shortages": preview["shortages"],
            "preview": "output/previews/latest_cycle.json",
        }, indent=2))
    elif args.command == "free-cloud":
        from scripts.run_free_cloud import main as free_cloud_main
        asyncio.run(free_cloud_main())
    elif args.command == "api":
        uvicorn.run("app.api:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
