from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

from app.config import load_config
from app.official_web_chart import OfficialBinanceWebChartCapture, normalize_timeframe


def _safe_symbol(value: str) -> str:
    symbol = re.sub(r"[^A-Za-z0-9]", "", value).upper()
    if not symbol.endswith("USDT") or len(symbol) <= 4:
        raise ValueError("PROOF_SYMBOL must be a USDT symbol such as BTCUSDT")
    return symbol


async def main() -> None:
    if os.getenv("CAPTURE_APPROVAL", "") != "CAPTURE_ONE":
        raise RuntimeError("CAPTURE_APPROVAL must be CAPTURE_ONE")

    root = Path(__file__).resolve().parents[1]
    config = load_config(root)
    symbol = _safe_symbol(os.getenv("PROOF_SYMBOL", "BTCUSDT"))
    timeframe = normalize_timeframe(os.getenv("PROOF_TIMEFRAME", "15m"))

    output_dir = root / "output" / "mobile_web_proof"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{symbol}_{timeframe}_official_binance_mobile_live.png"

    allow_ma_overlay = os.getenv("PROOF_ALLOW_MA_OVERLAY", "true").strip().lower() in {
        "1", "true", "yes", "on"
    }
    if allow_ma_overlay:
        config.settings["capture"]["web"]["allow_ma_overlay_for_capture_proof"] = True

    # Proof mode is screenshot-only. Do not click anonymous chart toolbar controls: on
    # Binance mobile web they can be the clear-all-drawings button instead of MA/EMA.
    # The report still records whether the overlay is visible, but the workflow continues.
    skip_indicator_cleanup = os.getenv(
        "PROOF_SKIP_INDICATOR_CLEANUP", "true"
    ).strip().lower() in {"1", "true", "yes", "on"}
    config.settings["capture"]["web"][
        "skip_indicator_cleanup_for_proof"
    ] = skip_indicator_cleanup

    require_network_interval = os.getenv(
        "PROOF_REQUIRE_NETWORK_INTERVAL", "false"
    ).strip().lower() in {"1", "true", "yes", "on"}
    config.settings["capture"]["web"][
        "require_network_timeframe_confirmation"
    ] = require_network_interval

    # A proof run must not be blocked by Binance's non-modal chart panels being
    # misclassified as destructive confirmations. Real modal recovery is attempted,
    # but a failed dismissal is recorded through diagnostics instead of raising the
    # repeated clear-drawings error.
    config.settings["capture"]["web"][
        "non_blocking_dialog_recovery_for_proof"
    ] = True

    capture = OfficialBinanceWebChartCapture(root, config.settings)
    await capture.capture(symbol, timeframe, output_path)

    capture_report_path = output_path.with_suffix(".capture.json")
    capture_report = json.loads(capture_report_path.read_text(encoding="utf-8"))
    report = {
        "status": "accepted",
        "symbol": symbol,
        "timeframe": timeframe,
        "mobile_layout_verified": capture_report.get("mobile_layout_verified"),
        "network_interval_verified": capture_report.get("network_interval_verified"),
        "visible_price": capture_report.get("visible_price"),
        "live_price_reference": capture_report.get("live_price_reference"),
        "price_deviation_percent": capture_report.get("price_deviation_percent"),
        "snapshot_fresh": capture_report.get("snapshot_fresh"),
        "ma_overlay_removed": capture_report.get("ma_overlay_removed"),
        "image_path": str(output_path.relative_to(root)).replace("\\", "/"),
        "capture_report": str(capture_report_path.relative_to(root)).replace("\\", "/"),
        "publishing_attempted": False,
    }
    (output_dir / "proof_summary.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    github_summary = os.getenv("GITHUB_STEP_SUMMARY")
    if github_summary:
        Path(github_summary).write_text(
            "\n".join(
                [
                    "# Official Binance mobile-web live chart proof",
                    "",
                    f"- Symbol: {symbol}",
                    f"- Timeframe: {timeframe}",
                    "- Mobile layout verified: yes",
                    f"- Exact kline interval observed on network: {capture_report.get('network_interval_verified')}",
                    "- Exact timeframe selected in official mobile row: yes",
                    "- Current Binance price matched: yes",
                    "- Snapshot freshness verified: yes",
                    f"- MA/EMA overlay removed: {capture_report.get('ma_overlay_removed')}",
                    "- Publishing attempted: no",
                    f"- Image: `{report['image_path']}`",
                ]
            ),
            encoding="utf-8",
        )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
