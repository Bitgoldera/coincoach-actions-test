# CoinCoach per-account social architecture

This version keeps the existing CoinCoach generation, Binance Square publishing,
chart capture, account isolation, ledger limits, reserve candidates, and live
slot workflow unchanged. The social layer is now **per account** instead of being
hard-routed to account_02.

## Runtime rule

1. Generate the signal/caption/chart exactly as before.
2. Publish the post to the active account's Binance Square.
3. Only after Square reports success, inspect that account's social credentials.
4. If no social destination is connected, finish with Binance only.
5. If one or more destinations are connected and `SOCIAL_LIVE_APPROVED=true`,
   send the same caption/image to those destinations.
6. A social failure never turns a confirmed Square publish into a failed Square publish.

## GitHub Secrets

Each account can have its own credentials. The workflow maps the following secret
names into generic runtime variables for the active matrix job:

- `BINANCE_SQUARE_KEY_ACCOUNT_01` ... `ACCOUNT_06`
- `DISCORD_WEBHOOK_URL_ACCOUNT_01` ... `ACCOUNT_06`
- `FACEBOOK_PAGE_ID_ACCOUNT_01` ... `ACCOUNT_06`
- `FACEBOOK_PAGE_ACCESS_TOKEN_ACCOUNT_01` ... `ACCOUNT_06`
- `INSTAGRAM_USER_ID_ACCOUNT_01` ... `ACCOUNT_06`
- `INSTAGRAM_ACCESS_TOKEN_ACCOUNT_01` ... `ACCOUNT_06`
- `THREADS_USER_ID_ACCOUNT_01` ... `ACCOUNT_06`
- `THREADS_ACCESS_TOKEN_ACCOUNT_01` ... `ACCOUNT_06`
- `CLOUDINARY_CLOUD_NAME_ACCOUNT_01` ... `ACCOUNT_06`
- `CLOUDINARY_API_KEY_ACCOUNT_01` ... `ACCOUNT_06`
- `CLOUDINARY_API_SECRET_ACCOUNT_01` ... `ACCOUNT_06`

Do not commit real credentials to the repository.

## Connection behavior

The application treats a destination as connected only when the destination's
workflow switch is enabled **and** all required credentials are present. Therefore
blank social secrets cannot accidentally cause a social API request.

Required credentials:

- Discord: webhook URL.
- Facebook: page ID + page access token + Cloudinary credentials + Meta Graph API version.
- Instagram: user ID + access token + Cloudinary credentials + Meta Graph API version.
- Threads: user ID + access token + Cloudinary credentials.

`COINCOACH_SOCIAL_LIVE_APPROVED` is the repository-level safety gate. Keep it
`false` until the connected social destinations have been tested.

## Account ownership

The codebase can be shared with friends, but each person should put only their
own Binance/social credentials into their own GitHub Secrets. Never share API keys
or access tokens in the source code.
