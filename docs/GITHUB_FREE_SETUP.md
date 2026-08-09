# GitHub setup — v0.2.9

## 1. Apply and push

Run `install_v0_2_7_patch.ps1` against the existing repository, then commit and push.

## 2. One live mobile-web proof

Open:

`Actions → Manual official Binance mobile-web live chart proof`

Use:

- symbol: `BTCUSDT`
- timeframe: `15m`
- confirmation: `CAPTURE_ONE`

Download `official-binance-mobile-web-proof-*`.

Accepted files include:

- `BTCUSDT_15m_official_binance_mobile_live.png`
- `BTCUSDT_15m_official_binance_mobile_live.capture.json`
- `proof_summary.json`

Rejected output may include:

- `*_diagnostic.png`
- `*_page_text.txt`
- `*.capture.json`

The report must show:

- `mobile_layout_verified: true`
- `selected_timeframe_verified: true`
- `network_interval_verified: true`
- `snapshot_fresh: true`
- a small `price_deviation_percent`

## 3. Test 1h and 4h

Repeat the proof with `1h` and `4h`. Do not continue if the visible selected timeframe differs from the workflow input.

## 4. Five-image preview

Run:

`Actions → Manual official Binance mobile-web live chart preview`

The workflow intentionally blocks publishing and fails when fewer than five images pass.

## 5. One controlled Square API post

Only after the proof artifacts are visually approved, add the Square posting key as:

`BINANCE_SQUARE_KEY_ACCOUNT_01`

Then run:

`Actions → Manual Square API one-post test`

Confirmation: `POST_ONE`

Do not enable the hourly template before the published image and caption are checked manually.
