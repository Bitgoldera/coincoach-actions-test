# v0.3.7 — stop clear-drawings failures

- Manual proof mode no longer clicks anonymous chart toolbar controls while trying to remove MA/EMA overlays.
- This prevents Binance's **Clear all drawings** confirmation from opening accidentally.
- The screenshot proof continues even when MA/EMA remains visible and records `ma_overlay_removed: false`.
- Expanded safe dismissal support for Cancel, No, Keep, Close, Back, Not now, and Escape.
- Publishing remains disabled in the proof workflow.
