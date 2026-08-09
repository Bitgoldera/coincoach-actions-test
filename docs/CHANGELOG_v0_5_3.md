# CoinCoachSignalCloud v0.5.3

## Live schedule
- Added active GitHub Actions workflow `.github/workflows/live-square-96-per-day.yml`.
- Schedules four runs per hour at minutes 07, 22, 37 and 52 UTC.
- One post maximum per keyed account per run.
- Intended cadence: 4 posts/hour and 96 scheduled posts/day per keyed account.
- Added repository-variable kill switch: `COINCOACH_LIVE_96_ENABLED` must equal `true` for scheduled runs.

## Safety and reliability
- Keeps the verified 1080×1080 official Binance mobile chart capture.
- Keeps reserve candidates, capture retry, one-hour symbol cooldown and immediate stop after a publisher exception.
- Adds explicit `PER_ACCOUNT_DAILY_LIMIT=96` support to the live runner.
- Uses one concurrency group so live slots cannot publish simultaneously.

## Timing limitation
GitHub scheduled workflows can start late or occasionally be dropped under high platform load. This workflow requests exactly four slots per hour, but GitHub Actions cannot guarantee exact wall-clock delivery of all 96 posts.
