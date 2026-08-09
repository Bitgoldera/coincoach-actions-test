# v0.2.3 — Automatic official APK + ARM64 proof

- Removes the need for `BINANCE_ANDROID_APK_URL` GitHub Secret.
- Downloads from Binance-controlled `download.binance.com` only.
- Verifies package name `com.binance.dev`.
- Verifies the Binance APK signing-certificate SHA-256 fingerprint before install.
- Moves the proof job to an Apple-silicon GitHub runner.
- Boots an ARM64 Android system image so the official ARM64 Binance APK is compatible.
- Keeps publishing, login, trading, buying, selling, transfers, and Square posting disabled.
