# CoinCoachSignalCloud v0.4.1

## Exact fix
- Removed the blind top-right mouse click from chart-hover cleanup. That click was opening Binance's **Delete all drawings** confirmation.
- Chart hover cleanup now uses Escape, blur, pointer-leave events, and mouse movement only. It never clicks a guessed toolbar coordinate.
- Added exact detection for Binance's visible delete-all-drawings warning even when it has no `role="dialog"` wrapper.
- Added safe Cancel/Escape recovery and refuses to save a screenshot while the warning remains visible.
- Added regression tests proving hover cleanup cannot click a top-right toolbar button.

## Validation
- Full suite: 50 tests passed.
