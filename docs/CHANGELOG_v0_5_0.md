# CoinCoachSignalCloud v0.5.0

## Five-post reserve replacement

The manual official Binance chart preview now generates up to nine routed candidates internally while keeping the final public preview at five posts.

- Final quota remains five posts per active account.
- Final timeframe cap remains two posts per timeframe.
- Up to four extra candidates are held as reserves.
- A candidate whose official Binance screenshot fails is discarded and replaced by the next eligible reserve candidate.
- Rejected diagnostic images are removed from a successful artifact; the error text remains in `latest_cycle.json`.
- The capture class keeps its internal retry policy, while preview outer attempts are limited to two so the workflow moves to a reserve symbol instead of waiting repeatedly on one bad page.
- Captions retain the approved varied layout and continue to omit the setup/context line and `NFA. DYOR.`
- Publishing remains disabled.
