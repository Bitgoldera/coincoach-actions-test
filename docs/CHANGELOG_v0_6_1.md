# CoinCoach Signal Cloud v0.6.1

## Leverage caption reliability patch

This incremental patch leaves the v0.6.0 social syndication and the existing Binance Square automation unchanged.

### Changed

- Uses exactly 30 planned leverage-caption slots per UTC day for every active Binance account.
- Gives each account an independent deterministic slot plan, preventing synchronized leverage posts across all accounts.
- Limits displayed leverage to varied integer values from 15x through 25x.
- Keeps leverage inside the first natural-language sentence beside the asset cashtag.
- Never places leverage as a separate line, at the beginning of the sentence, or at the end of the sentence.
- Applies the same behavior to bullish and bearish setups.
- Continues to prefer perpetual-eligible assets during selected leverage slots.
- Preserves captions, entries, targets, stop losses, images, scheduler fairness, and account_02 social fan-out.

### Example forms

- `leaning long on $SUI, while I keep leverage near 17x, the trend is trying to continue`
- `okay, $SUI, keeping leverage around 23x, the recovery is losing energy again`
- `the candles on $SUI, with leverage near 15x, buyers are stepping back in`

The exact wording, value, asset, direction, and setup continue to vary deterministically.

### Important behavior

The 30-post target assumes all 96 scheduled account slots complete and a perpetual-eligible candidate is available. A failed workflow, failed chart capture, failed Square API request, or unavailable perpetual metadata can reduce actual published volume; the patch does not fabricate futures eligibility.
