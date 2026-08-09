# Changelog v0.1.7

- Adds screenshot-level visual detection for Binance's destructive clear-drawings dialog, including dialogs rendered inside chart frames.
- Tries Escape first, then clicks only the visually identified left-side Cancel button; it never clicks the yellow Confirm button.
- Restricts timeframe selection to compact controls inside the expected chart toolbar band.
- Rejects blank or unloaded charts using candle/volume pixel activity checks.
- Moves every rejected PNG to a `_diagnostic.png` filename so failed captures cannot be mistaken for publishable images.
- Adds synthetic visual-detector tests and validates the detector against the popup screenshots reported during v0.1.6 testing.
- Publishing remains disabled.
