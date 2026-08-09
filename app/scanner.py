from __future__ import annotations

import asyncio
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from .binance_market import BinanceMarketClient
from .models import Candle, MarketSymbol


@dataclass(slots=True)
class DeepScanItem:
    symbol: MarketSymbol
    timeframe: str
    candles: list[Candle]


class UniverseScanner:
    def __init__(self, client: BinanceMarketClient, settings: dict) -> None:
        self.client = client
        self.settings = settings
        self.last_filter_stats: dict[str, int] = {}

    def eligibility_reason(self, symbol: MarketSymbol) -> str | None:
        """Return None when eligible, otherwise a stable exclusion reason."""

        cfg = self.settings["market"]
        base_asset = symbol.base_asset.upper()
        excluded_assets = {str(value).upper() for value in cfg.get("excluded_base_assets", [])}
        patterns = [re.compile(str(value), re.IGNORECASE) for value in cfg.get("excluded_symbol_patterns", [])]

        if base_asset in excluded_assets:
            return "excluded_base_asset"

        if cfg.get("exclude_tokenized_securities", False):
            suffix = str(cfg.get("tokenized_security_suffix", "B")).upper()
            allowed = {str(value).upper() for value in cfg.get("crypto_assets_with_security_suffix_allowlist", [])}
            include_tradfi = bool(cfg.get("include_tradfi_tokenized_securities", False))
            if suffix and base_asset.endswith(suffix) and base_asset not in allowed and not include_tradfi:
                return "tokenized_security_or_unclassified_suffix"

        if any(pattern.fullmatch(symbol.symbol) for pattern in patterns):
            return "excluded_symbol_pattern"
        if symbol.price < float(cfg["minimum_price"]):
            return "price_below_minimum"
        if symbol.quote_volume_24h < float(cfg["minimum_quote_volume_usdt"]):
            return "volume_below_minimum"
        if symbol.spread_percent > float(cfg["maximum_spread_percent"]):
            return "spread_above_maximum"
        return None

    def _annotate_discovery_tags(
        self,
        symbol: MarketSymbol,
        perpetual_metadata: dict[str, dict],
        now_ms: int,
    ) -> None:
        cfg = self.settings["market"]
        discovery = cfg.get("discovery", {})
        base = symbol.base_asset.upper()
        tags: set[str] = set()

        if symbol.quote_asset.upper() == "USDC":
            tags.add("usdc")

        suffix = str(cfg.get("tokenized_security_suffix", "B")).upper()
        suffix_allowlist = {
            str(value).upper()
            for value in cfg.get("crypto_assets_with_security_suffix_allowlist", [])
        }
        if suffix and base.endswith(suffix) and base not in suffix_allowlist:
            tags.add("tradfi")

        alpha_assets = {str(value).upper() for value in discovery.get("alpha_assets", [])}
        ai_assets = {str(value).upper() for value in discovery.get("ai_assets", [])}
        web3_assets = {str(value).upper() for value in discovery.get("web3_assets", [])}
        if base in alpha_assets:
            tags.add("alpha")
        if base in ai_assets:
            tags.add("ai")
        if base in web3_assets:
            tags.add("web3")

        metadata = perpetual_metadata.get(base)
        if metadata:
            symbol.perpetual_eligible = bool(metadata.get("perpetual_eligible", False))
            symbol.onboard_date_ms = metadata.get("onboard_date_ms")
            if symbol.perpetual_eligible:
                tags.add("perpetual")
            tags.update(str(value).lower() for value in metadata.get("categories", []))

            max_age_days = int(discovery.get("new_listing_max_age_days", 45))
            onboard_ms = symbol.onboard_date_ms
            if onboard_ms is not None and max_age_days > 0:
                age_ms = max(0, now_ms - int(onboard_ms))
                if age_ms <= max_age_days * 86_400_000:
                    tags.add("new_listing")

        symbol.market_tags = tuple(sorted(tags))

    async def shortlist(self) -> list[MarketSymbol]:
        cfg = self.settings["market"]
        quote_assets = [
            str(value).upper().strip()
            for value in cfg.get("quote_assets", [cfg.get("quote_asset", "USDT")])
            if str(value).strip()
        ]
        if not quote_assets:
            quote_assets = [str(cfg.get("quote_asset", "USDT")).upper()]

        universe_results = await asyncio.gather(
            *(self.client.universe(quote_asset) for quote_asset in quote_assets)
        )
        universe: dict[str, MarketSymbol] = {}
        stats: dict[str, int] = {"raw_spot_total": 0, "eligible": 0}
        for quote_asset, quote_universe in zip(quote_assets, universe_results):
            universe.update(quote_universe)
            stats[f"raw_spot_{quote_asset.lower()}"] = len(quote_universe)
            stats["raw_spot_total"] += len(quote_universe)

        discovery = cfg.get("discovery", {})
        perpetual_metadata: dict[str, dict] = {}
        if bool(discovery.get("fetch_perpetual_metadata", True)):
            try:
                perpetual_metadata = await self.client.perpetual_metadata()
            except Exception:
                # Discovery metadata is a ranking enhancement. Spot scanning stays
                # available if the separate futures metadata endpoint is unavailable.
                stats["perpetual_metadata_unavailable"] = 1

        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        filtered: list[MarketSymbol] = []
        for symbol in universe.values():
            self._annotate_discovery_tags(symbol, perpetual_metadata, now_ms)
            reason = self.eligibility_reason(symbol)
            if reason is None:
                filtered.append(symbol)
                stats["eligible"] += 1
                for tag in symbol.market_tags:
                    stats[f"eligible_tag_{tag}"] = stats.get(f"eligible_tag_{tag}", 0) + 1
            else:
                stats[reason] = stats.get(reason, 0) + 1
        self.last_filter_stats = stats

        category_boosts = {
            str(key).lower(): float(value)
            for key, value in discovery.get("category_score_boosts", {}).items()
        }

        def fast_score(item: MarketSymbol) -> float:
            volume_component = math.log10(max(item.quote_volume_24h, 1)) * 7
            movement_component = min(abs(item.change_percent_24h), 40) * 1.4
            range_component = 0.0
            if item.low_24h > 0:
                range_component = min(((item.high_24h - item.low_24h) / item.low_24h) * 100, 50)
            spread_penalty = item.spread_percent * 12
            discovery_boost = sum(category_boosts.get(tag, 0.0) for tag in item.market_tags)
            return volume_component + movement_component + range_component + discovery_boost - spread_penalty

        filtered.sort(key=fast_score, reverse=True)
        return filtered[: int(cfg["shortlist_size"])]

    async def deep_scan(self, symbols: list[MarketSymbol]) -> list[DeepScanItem]:
        cfg = self.settings["market"]
        semaphore = asyncio.Semaphore(int(cfg["request_concurrency"]))
        timeframes: list[str] = list(cfg["timeframes"])
        limit = int(cfg["candles_per_timeframe"])
        symbols = symbols[: int(cfg["deep_scan_limit"])]

        async def fetch(symbol: MarketSymbol, timeframe: str) -> DeepScanItem | None:
            async with semaphore:
                try:
                    candles = await self.client.klines(symbol.symbol, timeframe, limit)
                    if len(candles) < 80:
                        return None
                    return DeepScanItem(symbol=symbol, timeframe=timeframe, candles=candles)
                except Exception:
                    return None

        tasks = [fetch(symbol, timeframe) for symbol in symbols for timeframe in timeframes]
        results = await asyncio.gather(*tasks)
        return [item for item in results if item is not None]
