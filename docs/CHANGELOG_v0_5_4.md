# CoinCoachSignalCloud v0.5.4

## External 96-post scheduler
- Replaced the non-firing GitHub `schedule` event with Cloudflare Cron Trigger support.
- Cloudflare calls the existing live workflow through GitHub's `workflow_dispatch` API.
- Keeps exactly four base slots per hour and 96 dispatch attempts per day.
- Adds a 0–120 second timing window so every slot is not stamped at an identical second.

## Safety controls
- Keeps `COINCOACH_LIVE_96_ENABLED` as the repository kill switch.
- External triggers require both `trigger_source=cloudflare` and `confirmation=CLOUDFLARE_SLOT`.
- Manual live runs still require `RUN_LIVE_SLOT`.
- GitHub token is stored only as a Cloudflare encrypted secret.
- Keeps one post per keyed account per run, 96/day cap, reserve candidates, symbol cooldown and verified 1080×1080 capture.

## Cleanup
- The installer removes the temporary `schedule-heartbeat.yml` diagnostic workflow.
- GitHub's own cron is removed from the live workflow to prevent duplicate slots if it later recovers.
