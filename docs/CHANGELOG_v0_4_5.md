# CoinCoachSignalCloud v0.4.5

## Timeframe-diverse five-post batches

- Adds a strict maximum of two signals from the same timeframe per account batch.
- Keeps all symbol/timeframe variants available until routing, so lower-scoring 15m or 1h signals are not erased when 4h scores dominate.
- A complete five-post batch must therefore use all three configured timeframes, normally in a 2/2/1 distribution.
- Global symbol uniqueness remains enforced.

## Clearer public captions

Every caption now includes:

- Direction and setup context
- Spot chart or Futures label from configuration
- Exact timeframe (15M, 1H, or 4H)
- Entry zone
- TP1, TP2, and TP3
- Stop Loss
- NFA. DYOR.

For Spot data, short calls are labelled `Short setup | Spot chart` so the post does not falsely imply that a native Spot short order is being placed.

## Preview validation

The five-image preview now reports and validates:

- Expected post count
- Timeframe distribution
- Maximum-two-per-timeframe rule
- Caption timeframe/market/risk context
- Official Binance image validation

Publishing remains disabled in preview mode.
