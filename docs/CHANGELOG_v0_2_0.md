# v0.2.0 — Free rendered chart pipeline

## Why this version exists

Binance mobile-web repeatedly opens a destructive drawing confirmation inside its chart layer on GitHub-hosted headless browsers. The previous safety detector correctly rejected those images, but the browser route remained unreliable.

## Changes

- Stops using Playwright/Binance mobile-web screenshots in the free GitHub workflow.
- Fetches current public Binance klines for each selected symbol and timeframe.
- Renders an original 1080×1350 mobile chart with candles, volume, Entry, TP1–TP3 and SL.
- Adds no custom watermark and no Binance logo.
- Keeps Square publishing disabled.
- Removes Chromium installation from GitHub Actions, reducing workflow time.
- Adds renderer tests and small-price formatting tests.

## Important limitation

These images use real Binance market data, but they are not screenshots of the Binance Android app or website. Exact app screenshots still require a real Android device or a compatible cloud Android service.
