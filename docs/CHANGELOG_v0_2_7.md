# v0.2.7 — official Binance mobile-web live verification

- Replaced desktop viewport capture with Android mobile browser emulation.
- Added exact `15m`, `1h`, and `4h` timeframe choices.
- Requires both visible selected-state verification and Binance kline-network interval verification.
- Fetches a fresh Binance ticker/kline snapshot before capture.
- Compares the official page's visible price with the fresh ticker price.
- Rejects stale snapshots using timeframe-aware freshness limits.
- Uses an exact mobile timeframe-row selector with hit-testing and forbidden drawing-control metadata.
- Produces a square 1080 × 1080 official mobile-web crop.
- Keeps popup, blank-chart, symbol, layout, and image validation fail-closed.
- Publishing remains disabled in proof and preview workflows.
