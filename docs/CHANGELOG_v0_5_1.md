# v0.5.1 — reliable one-post Square pilot

## Fixed

- The live one-post workflow now recognizes that a valid Binance Square API key is present and separates publisher failures from chart-capture failures.
- Exact timeframe controls can now be activated safely when Binance temporarily covers the button with a sticky or transparent element. The fallback invokes the previously validated exact timeframe DOM control; it never uses blind coordinates or anonymous toolbar buttons.
- The live pilot now generates reserve signal candidates. If one official Binance chart cannot be captured, the system tries the next candidate instead of ending the run immediately.
- Each chart candidate receives bounded outer retries in addition to the capture class's internal retries.
- A publisher/API exception is never followed by another publication attempt, avoiding possible duplicate posts when the remote response is ambiguous.

## Safety

- The workflow still publishes at most one post per keyed account.
- MA overlays remain allowed, matching the approved chart style.
- Symbol, visible selected timeframe, live price, freshness, and image validation remain enabled.
- No coordinate click was added.
