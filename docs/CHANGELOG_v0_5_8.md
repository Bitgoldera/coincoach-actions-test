# CoinCoachSignalCloud v0.5.8

## Natural selective leverage wording

- Preserves every existing caption layout and all Entry, TP and Stop Loss lines.
- Adds leverage only to the existing opening line; no pipe separator or new caption block is introduced.
- Uses deterministic daily coverage of 20, 22, 25, 27 or 30 of the 96 scheduled slots.
- Supports both LONG and SHORT setups.
- Rotates leverage wording across the start, middle and end of the opening line.
- Uses 5x, 10x, 15x and occasional 20x values by timeframe.
- Adds leverage only when the same base asset has an active USDⓈ-M perpetual market.

## Expanded discovery scanner

- Scans both USDT and USDC spot quote universes.
- Adds best-effort USDⓈ-M perpetual eligibility and onboard-date metadata.
- Prioritizes configurable discovery buckets for new listings, Alpha watchlist assets, AI, Web3, USDC and TradFi tokenized securities.
- Keeps signal prices and official chart verification on the exact selected spot pair.
- If futures metadata is temporarily unavailable, normal spot scanning continues without failing the live run.

## Unchanged

- TP-distance correction from v0.5.7.
- 1080x1080 official Binance mobile-web chart capture.
- Cloudflare schedule and GitHub Actions live workflow.
- One post maximum per account per scheduled run.
- Existing Binance Square API account support.
