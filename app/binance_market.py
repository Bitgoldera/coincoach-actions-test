from __future__ import annotations

import asyncio
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import httpx

from .models import Candle, MarketSymbol


class BinanceMarketClient:
    """Public market-data client. It never uses a trading API key."""

    def __init__(self, base_url: str = "https://data-api.binance.vision", timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    async def close(self) -> None:
        await self.client.aclose()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = await self.client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    async def universe(self, quote_asset: str = "USDT") -> dict[str, MarketSymbol]:
        exchange_info, tickers, books = await asyncio.gather(
            self._get("/api/v3/exchangeInfo"),
            self._get("/api/v3/ticker/24hr"),
            self._get("/api/v3/ticker/bookTicker"),
        )
        ticker_by_symbol = {row["symbol"]: row for row in tickers}
        book_by_symbol = {row["symbol"]: row for row in books}
        universe: dict[str, MarketSymbol] = {}
        normalized_quote = str(quote_asset).upper().strip()
        for row in exchange_info.get("symbols", []):
            if row.get("quoteAsset") != normalized_quote or row.get("status") != "TRADING":
                continue
            if not row.get("isSpotTradingAllowed", True):
                continue
            permission_sets = row.get("permissionSets") or row.get("permissionsSets") or []
            legacy_permissions = row.get("permissions") or []
            if permission_sets:
                if not any("SPOT" in permission_set for permission_set in permission_sets):
                    continue
            elif legacy_permissions and "SPOT" not in legacy_permissions:
                continue
            tick_size = 0.0
            step_size = 0.0
            for item in row.get("filters", []):
                if item.get("filterType") == "PRICE_FILTER":
                    tick_size = float(item.get("tickSize", 0))
                elif item.get("filterType") == "LOT_SIZE":
                    step_size = float(item.get("stepSize", 0))
            ticker = ticker_by_symbol.get(row["symbol"], {})
            book = book_by_symbol.get(row["symbol"], {})
            universe[row["symbol"]] = MarketSymbol(
                symbol=row["symbol"],
                base_asset=row["baseAsset"],
                quote_asset=row["quoteAsset"],
                status=row["status"],
                tick_size=tick_size,
                step_size=step_size,
                quote_precision=int(row.get("quoteAssetPrecision", 8)),
                price=float(ticker.get("lastPrice", 0)),
                change_percent_24h=float(ticker.get("priceChangePercent", 0)),
                high_24h=float(ticker.get("highPrice", 0)),
                low_24h=float(ticker.get("lowPrice", 0)),
                quote_volume_24h=float(ticker.get("quoteVolume", 0)),
                bid=float(book.get("bidPrice", 0)),
                ask=float(book.get("askPrice", 0)),
            )
        return universe

    async def perpetual_metadata(self) -> dict[str, dict[str, Any]]:
        """Return best-effort USDⓈ-M perpetual metadata keyed by base asset.

        The scanner uses this only to label spot symbols that also have an active
        perpetual market. Signal prices and chart verification remain on the exact
        spot pair selected by the scanner.
        """

        response = await self.client.get("https://fapi.binance.com/fapi/v1/exchangeInfo")
        response.raise_for_status()
        payload = response.json()
        metadata: dict[str, dict[str, Any]] = {}
        for row in payload.get("symbols", []):
            if row.get("status") != "TRADING" or row.get("contractType") != "PERPETUAL":
                continue
            base_asset = str(row.get("baseAsset", "")).upper().strip()
            if not base_asset:
                continue
            raw_categories = row.get("underlyingSubType") or []
            categories = {
                str(value).strip().lower().replace(" ", "_").replace("-", "_")
                for value in raw_categories
                if str(value).strip()
            }
            if any("ai" == value or value.startswith("ai_") or value.endswith("_ai") for value in categories):
                categories.add("ai")
            if any(
                token in value
                for value in categories
                for token in ("web3", "defi", "layer_1", "layer_2", "infrastructure")
            ):
                categories.add("web3")
            onboard_date = row.get("onboardDate")
            try:
                onboard_date_ms = int(onboard_date) if onboard_date is not None else None
            except (TypeError, ValueError):
                onboard_date_ms = None

            current = metadata.get(base_asset)
            if current is None:
                metadata[base_asset] = {
                    "perpetual_eligible": True,
                    "onboard_date_ms": onboard_date_ms,
                    "categories": sorted(categories),
                    "symbols": [str(row.get("symbol", ""))],
                }
            else:
                current_categories = set(current.get("categories", []))
                current_categories.update(categories)
                current["categories"] = sorted(current_categories)
                current.setdefault("symbols", []).append(str(row.get("symbol", "")))
                previous = current.get("onboard_date_ms")
                if onboard_date_ms is not None and (previous is None or onboard_date_ms > previous):
                    current["onboard_date_ms"] = onboard_date_ms
        return metadata

    async def klines(self, symbol: str, interval: str, limit: int = 220) -> list[Candle]:
        payload = await self._get(
            "/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
        )
        return [
            Candle(
                open_time=int(row[0]),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
                close_time=int(row[6]),
                quote_volume=float(row[7]),
            )
            for row in payload
        ]


def round_to_tick(value: float, tick_size: float) -> float:
    if tick_size <= 0:
        return value
    tick = Decimal(str(tick_size))
    rounded = (Decimal(str(value)) / tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * tick
    return float(rounded)
