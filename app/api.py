from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException

from .config import load_config
from .cycle import run_cycle

app = FastAPI(title="CoinCoach Signal Cloud", version="0.1.7")


@app.get("/health")
def health() -> dict:
    config = load_config()
    return {
        "status": "ok",
        "mode": config.settings.get("mode", "dry_run"),
        "publishing_enabled": config.settings["publishing"]["enabled"],
        "mobile_capture_enabled": config.settings["capture"]["enabled"],
        "web_capture_enabled": config.settings["capture"].get("web_enabled", False),
        "account_activation_mode": config.account_activation_mode,
        "active_account_count": len(config.active_accounts()),
        "active_accounts": [account.id for account in config.active_accounts()],
    }


@app.get("/accounts/status")
def accounts_status() -> dict:
    config = load_config()
    return {
        "activation_mode": config.account_activation_mode,
        "active_count": len(config.active_accounts()),
        "accounts": config.account_statuses(),
    }


@app.post("/cycles/dry-run")
async def dry_run_cycle() -> dict:
    config = load_config()
    if config.settings["publishing"]["enabled"]:
        raise HTTPException(status_code=409, detail="Disable publishing before running the dry-run endpoint")
    return await run_cycle(config)


@app.get("/cycles/latest")
def latest_cycle() -> dict:
    config = load_config()
    path = config.root / "output" / "previews" / "latest_cycle.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="No cycle has run yet")
    return json.loads(path.read_text(encoding="utf-8"))
