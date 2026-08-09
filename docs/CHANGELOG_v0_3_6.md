# CoinCoachSignalCloud v0.3.6

## Fixes
- Tracks Binance kline intervals inside multiplexed WebSocket subscription and data frames, not only from request URLs.
- The manual screenshot proof no longer fails only because GitHub did not observe the network interval. The official timeframe row, current market snapshot, live visible price, and freshness checks still remain active.
- The capture report accurately records whether network interval evidence was observed.
- Manual proof capture also allows an MA overlay to remain when Binance does not expose a reliable hide control, so the artifact is still produced for visual review. Live publishing configuration remains strict and unchanged.
