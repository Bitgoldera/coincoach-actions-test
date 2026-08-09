from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.caption_engine import CaptionEngine
from app.config import load_config
from app.models import Signal
from app.router import AccountRouter
from app.storage import Storage


def make_signal(index: int) -> Signal:
    price = 0.01 + index * 0.0037
    side = "LONG" if index % 2 == 0 else "SHORT"
    risk = 3.7 + (index % 7) * 0.31
    tp1p = risk * (1.39 + (index % 5) * 0.041)
    tp2p = risk * (2.55 + (index % 6) * 0.063)
    tp3p = risk * (4.02 + (index % 4) * 0.117)
    entry_low = price * 0.997
    entry_high = price * 1.003
    if side == "LONG":
        stop = price * (1 - risk / 100)
        tps = [price * (1 + p / 100) for p in (tp1p, tp2p, tp3p)]
        setup = ["breakout_continuation", "trend_pullback", "rebound_continuation"][index % 3]
    else:
        stop = price * (1 + risk / 100)
        tps = [price * (1 - p / 100) for p in (tp1p, tp2p, tp3p)]
        setup = ["breakdown_continuation", "trend_rejection", "resistance_rejection"][index % 3]
    base = f"DEMO{index+1}"
    return Signal(
        signal_id=f"demo-{index+1:02d}", symbol=f"{base}USDT", base_asset=base,
        timeframe=["15m", "1h", "4h"][index % 3], side=side, setup=setup,
        score=94 - index * 0.7, current_price=price, entry_low=entry_low,
        entry_high=entry_high, entry_mid=price, stop_loss=stop,
        tp1=tps[0], tp2=tps[1], tp3=tps[2], stop_percent=round(risk, 2),
        tp1_percent=round(tp1p, 2), tp2_percent=round(tp2p, 2),
        tp3_percent=round(tp3p, 2), facts={"demo": True},
        created_at=datetime.now(timezone.utc),
    )


def main() -> None:
    config = load_config()
    demo_db = config.root / "data" / "demo.db"
    demo_db.unlink(missing_ok=True)
    storage = Storage(demo_db)
    caption_engine = CaptionEngine(storage, config.settings)
    router = AccountRouter(config.settings)
    routed, shortages = router.route(
        [make_signal(i) for i in range(36)],
        config.accounts,
        lambda signal, account_id, style: caption_engine.generate(signal, account_id, style),
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "shortages": shortages,
        "posts": [{
            "account_id": post.account_id,
            "style": post.style,
            "slot_time": post.slot_time.isoformat(),
            "caption": post.caption,
            "signal": asdict(post.signal),
        } for post in routed],
    }
    output = config.root / "output" / "previews" / "demo_cycle.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"Created {output} with {len(routed)} routed demo posts")


if __name__ == "__main__":
    main()
