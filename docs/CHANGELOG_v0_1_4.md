# v0.1.4

- Fixed awkward stacked openers such as `guys, worth a look, $XRP...`.
- `guys` now replaces the normal opener instead of being prepended to it.
- Fixed missing punctuation in lines such as `this one looks clean $LINK...`.
- Added observation-memory checks so the same market sentence is not repeated within a five-post batch when alternatives exist.
- Reworded several rejection observations to sound more natural.
- Added XAUT to the default crypto-only exclusion list.
- Added caption grammar and observation-diversity tests.
