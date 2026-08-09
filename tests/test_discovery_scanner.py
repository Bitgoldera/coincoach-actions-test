from __future__ import annotations

import time
import unittest

from app.models import MarketSymbol
from app.scanner import UniverseScanner


class DiscoveryClient:
    @staticmethod
    def _symbol(base: str, quote: str, *, volume: float = 50_000_000) -> MarketSymbol:
        return MarketSymbol(
            symbol=f"{base}{quote}", base_asset=base, quote_asset=quote, status="TRADING",
            tick_size=0.0001, step_size=0.01, quote_precision=8, price=1.0,
            quote_volume_24h=volume, bid=0.999, ask=1.001,
        )

    async def universe(self, quote_asset: str):
        if quote_asset == "USDT":
            return {
                "FETUSDT": self._symbol("FET", "USDT"),
                "SOXLBUSDT": self._symbol("SOXLB", "USDT"),
            }
        if quote_asset == "USDC":
            return {"LINKUSDC": self._symbol("LINK", "USDC")}
        return {}

    async def perpetual_metadata(self):
        now_ms = int(time.time() * 1000)
        return {
            "FET": {
                "perpetual_eligible": True,
                "onboard_date_ms": now_ms,
                "categories": ["ai"],
            },
            "LINK": {
                "perpetual_eligible": True,
                "onboard_date_ms": now_ms - 100 * 86_400_000,
                "categories": ["web3"],
            },
        }


class DiscoveryScannerTest(unittest.IsolatedAsyncioTestCase):
    def settings(self) -> dict:
        return {
            "market": {
                "quote_asset": "USDT",
                "quote_assets": ["USDT", "USDC"],
                "minimum_price": 0.00000001,
                "minimum_quote_volume_usdt": 1_000_000,
                "maximum_spread_percent": 0.40,
                "shortlist_size": 20,
                "deep_scan_limit": 20,
                "timeframes": ["1h"],
                "candles_per_timeframe": 220,
                "request_concurrency": 2,
                "excluded_base_assets": [],
                "excluded_symbol_patterns": [r".*(UP|DOWN|BULL|BEAR)(USDT|USDC)$"],
                "exclude_tokenized_securities": True,
                "include_tradfi_tokenized_securities": True,
                "tokenized_security_suffix": "B",
                "crypto_assets_with_security_suffix_allowlist": ["BNB", "ARB", "CKB"],
                "discovery": {
                    "fetch_perpetual_metadata": True,
                    "new_listing_max_age_days": 45,
                    "alpha_assets": ["FET"],
                    "ai_assets": ["FET"],
                    "web3_assets": ["LINK"],
                    "category_score_boosts": {
                        "perpetual": 9.0,
                        "new_listing": 8.0,
                        "alpha": 7.0,
                        "ai": 5.0,
                        "web3": 4.0,
                        "usdc": 3.0,
                        "tradfi": 2.0,
                    },
                },
            }
        }

    async def test_usdc_perpetual_new_listing_alpha_ai_web3_and_tradfi_are_tagged(self):
        scanner = UniverseScanner(DiscoveryClient(), self.settings())  # type: ignore[arg-type]
        shortlist = await scanner.shortlist()
        by_symbol = {item.symbol: item for item in shortlist}

        self.assertEqual({"FETUSDT", "SOXLBUSDT", "LINKUSDC"}, set(by_symbol))
        self.assertTrue(by_symbol["FETUSDT"].perpetual_eligible)
        self.assertTrue({"perpetual", "new_listing", "alpha", "ai"}.issubset(
            set(by_symbol["FETUSDT"].market_tags)
        ))
        self.assertTrue({"perpetual", "web3", "usdc"}.issubset(
            set(by_symbol["LINKUSDC"].market_tags)
        ))
        self.assertIn("tradfi", by_symbol["SOXLBUSDT"].market_tags)
        self.assertGreater(scanner.last_filter_stats.get("eligible_tag_perpetual", 0), 0)

    async def test_tradfi_can_still_be_disabled(self):
        settings = self.settings()
        settings["market"]["include_tradfi_tokenized_securities"] = False
        scanner = UniverseScanner(DiscoveryClient(), settings)  # type: ignore[arg-type]
        shortlist = await scanner.shortlist()
        self.assertNotIn("SOXLBUSDT", {item.symbol for item in shortlist})
