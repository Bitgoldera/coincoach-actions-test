# CoinCoachSignalCloud v0.5.7

## Balanced take-profit distances

This patch keeps the existing risk-aware target calculation but applies substantially tighter timeframe-specific maximum distances.

- 15m caps: TP1 3.0%, TP2 5.5%, TP3 8.0%
- 1h caps: TP1 3.5%, TP2 6.5%, TP3 10.0%
- 4h caps: TP1 5.0%, TP2 9.5%, TP3 14.0%

Targets that are naturally closer remain unchanged. The patch does not alter entry zones, stop-loss logic, chart capture, captions, scheduling, account routing, or Binance Square publishing.
