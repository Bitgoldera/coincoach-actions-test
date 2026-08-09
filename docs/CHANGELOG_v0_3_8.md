# v0.3.8 — visible-only clear-drawings detection

- Fixed the repeated `Binance clear-drawings confirmation is visible` failure.
- Binance keeps destructive drawing labels in hidden DOM/accessibility nodes; previous code scanned the whole page body and treated hidden text as an open modal.
- Detection now accepts only a genuinely visible dialog/modal container or the visual modal signature.
- Cancellation searches only inside the visible destructive dialog and clicks safe buttons such as Cancel/No/Close.
- Anonymous chart and toolbar controls are never clicked while dismissing the dialog.
- Added browser tests for hidden destructive text and safe cancellation of a visible dialog.
- Publishing remains disabled in the manual proof workflow.
