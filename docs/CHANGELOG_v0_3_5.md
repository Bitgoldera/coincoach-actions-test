# v0.3.5 — frame-aware MA cleanup and non-blocking proof

- Searches the main page and embedded chart frames for MA/EMA legends and controls.
- Clicks semantic Remove/Hide indicator controls directly when Binance exposes them.
- Keeps a coordinate and tooltip fallback for canvas-style chart controls.
- The manual proof workflow no longer fails only because Binance refuses to hide MA/EMA.
  It still records `ma_overlay_removed` in the capture report and never publishes.
- Real preview/live publishing keeps the strict MA-removal requirement.
- Preserves the tall 1080x1350 crop from v0.3.4.
