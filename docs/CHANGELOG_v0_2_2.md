# v0.2.2 — Official Binance Android Chart Proof

This release adds a capture-only GitHub Actions proof for the official Binance Android app.

## Added

- `.github/workflows/manual-binance-android-proof.yml`
- Official APK URL and optional SHA-256 supplied only through GitHub Actions secrets
- APK package/activity and native-ABI preflight
- Hardware-accelerated Android x86_64 emulator on GitHub-hosted Linux
- Appium 3 + UiAutomator2 navigation
- One official-app full-screen screenshot and one square chart candidate
- UI hierarchy, Appium logs, ADB logcat and final-screen diagnostics
- Basic blank/error/symbol validation
- Hard capture-only controls: no login secrets, no trading actions, no Square publishing

## Honest limitation

The fast free GitHub emulator is x86_64. If Binance's official APK includes only ARM native libraries, the workflow stops at the ABI preflight instead of pretending it can run. The APK may also reject emulators or expose UI elements differently. The first run is a proof and calibration step, not a production claim.
