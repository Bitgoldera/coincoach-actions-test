from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    report_path = root / "output" / "previews" / "square_api_run.json"
    if not report_path.exists():
        raise SystemExit(f"Missing pilot report: {report_path}")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    published = [
        item
        for item in report.get("results", [])
        if item.get("account_id") == "account_02" and item.get("published") is True
    ]
    if not published:
        raise SystemExit("Pilot did not publish a confirmed account_02 Square post")

    social = published[-1].get("social_syndication")
    if not isinstance(social, dict):
        raise SystemExit("Pilot report has no social_syndication result")
    if social.get("status") != "complete":
        print(json.dumps(social, indent=2))
        raise SystemExit("One or more selected social destinations failed")

    print(json.dumps(social, indent=2))
    print("Account_02 Square + selected social destinations passed")


if __name__ == "__main__":
    try:
        main()
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f"Pilot validation error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
