from __future__ import annotations

import json
from dataclasses import asdict

from .binance_market import BinanceMarketClient
from .caption_engine import CaptionEngine
from .config import AppConfig
from .router import AccountRouter
from .scanner import UniverseScanner
from .signal_engine import SignalEngine
from .storage import Storage


async def run_cycle(config: AppConfig) -> dict:
    storage = Storage()
    active_accounts = config.active_accounts()

    # Do not scan the whole market when there is no active destination account.
    if not active_accounts:
        preview = {
            "active_account_count": 0,
            "active_accounts": [],
            "account_statuses": config.account_statuses(),
            "shortlist_count": 0,
            "deep_scan_count": 0,
            "candidate_count": 0,
            "signal_count": 0,
            "shortages": {"global_needed": 0, "global_available_unique": 0},
            "posts": [],
            "message": "No active account. Add a Square key to .env for an enabled account.",
        }
        preview_path = config.root / "output" / "previews" / "latest_cycle.json"
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        preview_path.write_text(json.dumps(preview, indent=2), encoding="utf-8")
        return preview

    market = BinanceMarketClient()
    scanner = UniverseScanner(market, config.settings)
    engine = SignalEngine(config.settings)
    caption_engine = CaptionEngine(storage, config.settings)
    try:
        shortlist = await scanner.shortlist()
        deep_items = await scanner.deep_scan(shortlist)
        candidates = []
        for item in deep_items:
            candidates.extend(engine.detect(item))

        minimum = float(config.settings["signals"]["tier_c_minimum_score"])
        signals = []
        cooldown = int(config.settings["signals"]["symbol_cooldown_hours"])
        for candidate in sorted(candidates, key=lambda item: item.score, reverse=True):
            if candidate.score < minimum:
                continue
            if storage.symbol_in_cooldown(candidate.symbol.symbol, cooldown):
                continue
            signal = engine.build_signal(candidate)
            if signal is not None:
                signals.append(signal)

        router = AccountRouter(config.settings)
        routed, shortages = router.route(
            signals,
            active_accounts,
            lambda signal, account_id, style: caption_engine.generate(signal, account_id, style),
        )
        preview_path = config.root / "output" / "previews" / "latest_cycle.json"
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        preview = {
            "active_account_count": len(active_accounts),
            "active_accounts": [account.id for account in active_accounts],
            "account_statuses": config.account_statuses(),
            "universe_filter_stats": scanner.last_filter_stats,
            "shortlist_count": len(shortlist),
            "deep_scan_count": len(deep_items),
            "candidate_count": len(candidates),
            "signal_count": len(signals),
            "shortages": shortages,
            "posts": [
                {
                    "account_id": post.account_id,
                    "style": post.style,
                    "slot_time": post.slot_time.isoformat(),
                    "caption": post.caption,
                    "signal": asdict(post.signal),
                    "image_path": post.image_path,
                }
                for post in routed
            ],
        }
        preview_path.write_text(json.dumps(preview, indent=2, default=str), encoding="utf-8")
        for post in routed:
            storage.save_signal(post.signal, post.account_id, post.caption, post.image_path, "queued_dry_run")
        return preview
    finally:
        storage.close()
        await market.close()
