# v0.2.9 — MA removal and header-anchored crop

- Fixes the square crop so it remains anchored to the live price and 24h statistics instead of sliding down to include more chart area.
- Replaces generic MA text clicking with targeted hover-and-close interaction on the official Binance MA/EMA legend controls.
- Uses the nearest remove/close button, with the visibility button only as a fallback, while excluding drawing-clear controls.
- Keeps live symbol, price, timeframe, kline-interval, popup, freshness, and blank-chart validation.
