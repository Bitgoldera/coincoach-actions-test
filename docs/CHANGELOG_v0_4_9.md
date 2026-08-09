# v0.4.9 — clean-caption validator and preview reliability

- Fixes the preview validator so it accepts the user-approved caption format without the context line and without `NFA. DYOR.`.
- Rejects the old removed lines if they reappear.
- Increases official Binance preview capture attempts from two to three outer attempts.
- Clears stale diagnostics before each retry so a successful later capture is reported cleanly.
- Stores caption, image and timeframe validation fields in `latest_cycle.json`.
- Publishing remains disabled in the preview workflow.
