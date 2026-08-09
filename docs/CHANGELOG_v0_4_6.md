# CoinCoachSignalCloud v0.4.6

## Five-post preview reliability

- Manual preview ignores signal cooldown memory restored from earlier dry runs, preventing a previous preview from starving the next batch.
- Requires three distinct configured timeframes for a five-post preview, while retaining the maximum-two-per-timeframe rule.
- Adds one outer retry after the official chart capturer exhausts its internal attempts, improving recovery from transient Binance mobile-page failures.
- Records the successful outer capture attempt in each post and preserves final diagnostics when all retries fail.
- Publishing remains disabled.
