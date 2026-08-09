# CoinCoachSignalCloud v0.5.5

## Direct Render Cron scheduler
- Replaces the Cloudflare-to-GitHub dispatch chain with a direct Render Cron Job.
- Adds `render.yaml` with four UTC slots per hour: `6,21,36,51`.
- Adds a dedicated Docker image with Python, Node 22, Chromium, Playwright dependencies, and Binance's official Square Post Skill.
- Adds a Render entrypoint that exits after one slot and enforces a 13-minute safety timeout.

## Safety
- Live posting requires both `RENDER_LIVE_ENABLED=true` and `RENDER_LIVE_APPROVED=true`.
- Blueprint defaults keep both switches false and keep `PUBLISH_ENABLED=false`.
- The first manual Render run safely exits without scanning or publishing.
- Removes the obsolete Cloudflare Worker files and external-dispatch GitHub workflow.

## Exact total cadence with additional keys
- Default `round_robin` account mode preserves four total attempts per hour and 96 attempts per day even when more separate account keys are added.
- Optional `parallel` mode is explicit and multiplies the per-slot total.
- Unselected account keys are removed from the child process environment for each round-robin run.

## Stateless runtime support
- Adds deterministic 15-minute slot indexing.
- Rotates reserve candidates by slot to reduce repeated top-candidate selection on Render's ephemeral cron filesystem.
- Documents that SQLite cooldown and local daily-ledger files do not persist across cron instances.
