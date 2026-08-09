# v0.4.4 — five-image preview capture policy fix

The one-chart proof workflow was passing because it applied a non-destructive proof policy at runtime. The five-image preview did not apply those overrides, so all five images were rejected even though the same capture engine worked individually.

Changes:
- The five-image preview now uses the same proven screenshot-only policy as the one-chart proof.
- MA overlays are allowed in preview images.
- Anonymous indicator-toolbar cleanup is skipped to avoid the Binance clear-drawings control.
- Network interval observation is recorded but is non-blocking for preview mode.
- Real symbol, visible selected timeframe, fresh Binance snapshot, live-price matching, and valid image checks remain active.
- Publishing remains disabled.
