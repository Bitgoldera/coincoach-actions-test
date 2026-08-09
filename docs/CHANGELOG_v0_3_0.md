# v0.3.0 — real indicator-control click

- Replaced synthetic DOM indicator clicks with real Playwright pointer clicks.
- Prioritizes the official MA/EMA **Hide** control, then the remove/close control in the same legend band.
- Detects the hidden state when the control changes from Hide to Show.
- Moves the pointer away and waits before capture so the Hide tooltip is not included.
- Keeps the full mobile price header crop and all live symbol/timeframe/freshness checks.
