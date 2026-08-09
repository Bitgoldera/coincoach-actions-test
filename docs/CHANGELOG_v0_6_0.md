# CoinCoach Signal Cloud v0.6.0

## Account 02 social syndication

This patch adds an isolated social-media delivery layer after a confirmed
Binance Square publish for `account_02`.

### Unchanged

- Six Binance Square API account matrix
- Cloudflare 15-minute dispatch cadence
- Four signals per hour per configured Binance account
- Scanner, routing, captions, leverage, TP/SL calculations
- Official Binance mobile-web image capture and 1:1 crop
- Per-account database, publish ledger, cache and artifacts
- Existing Square publish safety gates

### Added

- Discord webhook image publishing
- Facebook Page photo publishing
- Instagram single-image publishing
- Threads single-image publishing
- Cloudinary public-image bridge for Meta destinations
- Persistent account_02 social outbox and per-platform status
- Independent platform failures and pending-delivery retry
- Dedicated manual account_02 Square + social pilot workflow
- Social pilot result validator
- Repository variables and secrets wired into the existing live workflow

### Safety behavior

- All new social switches default to `false`.
- Installing the patch does not enable any social publishing.
- Only `account_02` can enter the social publishing path.
- Social delivery starts only after Square returns a confirmed success.
- A social failure cannot mark Square failed or trigger a replacement signal.
- The pilot workflow requires `POST_ACCOUNT_02_SOCIAL_PILOT`.
