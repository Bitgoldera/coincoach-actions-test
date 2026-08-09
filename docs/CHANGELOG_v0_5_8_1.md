# CoinCoachSignalCloud v0.5.8.1

## Windows/Python 3.14 test hotfix

- Adds explicit `Storage.close()` and context-manager support.
- Updates caption tests to close SQLite databases before temporary folders are deleted.
- Replaces the stale Render-era `test_live_96_schedule.py` with the current Cloudflare/GitHub live-scheduler tests.
- Does not change captions, leverage selection, take-profit logic, scanning, chart capture, API accounts, or the live schedule.
