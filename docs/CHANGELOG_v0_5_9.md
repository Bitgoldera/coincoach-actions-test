# v0.5.9 — Parallel API account delivery

## Problem fixed

The live slot previously processed API accounts in one sequential Python loop. Account 02
waited for account 01, account 03 waited for both, and account 04 could reach the workflow
timeout after earlier chart captures or API retries. This caused increasing delays and missed
hourly posts on later accounts.

## New behavior

- Each Cloudflare slot starts one independent GitHub Actions matrix job per configured API account.
- Up to six API accounts run in parallel.
- `fail-fast: false` prevents one account failure from cancelling the others.
- Each account gets isolated SQLite, publish-ledger, cache, and artifacts.
- Each configured account still publishes at most one post per slot: four scheduled attempts per
  hour and 96 per UTC day.
- Existing captions, leverage selection, TP logic, scanner, chart format, and Cloudflare schedule
  are unchanged.

## Reliability note

The patch removes account-to-account blocking. It cannot guarantee a successful remote publish
when GitHub, Binance, networking, or live chart capture is unavailable, but one account's failure
no longer delays or suppresses the others.
