# v0.4.3 — protect the live price from top cropping

- Detects the large live-price text in the official Binance mobile viewport.
- Clamps the crop top so the full price stays visible with a 10px safety margin.
- Keeps a small controlled vertical variation, but never allows that variation to cut the live price.
- Reduces the default downward shift from 32px to 8px and narrows jitter to -6px…+10px.
- Keeps the 1080×1350 output and existing clear-drawings safety fixes.
