# v0.5.2 — Square Binance Square image output

- Changes the final official Binance chart image from 1080 × 1350 (4:5) to 1080 × 1080 (1:1).
- Uses the same verified mobile-web capture, price safety, timeframe selection, retry, caption, reserve-candidate, and publishing logic from v0.5.1.
- Sets the mobile crop aspect ratio to 1.0 so the image is genuinely square before resize, rather than stretching a portrait crop.
- Keeps the live price, 24h statistics, selected timeframe, main candles, and right-side price label in the square frame.
- Publishing behavior is unchanged; the one-post workflow still posts at most one item per keyed account.
