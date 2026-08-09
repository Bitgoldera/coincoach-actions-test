# CoinCoach Signal Cloud v0.3.0

Zero-cost GitHub Actions proof for **official Binance mobile-web live chart capture**.

This release does not draw candles and does not create a custom Binance-looking image. It opens the official Binance Spot page with Android mobile emulation and accepts an image only when all of these are verified:

- the requested USDT symbol is visible;
- the page is rendered at a mobile width with an Android mobile user agent;
- the exact signal timeframe is selected (`15m`, `1h`, or `4h`);
- Binance's own kline request uses that same interval;
- the visible page price is close to a fresh Binance public ticker price;
- the current kline is fresh for the requested timeframe;
- candles are loaded;
- no clear-drawings dialog, popup, blank chart, or desktop layout is present.

Accepted output is normalized to a taller `1080 × 1350` PNG. The crop begins immediately below the pair name and keeps the live price block, 24h statistics, timeframe row, and a longer candle-chart area. A failed proof produces diagnostics and no final image.

## Workflows

### Manual official Binance mobile-web live chart proof

Captures one image and never publishes.

Inputs:

- symbol: `BTCUSDT`
- timeframe: `15m`, `1h`, or `4h`
- confirmation: `CAPTURE_ONE`

Artifact name:

`official-binance-mobile-web-proof-*`

### Manual official Binance mobile-web live chart preview

Generates five current-market signals and attempts five matching mobile-web chart captures. It fails closed unless all five images pass validation. Publishing remains disabled.

### Manual Square API one-post test

Existing controlled one-post publisher. Run it only after the one-image and five-image proofs are visually approved. The Square key belongs in GitHub Actions Secrets, never in code.

## Fail-closed rule

`wrong symbol / wrong timeframe / stale price / popup / blank chart / desktop layout = no image = no post`

## Important limitation

The capture engine is built and unit-tested, but Binance can change its public page structure at any time. The first GitHub proof run is the live compatibility test. A green workflow and a visually correct artifact are both required before publishing is enabled.

Signal posts are informational and do not guarantee profitable trades.
