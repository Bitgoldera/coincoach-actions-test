from __future__ import annotations

import io
import json
import math
import random
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from PIL import Image

from .web_capture import (
    VisualCaptureInspection,
    WebCaptureError,
    build_binance_url,
    contains_destructive_modal,
    resolve_symbol_quote,
    inspect_capture_image,
)


FORBIDDEN_CONTROL_WORDS = (
    "delete",
    "clear",
    "drawing",
    "remove",
    "trash",
    "reset",
)

TIMEFRAME_ALIASES: dict[str, tuple[str, ...]] = {
    "15m": ("15m", "15M"),
    "1h": ("1h", "1H"),
    "4h": ("4h", "4H"),
    "1d": ("1d", "1D"),
}

TIMEFRAME_SECONDS: dict[str, int] = {
    "15m": 15 * 60,
    "1h": 60 * 60,
    "4h": 4 * 60 * 60,
    "1d": 24 * 60 * 60,
}

_NUMBER_RE = re.compile(r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")


def normalize_timeframe(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized not in TIMEFRAME_ALIASES:
        raise WebCaptureError(f"Unsupported timeframe: {value}")
    return normalized


def extract_kline_interval(url: str) -> str | None:
    """Return the interval from a Binance kline/candlestick request URL."""

    try:
        parsed = urlparse(str(url))
    except Exception:
        return None
    path = parsed.path.lower()
    query = parsed.query.lower()
    combined = f"{path}?{query}"
    stream_match = re.search(r"@kline_(15m|1h|4h|1d)(?:@|/|&|$)", combined, re.I)
    if stream_match:
        try:
            return normalize_timeframe(stream_match.group(1))
        except WebCaptureError:
            return None
    if "kline" not in path and "kline" not in query and "candlestick" not in combined:
        return None
    values = parse_qs(parsed.query).get("interval", [])
    if not values:
        return None
    try:
        return normalize_timeframe(str(values[0]).strip())
    except WebCaptureError:
        return None


def extract_kline_interval_from_payload(payload: str | bytes) -> str | None:
    """Extract a Binance kline interval from a WebSocket frame payload.

    Binance may open a generic multiplexed WebSocket URL and subscribe to kline streams
    later through JSON frames. Tracking only the socket URL can therefore miss the real
    timeframe even when the official chart is correctly loading it.
    """

    if isinstance(payload, bytes):
        try:
            value = payload.decode("utf-8", errors="ignore")
        except Exception:
            return None
    else:
        value = str(payload)
    lowered = value.lower()
    if "kline" not in lowered and "candlestick" not in lowered:
        return None

    patterns = (
        r"@kline_(15m|1h|4h|1d)(?:@|[\"'/,}\]]|$)",
        r"[\"']interval[\"']\s*:\s*[\"'](15m|1h|4h|1d)[\"']",
        r"[\"']period[\"']\s*:\s*[\"'](15m|1h|4h|1d)[\"']",
    )
    for pattern in patterns:
        match = re.search(pattern, lowered, re.I)
        if match:
            try:
                return normalize_timeframe(match.group(1))
            except WebCaptureError:
                return None
    return None


def parse_numeric_text(value: str) -> list[float]:
    values: list[float] = []
    for match in _NUMBER_RE.finditer(str(value)):
        try:
            parsed = float(match.group(0).replace(",", ""))
        except ValueError:
            continue
        if math.isfinite(parsed) and parsed > 0:
            values.append(parsed)
    return values


def price_deviation_percent(observed: float, reference: float) -> float:
    if observed <= 0 or reference <= 0:
        return float("inf")
    return abs(observed - reference) / reference * 100.0


def snapshot_is_fresh(
    latest_kline_open_time_ms: int,
    timeframe: str,
    now_ms: int,
    grace_seconds: int = 300,
) -> bool:
    interval_ms = TIMEFRAME_SECONDS[normalize_timeframe(timeframe)] * 1000
    age_ms = max(0, now_ms - int(latest_kline_open_time_ms))
    return age_ms <= interval_ms + max(0, int(grace_seconds)) * 1000


def square_mobile_clip(
    *,
    viewport_width: float,
    viewport_height: float,
    timeframe_y: float,
    chart_bottom: float,
    price_header_y: float | None = None,
    top_padding: float = 14.0,
    minimum_chart_pixels: float = 170.0,
    header_above_timeframe: float | None = None,
) -> dict[str, float]:
    """Build a square mobile crop that matches the chart-card look users expect.

    The crop should start near the big live price block, not from the very top of the
    Binance page. This removes the Binance logo / signup header while preserving the
    live price, 24h stats, timeframe row and a meaningful portion of the candle area.
    """

    width = max(1.0, float(viewport_width))
    height = max(1.0, float(viewport_height))
    crop_height = min(width, height)

    if price_header_y is None:
        legacy_offset = 205.0 if header_above_timeframe is None else float(header_above_timeframe)
        price_header_y = float(timeframe_y) - legacy_offset

    header_y = max(0.0, float(price_header_y) - max(0.0, float(top_padding)))
    latest_top = max(0.0, min(float(timeframe_y) - 130.0, height - crop_height))
    top = max(0.0, min(header_y, latest_top, height - crop_height))

    visible_chart = float(chart_bottom) - top
    if visible_chart < float(minimum_chart_pixels):
        deficit = float(minimum_chart_pixels) - visible_chart
        top = max(0.0, top - deficit)

    top = max(0.0, min(top, height - crop_height))
    return {"x": 0.0, "y": top, "width": width, "height": crop_height}


def tall_mobile_clip(
    *,
    viewport_width: float,
    viewport_height: float,
    pair_bottom_y: float,
    timeframe_y: float,
    chart_bottom: float,
    price_top_y: float | None = None,
    aspect_ratio: float = 0.8,
    top_padding: float = 4.0,
    minimum_chart_pixels: float = 250.0,
    base_down_shift_pixels: float = 0.0,
    vertical_jitter_pixels: float = 0.0,
    timeframe_safe_margin_pixels: float = 85.0,
    price_safe_padding_pixels: float = 10.0,
) -> dict[str, float]:
    """Build a 4:5 mobile crop without cutting the large live price.

    The crop may move slightly between captures, but its top edge is clamped above
    the detected live-price text. This keeps the entire price visible even when the
    pair-name section has been scrolled just outside the viewport.
    """

    width = max(1.0, float(viewport_width))
    height = max(1.0, float(viewport_height))
    ratio = max(0.55, min(1.0, float(aspect_ratio)))
    crop_height = min(height, width / ratio)

    requested_top = (
        float(pair_bottom_y)
        + max(0.0, float(top_padding))
        + float(base_down_shift_pixels)
        + float(vertical_jitter_pixels)
    )
    maximum_viewport_top = max(0.0, height - crop_height)
    maximum_timeframe_top = max(
        0.0,
        float(timeframe_y) - max(0.0, float(timeframe_safe_margin_pixels)),
    )

    maximum_price_top = maximum_viewport_top
    if price_top_y is not None and math.isfinite(float(price_top_y)):
        maximum_price_top = max(
            0.0,
            float(price_top_y) - max(0.0, float(price_safe_padding_pixels)),
        )

    top = max(
        0.0,
        min(
            requested_top,
            maximum_viewport_top,
            maximum_timeframe_top,
            maximum_price_top,
        ),
    )

    visible_chart = min(float(chart_bottom), top + crop_height) - max(float(timeframe_y), top)
    if visible_chart < float(minimum_chart_pixels):
        top = max(0.0, top - (float(minimum_chart_pixels) - visible_chart))

    top = min(top, maximum_viewport_top, maximum_timeframe_top, maximum_price_top)
    return {"x": 0.0, "y": top, "width": width, "height": crop_height}


@dataclass(frozen=True, slots=True)
class KlineObservation:
    interval: str
    url: str
    observed_monotonic: float


class KlineIntervalTracker:
    """Track the actual chart interval requested by the official Binance page."""

    def __init__(self) -> None:
        self.observations: list[KlineObservation] = []

    def mark(self) -> int:
        return len(self.observations)

    def _record(self, interval: str | None, source: str) -> None:
        if interval:
            self.observations.append(
                KlineObservation(
                    interval=interval,
                    url=str(source),
                    observed_monotonic=time.monotonic(),
                )
            )

    def observe_url(self, url: str) -> None:
        self._record(extract_kline_interval(url), str(url))

    def observe_payload(self, payload: str | bytes) -> None:
        preview = payload.decode("utf-8", errors="ignore") if isinstance(payload, bytes) else str(payload)
        self._record(extract_kline_interval_from_payload(payload), f"websocket-frame:{preview[:500]}")

    def latest_interval(self) -> str | None:
        if not self.observations:
            return None
        return self.observations[-1].interval

    def seen_after(self, timeframe: str, marker: int) -> bool:
        normalized = normalize_timeframe(timeframe)
        return any(item.interval == normalized for item in self.observations[max(0, marker) :])

    async def wait_for_after(self, page, timeframe: str, marker: int, timeout_ms: int) -> bool:
        elapsed = 0
        step = 200
        while elapsed <= timeout_ms:
            if self.seen_after(timeframe, marker):
                return True
            await page.wait_for_timeout(step)
            elapsed += step
        return self.seen_after(timeframe, marker)


@dataclass(frozen=True, slots=True)
class LiveMarketSnapshot:
    symbol: str
    timeframe: str
    current_price: float
    high_24h: float
    low_24h: float
    base_volume_24h: float
    quote_volume_24h: float
    latest_kline_open_time_ms: int
    fetched_at_ms: int


@dataclass(slots=True)
class OfficialWebCaptureReport:
    symbol: str
    timeframe: str
    url: str
    attempts: int
    mobile_layout_verified: bool
    selected_timeframe_verified: bool
    selected_timeframe_reason: str
    network_interval_verified: bool
    live_price_reference: float | None
    visible_price: float | None
    price_deviation_percent: float | None
    latest_kline_open_time_ms: int | None
    snapshot_fresh: bool
    ma_overlay_removed: bool | None
    screenshot_path: str | None
    diagnostic_path: str | None
    page_text_path: str | None
    candle_pixel_ratio: float | None
    output_dimensions: str | None
    status: str
    error: str | None = None


class OfficialBinanceWebChartCapture:
    """Capture the official Binance mobile-web chart using live, verified state.

    The class never renders candles and never fabricates Binance UI. It opens the official
    Binance Spot page with Android mobile emulation, selects the exact signal timeframe,
    proves the interval from Binance's own kline request, compares the visible page price
    with a fresh Binance public market snapshot, then crops only the mobile chart card.

    Fail-closed rule: wrong symbol, wrong timeframe, stale market snapshot, popup, blank
    chart, desktop layout or price mismatch means no final image and therefore no post.
    """

    def __init__(self, root: Path, settings: dict[str, Any]) -> None:
        self.root = root
        self.settings = settings
        self.capture_cfg = settings["capture"]
        self.web_cfg = self.capture_cfg["web"]

    async def capture(self, symbol: str, timeframe: str, output_path: Path) -> Path:
        if not self.capture_cfg.get("web_enabled", False):
            raise WebCaptureError("Official Binance mobile-web capture is disabled")

        normalized_timeframe = normalize_timeframe(timeframe)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        report_path = output_path.with_suffix(".capture.json")
        diagnostic_path = output_path.with_name(output_path.stem + "_diagnostic.png")
        page_text_path = output_path.with_name(output_path.stem + "_page_text.txt")
        market_cfg = self.settings["market"]
        quote = resolve_symbol_quote(
            symbol,
            market_cfg.get("quote_assets", [market_cfg.get("quote_asset", "USDT")]),
        )
        url = build_binance_url(
            str(self.web_cfg["url_template"]),
            symbol,
            quote,
        )
        max_attempts = int(self.web_cfg.get("max_attempts", 2))
        last_error: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            output_path.unlink(missing_ok=True)
            diagnostic_path.unlink(missing_ok=True)
            page_text_path.unlink(missing_ok=True)
            try:
                snapshot = await self._fetch_live_snapshot(symbol, normalized_timeframe)
                result = await self._capture_attempt(
                    symbol=symbol,
                    timeframe=normalized_timeframe,
                    url=url,
                    output_path=output_path,
                    diagnostic_path=diagnostic_path,
                    page_text_path=page_text_path,
                    attempt=attempt,
                    snapshot=snapshot,
                )
                report_path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
                return output_path
            except Exception as exc:  # diagnostics are intentionally preserved
                last_error = exc
                report = OfficialWebCaptureReport(
                    symbol=symbol,
                    timeframe=normalized_timeframe,
                    url=url,
                    attempts=attempt,
                    mobile_layout_verified=False,
                    selected_timeframe_verified=False,
                    selected_timeframe_reason="attempt_failed",
                    network_interval_verified=False,
                    live_price_reference=None,
                    visible_price=None,
                    price_deviation_percent=None,
                    latest_kline_open_time_ms=None,
                    snapshot_fresh=False,
                    ma_overlay_removed=None,
                    screenshot_path=None,
                    diagnostic_path=(
                        _relative_or_absolute(diagnostic_path, self.root)
                        if diagnostic_path.exists()
                        else None
                    ),
                    page_text_path=(
                        _relative_or_absolute(page_text_path, self.root)
                        if page_text_path.exists()
                        else None
                    ),
                    candle_pixel_ratio=None,
                    output_dimensions=None,
                    status="failed",
                    error=str(exc),
                )
                report_path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")

        message = str(last_error) if last_error else "unknown capture error"
        raise WebCaptureError(
            f"Official Binance mobile-web capture failed for {symbol} {normalized_timeframe} "
            f"after {max_attempts} attempts: {message}"
        )

    async def _fetch_live_snapshot(self, symbol: str, timeframe: str) -> LiveMarketSnapshot:
        base_url = str(self.web_cfg.get("market_data_base_url", "https://data-api.binance.vision")).rstrip("/")
        timeout = float(self.web_cfg.get("market_data_timeout_seconds", 20))
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
            ticker_response, kline_response = await _gather_http(
                client.get("/api/v3/ticker/24hr", params={"symbol": symbol}),
                client.get(
                    "/api/v3/klines",
                    params={"symbol": symbol, "interval": timeframe, "limit": 2},
                ),
            )
            ticker_response.raise_for_status()
            kline_response.raise_for_status()
            ticker = ticker_response.json()
            klines = kline_response.json()

        if not isinstance(klines, list) or not klines:
            raise WebCaptureError("Binance returned no current kline for freshness verification")
        latest = klines[-1]
        snapshot = LiveMarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            current_price=float(ticker["lastPrice"]),
            high_24h=float(ticker["highPrice"]),
            low_24h=float(ticker["lowPrice"]),
            base_volume_24h=float(ticker.get("volume", 0)),
            quote_volume_24h=float(ticker.get("quoteVolume", 0)),
            latest_kline_open_time_ms=int(latest[0]),
            fetched_at_ms=int(time.time() * 1000),
        )
        grace = int(self.web_cfg.get("freshness_grace_seconds", 300))
        if not snapshot_is_fresh(
            snapshot.latest_kline_open_time_ms,
            timeframe,
            snapshot.fetched_at_ms,
            grace,
        ):
            raise WebCaptureError("Binance market snapshot is stale for the requested timeframe")
        return snapshot

    async def _capture_attempt(
        self,
        *,
        symbol: str,
        timeframe: str,
        url: str,
        output_path: Path,
        diagnostic_path: Path,
        page_text_path: Path,
        attempt: int,
        snapshot: LiveMarketSnapshot,
    ) -> OfficialWebCaptureReport:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise WebCaptureError("Playwright is not installed") from exc

        viewport = {
            "width": int(self.web_cfg.get("viewport_width", 430)),
            "height": int(self.web_cfg.get("viewport_height", 932)),
        }
        if viewport["width"] > int(self.web_cfg.get("maximum_mobile_viewport_width", 540)):
            raise WebCaptureError("Configured viewport is not a mobile width")
        timeout_ms = int(float(self.web_cfg.get("navigation_timeout_seconds", 75)) * 1000)
        settle_ms = int(float(self.web_cfg.get("settle_seconds", 9)) * 1000)

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            context = await browser.new_context(
                viewport=viewport,
                screen=viewport,
                device_scale_factor=float(self.web_cfg.get("device_scale_factor", 2)),
                is_mobile=True,
                has_touch=True,
                color_scheme="dark",
                locale=str(self.web_cfg.get("locale", "en-US")),
                timezone_id=str(self.web_cfg.get("timezone", "Asia/Kolkata")),
                user_agent=str(
                    self.web_cfg.get(
                        "user_agent",
                        "Mozilla/5.0 (Linux; Android 14; Pixel 7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0.0.0 Mobile Safari/537.36",
                    )
                ),
            )
            page = await context.new_page()
            tracker = KlineIntervalTracker()
            page.on("request", lambda request: tracker.observe_url(request.url))

            def observe_websocket(websocket) -> None:
                tracker.observe_url(websocket.url)
                websocket.on("framesent", tracker.observe_payload)
                websocket.on("framereceived", tracker.observe_payload)

            page.on("websocket", observe_websocket)
            page.set_default_timeout(timeout_ms)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                await page.wait_for_timeout(2500)
                await self._dismiss_common_overlays(page)
                await self._cancel_destructive_dialog(page)
                await self._assert_mobile_layout(page, viewport)
                await self._assert_symbol_present(page, symbol)

                verified, reason, marker = await self._ensure_timeframe(page, timeframe, tracker)
                if not verified:
                    raise WebCaptureError(f"Requested timeframe could not be verified: {reason}")

                network_timeout = int(
                    float(self.web_cfg.get("network_timeframe_confirmation_seconds", 7)) * 1000
                )
                network_verified = tracker.seen_after(timeframe, marker)
                if not network_verified:
                    network_verified = await tracker.wait_for_after(page, timeframe, marker, network_timeout)
                if not network_verified:
                    # A page may request the selected interval before the DOM row finishes rendering.
                    network_verified = tracker.latest_interval() == timeframe
                if bool(self.web_cfg.get("require_network_timeframe_confirmation", True)) and not network_verified:
                    raise WebCaptureError(
                        f"Official Binance chart did not request current {timeframe} kline data"
                    )

                await page.wait_for_timeout(settle_ms)
                await self._dismiss_common_overlays(page)
                await self._cancel_destructive_dialog(page)
                await self._assert_page_clean(page)
                await self._wait_for_chart_activity(page)

                selected_again, selected_reason = await self._verify_selected_timeframe(page, timeframe)
                if not selected_again:
                    raise WebCaptureError(
                        f"Timeframe row does not visibly select {timeframe}: {selected_reason}"
                    )

                await self._position_mobile_chart_card(page, symbol)
                await page.wait_for_timeout(650)
                await self._dismiss_common_overlays(page)
                await self._cancel_destructive_dialog(page)
                await self._assert_page_clean(page)
                await self._wait_for_chart_activity(page)

                skip_indicator_cleanup = bool(
                    self.web_cfg.get("skip_indicator_cleanup_for_proof", False)
                )
                if skip_indicator_cleanup:
                    # Manual proof mode must never probe anonymous chart toolbar controls.
                    # Binance can map those controls to "clear all drawings", which opens a
                    # destructive confirmation dialog and blocks the screenshot. Keep the
                    # official chart untouched and record whether MA/EMA is still visible.
                    ma_removed = not await self._ma_overlay_visible(page)
                    await page.mouse.move(8, 8)
                    await page.wait_for_timeout(350)
                else:
                    ma_removed = await self._try_disable_moving_average_overlays(page)
                allow_overlay_for_proof = bool(
                    self.web_cfg.get("allow_ma_overlay_for_capture_proof", False)
                )
                if (
                    bool(self.web_cfg.get("require_ma_overlay_removed", True))
                    and not ma_removed
                    and not allow_overlay_for_proof
                ):
                    raise WebCaptureError(
                        "Moving-average overlay is still visible; refusing to publish a cluttered chart"
                    )

                await self._clear_chart_hover(page)
                await self._dismiss_common_overlays(page)
                await self._assert_page_clean(page)

                visible_price = await self._find_visible_live_price(page, snapshot.current_price)
                deviation = price_deviation_percent(visible_price, snapshot.current_price)
                maximum_deviation = float(self.web_cfg.get("maximum_price_deviation_percent", 0.80))
                if deviation > maximum_deviation:
                    raise WebCaptureError(
                        f"Visible Binance price is not current enough: {deviation:.3f}% deviation"
                    )

                geometry = await self._mobile_chart_geometry(page, viewport, symbol)
                jitter_min = int(self.web_cfg.get("crop_vertical_jitter_min_pixels", -14))
                jitter_max = int(self.web_cfg.get("crop_vertical_jitter_max_pixels", 18))
                if jitter_max < jitter_min:
                    jitter_min, jitter_max = jitter_max, jitter_min
                vertical_jitter = random.SystemRandom().randint(jitter_min, jitter_max)

                clip = tall_mobile_clip(
                    viewport_width=viewport["width"],
                    viewport_height=viewport["height"],
                    pair_bottom_y=geometry["pair_bottom_y"],
                    timeframe_y=geometry["timeframe_y"],
                    chart_bottom=geometry["chart_bottom"],
                    price_top_y=geometry.get("price_top_y"),
                    aspect_ratio=float(self.web_cfg.get("crop_aspect_ratio", 0.8)),
                    top_padding=float(self.web_cfg.get("crop_pair_gap_pixels", 4)),
                    minimum_chart_pixels=float(
                        self.web_cfg.get("minimum_visible_chart_pixels", 250)
                    ),
                    base_down_shift_pixels=float(
                        self.web_cfg.get("crop_base_down_shift_pixels", 32)
                    ),
                    vertical_jitter_pixels=float(vertical_jitter),
                    timeframe_safe_margin_pixels=float(
                        self.web_cfg.get("crop_timeframe_safe_margin_pixels", 85)
                    ),
                    price_safe_padding_pixels=float(
                        self.web_cfg.get("crop_price_safe_padding_pixels", 10)
                    ),
                )
                raw_viewport = await page.screenshot(full_page=False, type="png", scale="device")
                self._save_viewport_crop(raw_viewport, clip, viewport, output_path)
                inspection = self._validate_image(output_path)
                with Image.open(output_path) as image:
                    dimensions = f"{image.width}x{image.height}"

                now_ms = int(time.time() * 1000)
                fresh = snapshot_is_fresh(
                    snapshot.latest_kline_open_time_ms,
                    timeframe,
                    now_ms,
                    int(self.web_cfg.get("freshness_grace_seconds", 300)),
                )
                if not fresh:
                    output_path.unlink(missing_ok=True)
                    raise WebCaptureError("Snapshot became stale before screenshot completion")

                return OfficialWebCaptureReport(
                    symbol=symbol,
                    timeframe=timeframe,
                    url=url,
                    attempts=attempt,
                    mobile_layout_verified=True,
                    selected_timeframe_verified=True,
                    selected_timeframe_reason=f"{reason};post_capture:{selected_reason}",
                    network_interval_verified=network_verified,
                    live_price_reference=snapshot.current_price,
                    visible_price=visible_price,
                    price_deviation_percent=deviation,
                    latest_kline_open_time_ms=snapshot.latest_kline_open_time_ms,
                    snapshot_fresh=fresh,
                    ma_overlay_removed=ma_removed,
                    screenshot_path=_relative_or_absolute(output_path, self.root),
                    diagnostic_path=None,
                    page_text_path=None,
                    candle_pixel_ratio=inspection.candle_pixel_ratio,
                    output_dimensions=dimensions,
                    status="accepted",
                )
            except Exception:
                try:
                    text = await page.locator("body").inner_text(timeout=1500)
                    page_text_path.write_text(text, encoding="utf-8")
                except Exception:
                    pass
                try:
                    await page.screenshot(
                        path=str(diagnostic_path), full_page=False, type="png", scale="css"
                    )
                except Exception:
                    pass
                output_path.unlink(missing_ok=True)
                raise
            finally:
                await context.close()
                await browser.close()

    async def _dismiss_common_overlays(self, page) -> None:
        patterns = [
            re.compile(r"^(Accept|Accept all|Agree|Got it|I understand)$", re.I),
            re.compile(r"^(Continue in browser|Stay on web|Not now|Later|Close)$", re.I),
        ]
        for pattern in patterns:
            for frame in page.frames:
                try:
                    locator = frame.get_by_role("button", name=pattern).first
                    if await locator.is_visible(timeout=500):
                        await locator.click(timeout=1000)
                        await page.wait_for_timeout(200)
                except Exception:
                    continue

    async def _page_visual_inspection(self, page) -> VisualCaptureInspection:
        raw = await page.screenshot(full_page=False, type="png", scale="css")
        with Image.open(io.BytesIO(raw)) as image:
            return inspect_capture_image(image)

    async def _visible_destructive_dialog_container(self, page):
        """Return only a real modal confirmation, not a chart menu or settings panel.

        Binance mobile web uses class names containing ``modal``/``dialog`` for several
        ordinary panels. Those broad selectors caused false positives. A destructive
        confirmation is accepted only when it has modal semantics, fixed positioning,
        destructive wording, and both cancel-like and confirm-like actions.
        """

        cancel_pattern = re.compile(
            r"^(Cancel|No|Keep|Keep drawings|Close|Back|Not now|Never mind)$", re.I
        )
        confirm_pattern = re.compile(
            r"^(Confirm|Delete|Clear|Clear all|Remove|Yes|OK)$", re.I
        )
        selector = '[role="dialog"],[aria-modal="true"]'
        for frame in page.frames:
            try:
                containers = frame.locator(selector)
                count = min(await containers.count(), 20)
            except Exception:
                continue
            for index in range(count):
                container = containers.nth(index)
                try:
                    if not await container.is_visible(timeout=0):
                        continue
                    box = await container.bounding_box()
                    if not box or box["width"] < 160 or box["height"] < 90:
                        continue
                    style = await container.evaluate(
                        """el => {
                          const s = getComputedStyle(el);
                          return {position:s.position, zIndex:s.zIndex, opacity:s.opacity};
                        }"""
                    )
                    if str(style.get("position", "")).lower() not in {"fixed", "absolute"}:
                        continue
                    text = (await container.inner_text(timeout=250)).strip()
                    if not contains_destructive_modal(text):
                        continue

                    buttons = container.locator('button,[role="button"],a')
                    button_count = min(await buttons.count(), 20)
                    has_cancel = False
                    has_confirm = False
                    for button_index in range(button_count):
                        button = buttons.nth(button_index)
                        try:
                            if not await button.is_visible(timeout=0):
                                continue
                            meta = " ".join(
                                filter(
                                    None,
                                    [
                                        (await button.inner_text(timeout=80)).strip(),
                                        await button.get_attribute("aria-label"),
                                        await button.get_attribute("title"),
                                    ],
                                )
                            ).strip()
                            has_cancel = has_cancel or bool(cancel_pattern.search(meta))
                            has_confirm = has_confirm or bool(confirm_pattern.search(meta))
                        except Exception:
                            continue
                    if not (has_cancel and has_confirm):
                        continue
                    return frame, container
                except Exception:
                    continue
        return None

    async def _visible_destructive_dialog_text(self, page) -> bool:
        """Detect the exact Binance delete-all-drawings warning across page frames."""

        warning = re.compile(
            r"All drawings will be permanently deleted|"
            r"confirm that you want to delete all drawings",
            re.I,
        )
        for frame in page.frames:
            try:
                matches = frame.get_by_text(warning)
                count = min(await matches.count(), 12)
            except Exception:
                continue
            for index in range(count):
                try:
                    if await matches.nth(index).is_visible(timeout=0):
                        return True
                except Exception:
                    continue
        return False

    async def _destructive_dialog_visible(self, page) -> bool:
        # Binance's real warning is sometimes rendered without role=dialog. Trust either
        # a strict modal container or the exact visible warning copy, never chart pixels.
        return (
            await self._visible_destructive_dialog_container(page) is not None
            or await self._visible_destructive_dialog_text(page)
        )

    async def _cancel_destructive_dialog(self, page) -> None:
        if not await self._destructive_dialog_visible(page):
            return

        cancel_pattern = re.compile(
            r"^(Cancel|No|Keep|Keep drawings|Close|Back|Not now|Never mind)$", re.I
        )
        for _ in range(4):
            # When the exact warning is visible, it is safe to look for a cancel-like
            # action anywhere in that same frame. Binance may render the buttons below
            # the current viewport and without a role=dialog ancestor.
            for frame in page.frames:
                try:
                    actions = frame.locator(
                        'button,[role="button"],a,[aria-label],[title]'
                    )
                    count = min(await actions.count(), 80)
                except Exception:
                    continue
                for index in range(count):
                    item = actions.nth(index)
                    try:
                        meta = " ".join(
                            filter(
                                None,
                                [
                                    (await item.inner_text(timeout=80)).strip(),
                                    await item.get_attribute("aria-label"),
                                    await item.get_attribute("title"),
                                ],
                            )
                        ).strip()
                        if not cancel_pattern.search(meta):
                            continue
                        await item.click(timeout=1200, force=True)
                        await page.wait_for_timeout(450)
                        if not await self._destructive_dialog_visible(page):
                            return
                    except Exception:
                        continue

            try:
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(450)
                if not await self._destructive_dialog_visible(page):
                    return
            except Exception:
                pass

        raise WebCaptureError("Binance clear-drawings confirmation could not be closed")

    async def _assert_mobile_layout(self, page, viewport: dict[str, int]) -> None:
        result = await page.evaluate(
            """() => ({
              innerWidth,
              innerHeight,
              coarse: matchMedia('(pointer: coarse)').matches,
              touchPoints: navigator.maxTouchPoints,
              mobileUA: /Android|Mobile/i.test(navigator.userAgent)
            })"""
        )
        maximum = int(self.web_cfg.get("maximum_mobile_viewport_width", 540))
        if int(result["innerWidth"]) > maximum or viewport["width"] > maximum:
            raise WebCaptureError(f"Binance page rendered a desktop-width layout: {result['innerWidth']}")
        if not bool(result["mobileUA"]):
            raise WebCaptureError("Browser did not use the configured Android mobile user agent")

    async def _assert_symbol_present(self, page, symbol: str) -> None:
        quote = str(self.settings["market"].get("quote_asset", "USDT")).upper()
        base = symbol.upper().removesuffix(quote)
        expected = (symbol.upper(), f"{base}/{quote}", f"{base}{quote}")
        try:
            body_text = (await page.locator("body").inner_text(timeout=2500)).upper().replace(" ", "")
        except Exception as exc:
            raise WebCaptureError(f"Could not verify symbol on Binance page: {exc}") from exc
        compact = body_text.replace("/", "")
        if not any(item.replace("/", "") in compact for item in expected):
            raise WebCaptureError(f"Expected symbol {symbol} was not visible on the Binance page")

    async def _ensure_timeframe(
        self, page, timeframe: str, tracker: KlineIntervalTracker
    ) -> tuple[bool, str, int]:
        marker = tracker.mark()
        selected, reason = await self._verify_selected_timeframe(page, timeframe)
        if selected and tracker.latest_interval() == timeframe:
            return True, f"already_selected:{reason}", marker

        element = await self._safe_timeframe_element(page, timeframe)
        marker = tracker.mark()
        click_mode = await self._click_exact_timeframe_control(page, element, timeframe)
        await page.wait_for_timeout(700)
        if await self._destructive_dialog_visible(page):
            await self._cancel_destructive_dialog(page)
        selected, reason = await self._verify_selected_timeframe(page, timeframe)
        return selected, f"clicked_exact_mobile_row:{click_mode}:{reason}", marker

    async def _click_exact_timeframe_control(self, page, element, timeframe: str) -> str:
        """Click only the previously validated exact timeframe control.

        Binance occasionally inserts a temporary transparent/sticky element after
        ``scroll_into_view_if_needed``. A normal Playwright click then reports that the
        timeframe is covered even though the exact safe control was already located.
        We first dismiss known overlays and retry hit-testing. If the center is still
        covered, we use Playwright's force click on that exact validated DOM element —
        never a coordinate click and never an anonymous toolbar control.
        """

        aliases = [item.lower() for item in TIMEFRAME_ALIASES[timeframe]]
        await element.scroll_into_view_if_needed()

        async def center_is_clickable() -> bool:
            try:
                return bool(
                    await element.evaluate(
                        """el => {
                          const r = el.getBoundingClientRect();
                          const x = r.left + r.width / 2;
                          const y = r.top + r.height / 2;
                          const hit = document.elementFromPoint(x, y);
                          return Boolean(hit && (hit === el || el.contains(hit) || hit.contains(el)));
                        }"""
                    )
                )
            except Exception:
                return False

        if await center_is_clickable():
            await element.click(timeout=2500, force=False)
            return "normal"

        await self._dismiss_common_overlays(page)
        if await self._destructive_dialog_visible(page):
            await self._cancel_destructive_dialog(page)
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        await page.wait_for_timeout(180)

        if await center_is_clickable():
            await element.click(timeout=2500, force=False)
            return "normal_after_overlay_recovery"

        safe_exact = await element.evaluate(
            r"""
            (el, payload) => {
              const normalize = value => String(value || '').trim().replace(/\s+/g, '').toLowerCase();
              if (!el || !el.isConnected || !payload.aliases.includes(normalize(el.textContent))) return false;
              const s = getComputedStyle(el);
              const r = el.getBoundingClientRect();
              if (s.display === 'none' || s.visibility === 'hidden' || Number(s.opacity || 1) <= .35 ||
                  r.width < 18 || r.width > 85 || r.height < 16 || r.height > 58) return false;
              let node = el;
              for (let depth = 0; depth < 5 && node; depth++, node = node.parentElement) {
                const metadata = [node.getAttribute('aria-label'), node.getAttribute('title'),
                  node.getAttribute('data-testid'), String(node.className || '')].join(' ').toLowerCase();
                if (payload.forbidden.some(word => metadata.includes(word))) return false;
              }
              return true;
            }
            """,
            {"aliases": aliases, "forbidden": list(FORBIDDEN_CONTROL_WORDS)},
        )
        if not safe_exact:
            raise WebCaptureError("Exact timeframe control became unsafe before click")

        # Playwright force-click still dispatches through screen coordinates, so the
        # covering element can receive the event. Invoke click on the exact validated
        # DOM control instead; this cannot hit a neighboring toolbar button.
        await element.evaluate("el => el.click()")
        return "dom_exact_control_after_cover"

    async def _safe_timeframe_element(self, page, timeframe: str):
        aliases = [item.lower() for item in TIMEFRAME_ALIASES[timeframe]]
        handle = await page.evaluate_handle(
            r"""
            ({aliases, forbidden}) => {
              const normalize = value => String(value || '').trim().replace(/\s+/g, '').toLowerCase();
              const isVisible = el => {
                const s = getComputedStyle(el);
                const r = el.getBoundingClientRect();
                return s.display !== 'none' && s.visibility !== 'hidden' && Number(s.opacity || 1) > .35 &&
                  s.pointerEvents !== 'none' && r.width >= 18 && r.width <= 85 && r.height >= 16 && r.height <= 58;
              };
              const bad = el => {
                let node = el;
                for (let depth = 0; depth < 5 && node; depth++, node = node.parentElement) {
                  const metadata = [node.getAttribute('aria-label'), node.getAttribute('title'),
                    node.getAttribute('data-testid'), String(node.className || '')].join(' ').toLowerCase();
                  if (forbidden.some(word => metadata.includes(word))) return true;
                }
                return false;
              };
              const exactNodes = Array.from(document.querySelectorAll('button,[role="button"],[role="tab"],a,span,div'))
                .filter(el => aliases.includes(normalize(el.textContent)) && isVisible(el) && !bad(el));
              let best = null;
              let bestScore = -Infinity;
              for (const leaf of exactNodes) {
                const actionable = leaf.matches('button,[role="button"],[role="tab"],a')
                  ? leaf : leaf.closest('button,[role="button"],[role="tab"],a') || leaf;
                const text = normalize(actionable.textContent);
                if (!aliases.includes(text)) continue;
                const r = actionable.getBoundingClientRect();
                if (r.x < 4 || r.right > innerWidth - 4 || r.y < innerHeight * .12 || r.y > innerHeight * .58) continue;
                let row = actionable.parentElement;
                let rowCount = 0;
                let containsMore = false;
                for (let depth = 0; depth < 5 && row; depth++, row = row.parentElement) {
                  const tokens = Array.from(row.querySelectorAll('button,[role="button"],[role="tab"],a,span,div'))
                    .map(item => normalize(item.textContent));
                  const unique = new Set(tokens.filter(item => ['15m','1h','4h','1d'].includes(item)));
                  const count = unique.size;
                  const more = tokens.includes('more');
                  if (count > rowCount) { rowCount = count; containsMore = more; }
                }
                if (rowCount < 3) continue;
                const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
                if (!hit || !(hit === actionable || actionable.contains(hit) || hit.contains(actionable))) continue;
                const tagBonus = actionable.matches('button,[role="button"],[role="tab"],a') ? 80 : 0;
                const rowBonus = rowCount * 140 + (containsMore ? 25 : 0);
                const yScore = -Math.abs((r.y + r.height / 2) - innerHeight * .31);
                const score = tagBonus + rowBonus + yScore;
                if (score > bestScore) { best = actionable; bestScore = score; }
              }
              return best;
            }
            """,
            {"aliases": aliases, "forbidden": list(FORBIDDEN_CONTROL_WORDS)},
        )
        element = handle.as_element()
        if element is None:
            await handle.dispose()
            raise WebCaptureError(f"Could not locate exact mobile timeframe control for {timeframe}")
        return element

    async def _verify_selected_timeframe(self, page, timeframe: str) -> tuple[bool, str]:
        aliases = [item.lower() for item in TIMEFRAME_ALIASES[timeframe]]
        result = await page.evaluate(
            r"""
            ({aliases, forbidden}) => {
              const norm = value => String(value || '').trim().replace(/\s+/g, '').toLowerCase();
              const rgbBrightness = value => {
                const nums = String(value || '').match(/[\d.]+/g) || [];
                if (nums.length < 3) return 0;
                return Number(nums[0]) * .299 + Number(nums[1]) * .587 + Number(nums[2]) * .114;
              };
              const visible = el => {
                const s = getComputedStyle(el); const r = el.getBoundingClientRect();
                return s.display !== 'none' && s.visibility !== 'hidden' && Number(s.opacity || 1) > .35 &&
                  r.width >= 12 && r.width <= 95 && r.height >= 12 && r.height <= 60 &&
                  r.y >= innerHeight * .12 && r.y <= innerHeight * .58;
              };
              const candidates = Array.from(document.querySelectorAll('button,[role="button"],[role="tab"],a,span,div'))
                .filter(el => aliases.includes(norm(el.textContent)) && visible(el));
              for (const leaf of candidates) {
                const target = leaf.matches('button,[role="button"],[role="tab"],a')
                  ? leaf : leaf.closest('button,[role="button"],[role="tab"],a') || leaf;
                const metadata = [target.getAttribute('aria-label'), target.getAttribute('title'),
                  target.getAttribute('data-testid'), String(target.className || '')].join(' ').toLowerCase();
                if (forbidden.some(word => metadata.includes(word))) continue;
                let row = target.parentElement;
                let siblings = [];
                for (let depth = 0; depth < 5 && row; depth++, row = row.parentElement) {
                  const found = Array.from(row.querySelectorAll('button,[role="button"],[role="tab"],a,span,div'))
                    .filter(el => ['15m','1h','4h','1d'].includes(norm(el.textContent)) && visible(el));
                  const unique = [];
                  const seen = new Set();
                  for (const el of found) {
                    const key = norm(el.textContent); if (!seen.has(key)) { seen.add(key); unique.push(el); }
                  }
                  if (unique.length >= 3) { siblings = unique; break; }
                }
                if (siblings.length < 3) continue;
                const style = getComputedStyle(target);
                const explicit = target.getAttribute('aria-selected') === 'true' ||
                  target.getAttribute('aria-pressed') === 'true' || target.getAttribute('data-state') === 'active' ||
                  target.getAttribute('data-active') === 'true' || /(^|\s)(active|selected|current)(\s|$)/i.test(String(target.className || ''));
                const brightness = rgbBrightness(style.color);
                const others = siblings.filter(item => !aliases.includes(norm(item.textContent))).map(item => {
                  const s = getComputedStyle(item.matches('button,[role="button"],[role="tab"],a') ? item : item.closest('button,[role="button"],[role="tab"],a') || item);
                  return {brightness: rgbBrightness(s.color), weight: Number.parseInt(s.fontWeight, 10) || 400};
                });
                const otherBrightness = others.length ? others.map(item => item.brightness).sort((a,b)=>a-b)[Math.floor(others.length/2)] : 0;
                const otherWeight = others.length ? Math.max(...others.map(item => item.weight)) : 400;
                const weight = Number.parseInt(style.fontWeight, 10) || 400;
                const visual = brightness >= otherBrightness + 18 || weight >= otherWeight + 100;
                return {ok: explicit || visual, explicit, visual, brightness, otherBrightness, weight, otherWeight};
              }
              return {ok:false, reason:'requested_timeframe_not_in_mobile_row'};
            }
            """,
            {"aliases": aliases, "forbidden": list(FORBIDDEN_CONTROL_WORDS)},
        )
        if bool(result.get("ok")):
            if result.get("explicit"):
                return True, "explicit_selected_state"
            return True, "visual_selected_state"
        return False, str(result.get("reason", "not_selected"))

    async def _find_visible_live_price(self, page, reference: float) -> float:
        candidates = await page.evaluate(
            r"""
            () => {
              const values = [];
              for (const el of document.querySelectorAll('span,div,p,strong')) {
                const s = getComputedStyle(el); const r = el.getBoundingClientRect();
                if (s.display === 'none' || s.visibility === 'hidden' || Number(s.opacity || 1) < .35) continue;
                if (r.width < 18 || r.width > innerWidth * .76 || r.height < 12 || r.height > 100) continue;
                if (r.y < 10 || r.y > innerHeight * .48 || r.x > innerWidth * .88) continue;
                const text = String(el.textContent || '').trim();
                if (!text || text.length > 32) continue;
                const fontSize = Number.parseFloat(s.fontSize) || 0;
                values.push({text, x:r.x, y:r.y, width:r.width, height:r.height, fontSize});
              }
              return values;
            }
            """
        )
        best_value: float | None = None
        best_score = float("inf")
        for item in candidates:
            for value in parse_numeric_text(str(item.get("text", ""))):
                deviation = price_deviation_percent(value, reference)
                font_size = float(item.get("fontSize", 0))
                y = float(item.get("y", 0))
                score = deviation * 1000 - min(font_size, 80) * 2 + y * 0.02
                if score < best_score:
                    best_score = score
                    best_value = value
        if best_value is None:
            raise WebCaptureError("Could not find the current price in the official mobile Binance header")
        return best_value

    async def _assert_page_clean(self, page) -> None:
        # Never accept a proof image containing the delete-all-drawings warning. Attempt
        # a safe Cancel/Escape recovery, then verify the warning is genuinely gone.
        if await self._destructive_dialog_visible(page):
            await self._cancel_destructive_dialog(page)
        if await self._destructive_dialog_visible(page):
            raise WebCaptureError("Binance clear-drawings confirmation is still visible")

    async def _wait_for_chart_activity(self, page) -> None:
        attempts = int(self.web_cfg.get("chart_activity_checks", 8))
        delay_ms = int(float(self.web_cfg.get("chart_activity_check_seconds", 1.2)) * 1000)
        last_ratio = 0.0
        for _ in range(attempts):
            inspection = await self._page_visual_inspection(page)
            last_ratio = inspection.candle_pixel_ratio
            # Do not use the pixel-only destructive-modal heuristic here. It confuses
            # Binance chart panels with confirmation dialogs. Visible DOM dialogs are
            # handled separately by _cancel_destructive_dialog().
            if not inspection.chart_blank:
                return
            await page.wait_for_timeout(delay_ms)
        raise WebCaptureError(f"Official Binance chart remained blank (pixel ratio {last_ratio:.5f})")

    async def _find_ma_legend_locator(self, page):
        """Return the smallest visible MA/EMA legend across page frames."""

        pattern = re.compile(r"(?:^|\s)(?:MA|EMA)\s*\(", re.I)
        candidates = []
        for frame in page.frames:
            try:
                locator = frame.locator("span,div,p,strong").filter(has_text=pattern)
                count = min(await locator.count(), 30)
            except Exception:
                continue
            for index in range(count):
                item = locator.nth(index)
                try:
                    if not await item.is_visible(timeout=0):
                        continue
                    value = (await item.inner_text(timeout=100)).strip()
                    if len(value) > 220 or not pattern.search(value):
                        continue
                    box = await item.bounding_box()
                    if not box:
                        continue
                    width = float(box["width"])
                    height = float(box["height"])
                    if width <= 16 or height <= 10:
                        continue
                    if float(box["y"]) < 0 or float(box["y"]) > float(
                        self.web_cfg.get("viewport_height", 932)
                    ) * .84:
                        continue
                    area = width * height
                    score = len(value) * 10 + area * .01
                    candidates.append((score, frame, item, box))
                except Exception:
                    continue
        if not candidates:
            return None
        candidates.sort(key=lambda entry: entry[0])
        _, frame, item, box = candidates[0]
        return frame, item, box

    async def _ma_legend_geometry(self, page) -> dict[str, float] | None:
        found = await self._find_ma_legend_locator(page)
        if not found:
            return None
        _, _, box = found
        return {
            "x": float(box["x"]),
            "y": float(box["y"]),
            "width": float(box["width"]),
            "height": float(box["height"]),
        }

    async def _visible_indicator_tooltip(self, page) -> str | None:
        pattern = re.compile(r"^(remove|delete|close|hide|show)( indicator)?$", re.I)
        for frame in page.frames:
            try:
                locator = frame.locator(
                    '[role="tooltip"],[class*="tooltip"],[data-popper-placement],div,span'
                ).filter(has_text=pattern)
                count = min(await locator.count(), 20)
            except Exception:
                continue
            for index in range(count):
                item = locator.nth(index)
                try:
                    if not await item.is_visible(timeout=80):
                        continue
                    value = (await item.inner_text(timeout=120)).strip().lower()
                    match = pattern.fullmatch(value)
                    if not match:
                        continue
                    command = match.group(1).lower()
                    if command in {"remove", "delete", "close"}:
                        return "remove"
                    return command
                except Exception:
                    continue
        return None

    async def _ma_overlay_visible(self, page) -> bool:
        return await self._find_ma_legend_locator(page) is not None

    async def _click_indicator_control(self, page, x: float, y: float) -> None:
        await page.mouse.move(x, y)
        await page.wait_for_timeout(140)
        await page.mouse.down()
        await page.wait_for_timeout(90)
        await page.mouse.up()
        await page.wait_for_timeout(650)
        if await self._ma_overlay_visible(page):
            try:
                await page.touchscreen.tap(x, y)
                await page.wait_for_timeout(650)
            except Exception:
                pass

    async def _click_frame_indicator_control(self, page, frame, legend_box: dict[str, float]) -> bool:
        """Click a semantic indicator control in the same frame as the MA legend."""

        selectors = [
            '[aria-label*="remove indicator" i]',
            '[title*="remove indicator" i]',
            '[aria-label*="delete indicator" i]',
            '[title*="delete indicator" i]',
            '[aria-label*="close indicator" i]',
            '[title*="close indicator" i]',
            '[aria-label*="hide indicator" i]',
            '[title*="hide indicator" i]',
        ]
        for selector in selectors:
            try:
                locator = frame.locator(selector)
                count = min(await locator.count(), 8)
            except Exception:
                continue
            for index in range(count):
                item = locator.nth(index)
                try:
                    if not await item.is_visible(timeout=0):
                        continue
                    box = await item.bounding_box()
                    if not box:
                        continue
                    legend_y = float(legend_box["y"]) + float(legend_box["height"]) / 2.0
                    center_y = float(box["y"]) + float(box["height"]) / 2.0
                    if abs(center_y - legend_y) > 70:
                        continue
                    try:
                        await item.click(force=True, timeout=700)
                    except Exception:
                        await self._click_indicator_control(
                            page,
                            float(box["x"]) + float(box["width"]) / 2.0,
                            float(box["y"]) + float(box["height"]) / 2.0,
                        )
                    await page.wait_for_timeout(550)
                    await self._cancel_destructive_dialog(page)
                    await self._assert_page_clean(page)
                    if not await self._ma_overlay_visible(page):
                        return True
                except Exception:
                    continue

        # Generic right-side controls sometimes have no useful accessible name.
        try:
            controls = frame.locator('button,[role="button"],[aria-label],[title]')
            count = min(await controls.count(), 80)
        except Exception:
            return False
        visual = []
        legend_y = float(legend_box["y"]) + float(legend_box["height"]) / 2.0
        legend_left = float(legend_box["x"])
        for index in range(count):
            item = controls.nth(index)
            try:
                if not await item.is_visible(timeout=0):
                    continue
                box = await item.bounding_box()
                if not box:
                    continue
                width = float(box["width"])
                height = float(box["height"])
                center_x = float(box["x"]) + width / 2.0
                center_y = float(box["y"]) + height / 2.0
                if abs(center_y - legend_y) > 48:
                    continue
                if center_x < legend_left + 70 or width < 7 or height < 7 or width > 70 or height > 70:
                    continue
                visual.append((center_x, item, box))
            except Exception:
                continue
        visual.sort(key=lambda entry: entry[0], reverse=True)
        for _, item, box in visual[:5]:
            try:
                await item.click(force=True, timeout=650)
            except Exception:
                try:
                    await self._click_indicator_control(
                        page,
                        float(box["x"]) + float(box["width"]) / 2.0,
                        float(box["y"]) + float(box["height"]) / 2.0,
                    )
                except Exception:
                    continue
            await page.wait_for_timeout(500)
            if not await self._ma_overlay_visible(page):
                return True
        return False

    async def _try_disable_moving_average_overlays(self, page) -> bool:
        """Remove or hide Binance MA/EMA overlays, including controls inside iframes."""

        found = await self._find_ma_legend_locator(page)
        if found is None:
            await page.mouse.move(8, 8)
            return True

        frame, legend_locator, legend = found
        try:
            await legend_locator.hover(force=True, timeout=800)
        except Exception:
            center_x = float(legend["x"]) + min(float(legend["width"]) * .55, 170.0)
            center_y = float(legend["y"]) + float(legend["height"]) / 2.0
            await page.mouse.move(center_x, center_y)
        await page.wait_for_timeout(350)

        if await self._click_frame_indicator_control(page, frame, legend):
            await page.mouse.move(8, 8)
            await page.wait_for_timeout(350)
            return True

        viewport_width = float(self.web_cfg.get("viewport_width", 430))
        center_y = float(legend["y"]) + float(legend["height"]) / 2.0
        left = max(12.0, float(legend["x"]) + 70.0)
        right = min(viewport_width - 8.0, float(legend["x"]) + float(legend["width"]) + 140.0)

        remove_point: tuple[float, float] | None = None
        hide_point: tuple[float, float] | None = None
        x = right
        while x >= left:
            for y_offset in (-14.0, -9.0, -4.0, 0.0, 4.0, 9.0, 14.0):
                y = center_y + y_offset
                await page.mouse.move(x, y)
                await page.wait_for_timeout(70)
                tooltip = await self._visible_indicator_tooltip(page)
                if tooltip == "remove":
                    remove_point = (x, y)
                    break
                if tooltip == "hide" and hide_point is None:
                    hide_point = (x, y)
            if remove_point:
                break
            x -= 6.0

        for point in (remove_point, hide_point):
            if point is None:
                continue
            await self._click_indicator_control(page, *point)
            await self._cancel_destructive_dialog(page)
            await self._assert_page_clean(page)
            if not await self._ma_overlay_visible(page):
                await page.mouse.move(8, 8)
                await page.wait_for_timeout(350)
                return True
            if point == hide_point:
                await page.mouse.move(*point)
                await page.wait_for_timeout(220)
                hidden = await self._visible_indicator_tooltip(page) == "show"
                await page.mouse.move(8, 8)
                await page.wait_for_timeout(350)
                if hidden:
                    return True

        await page.mouse.move(8, 8)
        await page.wait_for_timeout(350)
        return not await self._ma_overlay_visible(page)

    async def _position_mobile_chart_card(self, page, symbol: str) -> None:
        """Place the pair-name bottom just above the viewport before final capture."""

        quote = str(self.settings["market"].get("quote_asset", "USDT")).upper()
        base = symbol.upper().removesuffix(quote)
        aliases = [symbol.upper(), f"{base}/{quote}"]
        gap = float(self.web_cfg.get("crop_pair_gap_pixels", 4))
        try:
            await page.evaluate(
                r"""({aliases, gap}) => {
                  const norm = value => String(value || '').trim().replace(/\s+/g, '').toUpperCase();
                  const visible = el => {
                    const s = getComputedStyle(el); const r = el.getBoundingClientRect();
                    return s.display !== 'none' && s.visibility !== 'hidden' && Number(s.opacity || 1) > .35 &&
                      r.width >= 50 && r.height >= 20;
                  };
                  let best = null;
                  for (const el of document.querySelectorAll('h1,h2,h3,strong,span,div')) {
                    if (!visible(el)) continue;
                    const value = norm(el.textContent);
                    if (!aliases.some(alias => value === norm(alias))) continue;
                    const r = el.getBoundingClientRect();
                    const fontSize = Number.parseFloat(getComputedStyle(el).fontSize) || 0;
                    const score = fontSize * 20 - r.top - Math.abs(r.left - innerWidth * .08);
                    if (!best || score > best.score) {
                      best = {score, bottom:r.bottom + scrollY};
                    }
                  }
                  if (best) {
                    window.scrollTo(0, Math.max(0, best.bottom + gap));
                    return true;
                  }

                  // Fallback: anchor the largest current-price text near the top.
                  for (const el of document.querySelectorAll('h1,h2,strong,span,div,p')) {
                    if (!visible(el)) continue;
                    const value = String(el.textContent || '').trim();
                    if (!/(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?/.test(value) || value.length > 24) continue;
                    const r = el.getBoundingClientRect();
                    const fontSize = Number.parseFloat(getComputedStyle(el).fontSize) || 0;
                    if (fontSize < 28 || r.left > innerWidth * .45) continue;
                    window.scrollTo(0, Math.max(0, r.top + scrollY - 10));
                    return true;
                  }
                  return false;
                }""",
                {"aliases": aliases, "gap": gap},
            )
            await page.wait_for_timeout(600)
        except Exception:
            return

    async def _clear_chart_hover(self, page) -> None:
        """Clear chart hover state without clicking any Binance toolbar control."""

        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        try:
            await page.evaluate(
                """() => {
                  try { document.activeElement && document.activeElement.blur(); } catch (e) {}
                  for (const el of document.querySelectorAll('canvas')) {
                    try { el.dispatchEvent(new MouseEvent('mouseleave', {bubbles:true})); } catch (e) {}
                    try { el.dispatchEvent(new PointerEvent('pointerleave', {bubbles:true})); } catch (e) {}
                  }
                }"""
            )
        except Exception:
            pass
        # Movement is safe; clicking a guessed top-right coordinate previously opened
        # Binance's "delete all drawings" confirmation. Never click here.
        for x, y in ((6, 6), (210, 8), (12, 110)):
            try:
                await page.mouse.move(x, y)
                await page.wait_for_timeout(160)
            except Exception:
                continue
        await self._cancel_destructive_dialog(page)

    async def _mobile_chart_geometry(
        self, page, viewport: dict[str, int], symbol: str | None = None
    ) -> dict[str, float]:
        quote = str(self.settings["market"].get("quote_asset", "USDT")).upper()
        base = symbol.upper().removesuffix(quote) if symbol else ""
        aliases = [symbol.upper(), f"{base}/{quote}"] if symbol else []
        geometry = await page.evaluate(
            r"""aliases => {
              const norm = value => String(value || '').trim().replace(/\s+/g, '').toUpperCase();
              const tfNorm = value => String(value || '').trim().replace(/\s+/g, '').toLowerCase();
              const visible = el => {
                const s = getComputedStyle(el); const r = el.getBoundingClientRect();
                return s.display !== 'none' && s.visibility !== 'hidden' && Number(s.opacity || 1) > .35 && r.width > 8 && r.height > 8;
              };

              let price = null;
              let priceScore = -Infinity;
              for (const el of document.querySelectorAll('h1,h2,h3,strong,span,div,p')) {
                if (!visible(el)) continue;
                const value = String(el.textContent || '').trim();
                if (!/^(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$/.test(value)) continue;
                const r = el.getBoundingClientRect();
                if (r.left > innerWidth * .48 || r.top > innerHeight * .36 || r.bottom < -20) continue;
                const fontSize = Number.parseFloat(getComputedStyle(el).fontSize) || 0;
                if (fontSize < 24) continue;
                const score = fontSize * 30 - Math.abs(r.left-innerWidth*.08) - Math.max(0, r.top) * .5;
                if (score > priceScore) {
                  priceScore = score;
                  price = {top:r.top,bottom:r.bottom,fontSize};
                }
              }

              let pair = null;
              let pairScore = -Infinity;
              if (aliases.length) {
                for (const el of document.querySelectorAll('h1,h2,h3,strong,span,div')) {
                  if (!visible(el)) continue;
                  const value = norm(el.textContent);
                  if (!aliases.some(alias => value === norm(alias))) continue;
                  const r = el.getBoundingClientRect();
                  const fontSize = Number.parseFloat(getComputedStyle(el).fontSize) || 0;
                  const score = fontSize * 20 - Math.abs(r.left-innerWidth*.08) - Math.abs(r.bottom);
                  if (score > pairScore) { pairScore = score; pair = {bottom:r.bottom}; }
                }
              }

              const rows = [];
              for (const el of document.querySelectorAll('div,nav,section')) {
                if (!visible(el)) continue;
                const tokens = Array.from(el.querySelectorAll('button,[role="button"],[role="tab"],a,span,div'))
                  .map(item => tfNorm(item.textContent));
                const unique = new Set(tokens.filter(item => ['15m','1h','4h','1d'].includes(item)));
                if (unique.size >= 3) {
                  const r = el.getBoundingClientRect();
                  if (r.width >= innerWidth * .60 && r.height <= 100 && r.y > innerHeight * .08 && r.y < innerHeight * .72) {
                    rows.push({y:r.y,bottom:r.bottom,width:r.width});
                  }
                }
              }
              rows.sort((a,b)=>Math.abs(a.y-innerHeight*.34)-Math.abs(b.y-innerHeight*.34));
              const row = rows[0] || null;

              let chart = null;
              let bestArea = 0;
              for (const el of document.querySelectorAll('canvas,iframe,[data-testid*="chart"],[class*="chart"]')) {
                if (!visible(el)) continue;
                const r = el.getBoundingClientRect();
                if (r.width < innerWidth * .62 || r.height < 180 || r.y < innerHeight * .18 || r.y > innerHeight * .90) continue;
                const area = r.width*r.height;
                if (area > bestArea) { bestArea=area; chart={y:r.y,bottom:r.bottom,width:r.width,height:r.height}; }
              }
              return {price,pair,row,chart};
            }""",
            aliases,
        )
        row = geometry.get("row")
        chart = geometry.get("chart")
        pair = geometry.get("pair")
        price = geometry.get("price")
        if not row:
            raise WebCaptureError("Could not locate the official mobile timeframe row")
        timeframe_y = float(row["y"])
        chart_bottom = float(chart["bottom"]) if chart else min(float(viewport["height"]), timeframe_y + 650)
        pair_bottom_y = float(pair["bottom"]) if pair else -float(self.web_cfg.get("crop_pair_gap_pixels", 4))
        price_top_y = float(price["top"]) if price else 0.0
        return {
            "pair_bottom_y": pair_bottom_y,
            "price_top_y": price_top_y,
            "timeframe_y": timeframe_y,
            "chart_bottom": chart_bottom,
        }

    def _target_dimensions(self) -> tuple[int, int]:
        legacy = int(self.web_cfg.get("output_size_pixels", 1080))
        width = int(self.web_cfg.get("output_width_pixels", legacy))
        height = int(self.web_cfg.get("output_height_pixels", legacy))
        return width, height

    def _save_viewport_crop(
        self, raw_png: bytes, clip: dict[str, float], viewport: dict[str, int], path: Path
    ) -> None:
        target_width, target_height = self._target_dimensions()
        with Image.open(io.BytesIO(raw_png)) as image:
            rgb = image.convert("RGB")
            scale_x = rgb.width / max(1.0, float(viewport["width"]))
            scale_y = rgb.height / max(1.0, float(viewport["height"]))
            left = max(0, int(round(float(clip["x"]) * scale_x)))
            top = max(0, int(round(float(clip["y"]) * scale_y)))
            right = min(rgb.width, int(round((float(clip["x"]) + float(clip["width"])) * scale_x)))
            bottom = min(rgb.height, int(round((float(clip["y"]) + float(clip["height"])) * scale_y)))
            if right <= left or bottom <= top:
                raise WebCaptureError("Calculated mobile chart crop is empty")
            cropped = rgb.crop((left, top, right, bottom))
            cropped = cropped.resize((target_width, target_height), Image.Resampling.LANCZOS)
            cropped.save(path, format="PNG", optimize=True)

    def _normalize_output(self, path: Path) -> None:
        target_width, target_height = self._target_dimensions()
        target_ratio = target_width / target_height
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            source_ratio = rgb.width / max(1, rgb.height)
            if abs(source_ratio - target_ratio) > 0.002:
                if source_ratio > target_ratio:
                    wanted_width = int(round(rgb.height * target_ratio))
                    left = max(0, (rgb.width - wanted_width) // 2)
                    rgb = rgb.crop((left, 0, left + wanted_width, rgb.height))
                else:
                    wanted_height = int(round(rgb.width / target_ratio))
                    top = max(0, (rgb.height - wanted_height) // 2)
                    rgb = rgb.crop((0, top, rgb.width, top + wanted_height))
            if rgb.size != (target_width, target_height):
                rgb = rgb.resize((target_width, target_height), Image.Resampling.LANCZOS)
            rgb.save(path, format="PNG", optimize=True)

    def _validate_image(self, path: Path) -> VisualCaptureInspection:
        minimum = int(self.web_cfg.get("minimum_image_bytes", 50000))
        if not path.exists() or path.stat().st_size < minimum:
            raise WebCaptureError("Official Binance screenshot is missing or unexpectedly small")
        with Image.open(path) as image:
            width, height = image.size
            expected_width, expected_height = self._target_dimensions()
            if width != expected_width or height != expected_height:
                raise WebCaptureError(
                    "Official Binance mobile screenshot must be "
                    f"{expected_width}x{expected_height}, found {width}x{height}"
                )
            extrema = image.convert("L").getextrema()
            if extrema is None or extrema[1] - extrema[0] < 18:
                raise WebCaptureError("Official Binance screenshot appears blank")
            inspection = inspect_capture_image(image)
            # A screenshot cannot be reliably rejected by the old pixel-only modal
            # heuristic because normal Binance chart UI triggers it. The live page has
            # already been checked for an actual visible DOM dialog before capture.
            if inspection.chart_blank:
                raise WebCaptureError(
                    f"Official Binance chart appears blank (pixel ratio {inspection.candle_pixel_ratio:.5f})"
                )
            return inspection


async def _gather_http(*awaitables):
    import asyncio

    return await asyncio.gather(*awaitables)


def _relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path.resolve())
