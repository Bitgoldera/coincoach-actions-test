# v0.6.0 setup — account_02 to Discord, Facebook, Instagram and Threads

## 1. Stop the current automation first

```powershell
$repo = "HarshitPatidarOfficial/coincoach-signal-cloud"
$gh = "C:\Program Files\GitHub CLI\gh.exe"

& $gh variable set COINCOACH_LIVE_96_ENABLED `
  --body "false" `
  --repo $repo

& $gh variable get COINCOACH_LIVE_96_ENABLED --repo $repo
```

The final command must print:

```text
false
```

Also cancel any already-running live workflow in GitHub Actions.

## 2. Install the patch

Extract the patch ZIP outside the main project, then run:

```powershell
powershell -ExecutionPolicy Bypass `
  -File "D:\CoinCoachSignalCloud_v0_6_0\CoinCoachSignalCloud_v0_6_0\install_v0_6_0_patch.ps1" `
  -Target "D:\CoinCoachSignalCloud_v0_1_5\CoinCoachSignalCloud_v0_1_5"
```

The installer checks that `COINCOACH_LIVE_96_ENABLED` is `false`, backs up every
changed file, applies the patch, compiles Python, parses YAML and runs all tests.

## 3. Commit and push while social publishing remains OFF

```powershell
cd "D:\CoinCoachSignalCloud_v0_1_5\CoinCoachSignalCloud_v0_1_5"

git status --short
git add -A
git commit -m "Add account 02 social syndication"
git push origin main
```

## 4. Add GitHub Secrets

Add only the credentials for platforms you will test. Use GitHub repository
Settings → Secrets and variables → Actions → Secrets.

Required names:

```text
DISCORD_WEBHOOK_URL
FACEBOOK_PAGE_ID
FACEBOOK_PAGE_ACCESS_TOKEN
INSTAGRAM_USER_ID
INSTAGRAM_ACCESS_TOKEN
THREADS_USER_ID
THREADS_ACCESS_TOKEN
CLOUDINARY_CLOUD_NAME
CLOUDINARY_API_KEY
CLOUDINARY_API_SECRET
```

Notes:

- Discord needs only `DISCORD_WEBHOOK_URL`.
- Facebook, Instagram and Threads use the Cloudinary credentials to make the
  generated chart temporarily reachable by their publishing APIs.
- `INSTAGRAM_ACCESS_TOKEN` may be the token specifically issued for the connected
  professional Instagram account.
- Never put these values in `.env`, source code, screenshots or chat messages.

## 5. Add GitHub Variables, all OFF

```powershell
& $gh variable set COINCOACH_SOCIAL_SYNDICATION_ENABLED --body "false" --repo $repo
& $gh variable set COINCOACH_SOCIAL_LIVE_APPROVED --body "false" --repo $repo
& $gh variable set COINCOACH_DISCORD_PUBLISH_ENABLED --body "false" --repo $repo
& $gh variable set COINCOACH_FACEBOOK_PUBLISH_ENABLED --body "false" --repo $repo
& $gh variable set COINCOACH_INSTAGRAM_PUBLISH_ENABLED --body "false" --repo $repo
& $gh variable set COINCOACH_THREADS_PUBLISH_ENABLED --body "false" --repo $repo
```

Set the Meta Graph API version supported by your current Meta app:

```powershell
& $gh variable set META_GRAPH_API_VERSION --body "vXX.X" --repo $repo
```

Optional Threads base override:

```powershell
& $gh variable set THREADS_API_BASE_URL `
  --body "https://graph.threads.net/v1.0" `
  --repo $repo
```

## 6. Run the first pilot with Discord only

Keep `COINCOACH_LIVE_96_ENABLED=false`.

In GitHub:

```text
Actions
→ Manual account_02 Square + social pilot
→ Run workflow
```

Use:

```text
Confirmation: POST_ACCOUNT_02_SOCIAL_PILOT
Discord: true
Facebook: false
Instagram: false
Threads: false
```

This creates one normal account_02 Square signal and sends the same caption and
chart to Discord. The workflow fails if the selected social delivery fails.

Then test Facebook, Instagram and Threads one at a time before selecting all four.

## 7. Enable automatic account_02 fan-out

After every selected platform passes its pilot:

```powershell
& $gh variable set COINCOACH_DISCORD_PUBLISH_ENABLED --body "true" --repo $repo
& $gh variable set COINCOACH_FACEBOOK_PUBLISH_ENABLED --body "true" --repo $repo
& $gh variable set COINCOACH_INSTAGRAM_PUBLISH_ENABLED --body "true" --repo $repo
& $gh variable set COINCOACH_THREADS_PUBLISH_ENABLED --body "true" --repo $repo

& $gh variable set COINCOACH_SOCIAL_LIVE_APPROVED --body "true" --repo $repo
& $gh variable set COINCOACH_SOCIAL_SYNDICATION_ENABLED --body "true" --repo $repo
```

Finally restart the original automation:

```powershell
& $gh variable set COINCOACH_LIVE_96_ENABLED --body "true" --repo $repo
& $gh variable get COINCOACH_LIVE_96_ENABLED --repo $repo
```

Expected:

```text
true
```

## Final routing

```text
account_01 → Binance Square only
account_02 → Binance Square, then Discord/Facebook/Instagram/Threads
account_03 → Binance Square only
account_04 → Binance Square only
account_05 → Binance Square only
account_06 → Binance Square only
```

## Emergency social stop

This stops social fan-out without stopping Binance:

```powershell
& $gh variable set COINCOACH_SOCIAL_SYNDICATION_ENABLED --body "false" --repo $repo
```

The six-account Binance Square automation continues unchanged.
