# v0.3.4 — tall crop below the pair name

- Changed the official Binance output from 1080×1080 to 1080×1350.
- Positions the mobile page so the pair-name row sits just above the screenshot.
- Starts the final crop immediately below BTC/USDT (or the active pair).
- Uses a viewport screenshot followed by a local crop, avoiding page-scroll coordinate errors.
- Keeps more of the candle chart visible underneath the price and timeframe sections.
- Strengthened MA/EMA removal with rightmost-control targeting, tooltip-guided detection, dense hover scanning, and touch fallback.
- Fails closed when the MA overlay remains visible, preventing a cluttered image from being accepted.
- Clears crosshair/OHLC hover state before the final screenshot.
