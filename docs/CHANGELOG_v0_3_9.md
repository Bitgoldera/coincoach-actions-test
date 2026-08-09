# v0.3.9 — remove false destructive-dialog blocking

- Removed the pixel-only destructive-dialog detector from live capture gating.
- Only a genuinely visible DOM dialog can now block or trigger cancellation.
- Chart activity and final-image validation no longer fail because normal Binance chart panels resemble a modal to the old image heuristic.
- Keeps safe Escape/cancel handling for a real visible confirmation dialog.
- Publishing remains disabled in proof mode.
