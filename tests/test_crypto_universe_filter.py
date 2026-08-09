from __future__ import annotations

import unittest

from app.models import MarketSymbol
from app.scanner import UniverseScanner


class DummyClient:
    pass


class CryptoUniverseFilterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = {
            "market": {
                "minimum_price": 0.00000001,
                "minimum_quote_volume_usdt": 10_000_000,
                "maximum_spread_percent": 0.40,
                "excluded_base_assets": ["PAXG", "USDC"],
                "excluded_symbol_patterns": [r".*(UP|DOWN|BULL|BEAR)USDT$"],
                "exclude_tokenized_securities": True,
                "tokenized_security_suffix": "B",
                "crypto_assets_with_security_suffix_allowlist": ["BNB", "ARB", "CKB", "DGB", "TRB", "VIB", "BB"],
            }
        }
        self.scanner = UniverseScanner(DummyClient(), self.settings)  # type: ignore[arg-type]

    @staticmethod
    def symbol(base: str, *, volume: float = 20_000_000) -> MarketSymbol:
        return MarketSymbol(
            symbol=f"{base}USDT", base_asset=base, quote_asset="USDT", status="TRADING",
            tick_size=0.0001, step_size=0.01, quote_precision=8, price=1.0,
            quote_volume_24h=volume, bid=0.999, ask=1.001,
        )

    def test_known_bstocks_are_rejected(self) -> None:
        for base in ["SOXLB", "SNDKB", "SKHYB", "EWYB", "MUB"]:
            with self.subTest(base=base):
                self.assertEqual(
                    self.scanner.eligibility_reason(self.symbol(base)),
                    "tokenized_security_or_unclassified_suffix",
                )

    def test_real_crypto_assets_ending_b_are_preserved(self) -> None:
        for base in ["BNB", "ARB", "CKB", "DGB", "TRB", "VIB", "BB"]:
            with self.subTest(base=base):
                self.assertIsNone(self.scanner.eligibility_reason(self.symbol(base)))

    def test_tokenized_gold_is_rejected_for_crypto_only_feed(self) -> None:
        self.assertEqual(self.scanner.eligibility_reason(self.symbol("PAXG")), "excluded_base_asset")


if __name__ == "__main__":
    unittest.main()
