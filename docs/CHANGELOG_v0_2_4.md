# v0.2.4 — Official Binance Web Chart + Square API

## Added

- `app/official_web_chart.py`
- one-chart proof workflow
- five-chart preview workflow
- official web capture integration in the Square publisher run
- capture reports, page-text diagnostics, retry logic, blank-chart checks
- safe timeframe-row selector that rejects delete/clear/drawing controls

## Removed from the active route

- custom chart renderer
- Android emulator proof workflow
- Appium dependency

## Safety

- preview publishing remains disabled
- live publishing requires both `PUBLISH_ENABLED=true` and `LIVE_PUBLISH_APPROVED=true`
- only validated non-diagnostic PNGs are passed to the Square Post Skill
- local per-account daily ledger remains capped at 100 posts
