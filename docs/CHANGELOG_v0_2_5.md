# v0.2.5 — Network-Verified Timeframe Capture

This patch addresses the GitHub proof failure where selecting a timeframe opened Binance's clear-drawings confirmation.

Changes:

- observes Binance's real kline requests and accepts the requested timeframe when it is already loaded
- avoids screen-coordinate clicks for timeframe selection
- uses a native DOM activation only when a change is actually required
- verifies the requested interval from the official Binance kline request after activation
- searches every page frame for the Cancel button if Binance opens the drawings dialog
- rejects the candidate if a timeframe activation triggers the destructive dialog
- keeps Square publishing disabled in proof workflows

The official Binance page itself is still the image source. No custom chart is drawn.
