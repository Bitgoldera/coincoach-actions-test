# Binance mobile chart capture calibration

The automation does not create a fake chart. It captures the real Binance mobile chart from a persistent cloud Android device.

## One-time proof of concept

1. Provision a fixed-resolution cloud Android device.
2. Install the current Binance app through a permitted channel.
3. Open public market charts manually and confirm they work on the virtual device.
4. Install and expose Appium only over a private network.
5. Pin the Android resolution and Binance app version during calibration.
6. Copy `config/mobile_calibration.example.yaml` and replace every placeholder coordinate.
7. Test BTCUSDT on 15m, 1h, 4h and 1D.
8. Confirm the crop contains only the mobile chart card and no notification banners.

## No custom watermark

The capture worker performs only crop and validation. It does not add a logo, profile header, engagement counts or watermark.

## Why calibration is required

Mobile app layouts and selectors can change. The worker fails closed when the screenshot is missing or unexpectedly small. Add stronger image validation after the first real cloud-device screenshots are available.
