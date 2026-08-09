# v0.5.6 — Free cloud restore

- Removed the active Render deployment path and its payment requirement.
- Restored the Cloudflare Cron Trigger and GitHub Actions workflow-dispatch path.
- Added `install_gh_oauth_secret.ps1` to use the already authenticated GitHub CLI OAuth token.
- The helper tests the dispatch before storing the token in Cloudflare.
- Avoids hidden prompt/clipboard mistakes by writing the tested token directly to Wrangler stdin.
- Live publishing remains controlled by `COINCOACH_LIVE_96_ENABLED`.
