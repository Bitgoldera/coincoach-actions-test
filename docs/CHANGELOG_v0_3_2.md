# CoinCoachSignalCloud v0.3.2

## What changed
- Reworked official Binance mobile-web crop logic so the square screenshot anchors to the live price block instead of the top site header.
- Added viewport positioning before capture so the mobile screenshot looks closer to a real in-app chart card.
- Added a hover-clearing step before screenshot to reduce stuck OHLC overlays and tooltip popups.
- Improved moving-average cleanup to prefer the rightmost indicator control when Binance exposes inline MA controls.

## Goal
Produce a tighter mobile-style chart crop with:
- no Binance logo / signup header in the final square image
- price and 24h stats visible
- timeframe row visible
- more consistent chart-card framing
- fewer leftover MA/EMA overlays
