# v0.4.0 — stop repeated false clear-drawings failures

- Replaced broad class-name modal detection with strict modal semantics.
- A destructive dialog now requires a visible role/aria modal, fixed positioning, destructive text, and both cancel and confirm actions.
- Timeframe selection attempts safe cancellation instead of immediately failing.
- Manual proof mode no longer raises the repeated clear-drawings error after recovery attempts.
- Indicator cleanup remains skipped in proof mode, so no anonymous drawing toolbar control is clicked.
