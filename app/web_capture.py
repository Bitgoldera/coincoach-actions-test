from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image


class WebCaptureError(RuntimeError):
    pass


DESTRUCTIVE_MODAL_PATTERNS = (
    "all drawings will be permanently deleted",
    "delete all drawings",
)


@dataclass(frozen=True, slots=True)
class VisualCaptureInspection:
    destructive_modal: bool
    chart_blank: bool
    confirm_button_box: tuple[int, int, int, int] | None
    candle_pixel_ratio: float


def contains_destructive_modal(text: str) -> bool:
    normalized = " ".join(str(text).lower().split())
    return any(pattern in normalized for pattern in DESTRUCTIVE_MODAL_PATTERNS)


def symbol_parts(symbol: str, quote: str = "USDT") -> tuple[str, str]:
    value = symbol.upper().strip()
    quote = quote.upper().strip()
    if not value.endswith(quote) or len(value) <= len(quote):
        raise WebCaptureError(f"Unsupported symbol format: {symbol}")
    return value[: -len(quote)], quote


def build_binance_url(template: str, symbol: str, quote: str = "USDT") -> str:
    base, normalized_quote = symbol_parts(symbol, quote)
    return template.format(base=base, quote=normalized_quote, symbol=f"{base}{normalized_quote}")


def resolve_symbol_quote(symbol: str, configured_quotes: list[str] | tuple[str, ...]) -> str:
    value = str(symbol).upper().strip()
    candidates = sorted(
        {str(quote).upper().strip() for quote in configured_quotes if str(quote).strip()},
        key=len,
        reverse=True,
    )
    for quote in candidates:
        if value.endswith(quote) and len(value) > len(quote):
            return quote
    raise WebCaptureError(f"Unsupported symbol quote for capture: {symbol}")


def _longest_true_run(values: list[bool]) -> tuple[int, int] | None:
    best: tuple[int, int] | None = None
    start: int | None = None
    for index, value in enumerate(values + [False]):
        if value and start is None:
            start = index
        elif not value and start is not None:
            if best is None or index - start > best[1] - best[0]:
                best = (start, index)
            start = None
    return best


def _analysis_image(image: Image.Image, width: int = 430) -> tuple[Image.Image, float, float]:
    rgb = image.convert("RGB")
    if rgb.width <= width:
        return rgb, 1.0, 1.0
    height = max(1, round(rgb.height * width / rgb.width))
    resized = rgb.resize((width, height), Image.Resampling.BILINEAR)
    return resized, rgb.width / resized.width, rgb.height / resized.height


def _is_binance_yellow(red: int, green: int, blue: int) -> bool:
    return red >= 185 and green >= 125 and blue <= 105 and red >= green and green >= blue * 1.35


def _is_candle_red(red: int, green: int, blue: int) -> bool:
    return red >= 72 and red >= green * 1.22 and red >= blue * 1.08


def _is_candle_green(red: int, green: int, blue: int) -> bool:
    return green >= 68 and green >= red * 1.16 and green >= blue * 1.03


def inspect_capture_image(image: Image.Image) -> VisualCaptureInspection:
    """Inspect a screenshot without OCR.

    Binance's destructive dialog may be rendered inside a chart frame and therefore be
    invisible to page.inner_text(). The modal has a stable visual signature: a large
    Binance-yellow action button in the lower middle plus a yellow warning icon above it.
    This detector intentionally requires both signals to reduce false positives.
    """

    small, scale_x, scale_y = _analysis_image(image)
    width, height = small.size
    pixels = small.load()

    yellow_rows = [0] * height
    yellow_cols = [0] * width
    upper_yellow = 0
    for y in range(height):
        for x in range(width):
            if _is_binance_yellow(*pixels[x, y]):
                yellow_rows[y] += 1
                yellow_cols[x] += 1
                if int(width * 0.22) <= x <= int(width * 0.78) and int(height * 0.14) <= y <= int(height * 0.53):
                    upper_yellow += 1

    lower_start = int(height * 0.43)
    lower_end = int(height * 0.84)
    row_threshold = max(24, int(width * 0.12))
    row_flags = [False] * height
    for y in range(lower_start, lower_end):
        row_flags[y] = yellow_rows[y] >= row_threshold
    row_run = _longest_true_run(row_flags)

    confirm_box_small: tuple[int, int, int, int] | None = None
    if row_run and row_run[1] - row_run[0] >= max(14, int(height * 0.018)):
        y1, y2 = row_run
        col_threshold = max(8, int((y2 - y1) * 0.40))
        col_flags = [False] * width
        for x in range(width):
            count = 0
            for y in range(y1, y2):
                if _is_binance_yellow(*pixels[x, y]):
                    count += 1
            col_flags[x] = count >= col_threshold
        col_run = _longest_true_run(col_flags)
        if col_run and col_run[1] - col_run[0] >= int(width * 0.20):
            confirm_box_small = (col_run[0], y1, col_run[1], y2)

    upper_threshold = max(90, int(width * height * 0.00045))
    destructive_modal = confirm_box_small is not None and upper_yellow >= upper_threshold

    # Detect a chart that loaded its shell but not its candles. Ignore the page header and
    # footer; count red/green candle and volume pixels in the central chart region.
    chart_x1, chart_x2 = int(width * 0.02), int(width * 0.98)
    chart_y1, chart_y2 = int(height * 0.30), int(height * 0.91)
    chart_area = max(1, (chart_x2 - chart_x1) * (chart_y2 - chart_y1))
    candle_pixels = 0
    for y in range(chart_y1, chart_y2):
        for x in range(chart_x1, chart_x2):
            color = pixels[x, y]
            if _is_candle_red(*color) or _is_candle_green(*color):
                candle_pixels += 1
    candle_ratio = candle_pixels / chart_area
    chart_blank = candle_pixels < max(180, int(chart_area * 0.00105))

    confirm_box: tuple[int, int, int, int] | None = None
    if confirm_box_small is not None:
        x1, y1, x2, y2 = confirm_box_small
        confirm_box = (
            round(x1 * scale_x),
            round(y1 * scale_y),
            round(x2 * scale_x),
            round(y2 * scale_y),
        )

    return VisualCaptureInspection(
        destructive_modal=destructive_modal,
        chart_blank=chart_blank,
        confirm_button_box=confirm_box,
        candle_pixel_ratio=candle_ratio,
    )


class BinanceWebMobileCapture:
    """Capture the real Binance mobile-web trading page with Playwright.

    This zero-cost GitHub-hosted fallback does not recreate candles, add a watermark,
    or draw a fake Binance interface. The web layout can differ from the Android app.
    Every screenshot remains a preview until visually reviewed.
    """

    def __init__(self, root: Path, settings: dict[str, Any]) -> None:
        self.root = root
        self.settings = settings
        self.capture_cfg = settings["capture"]
        self.web_cfg = self.capture_cfg["web"]

    async def capture(self, symbol: str, timeframe: str, output_path: Path) -> Path:
        if not self.capture_cfg.get("web_enabled", False):
            raise WebCaptureError("Web capture is disabled. Set WEB_CAPTURE_ENABLED=true for preview runs.")
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise WebCaptureError("Playwright is not installed") from exc

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
        output_path.parent.mkdir(parents=True, exist_ok=True)
        viewport = {
            "width": int(self.web_cfg.get("viewport_width", 430)),
            "height": int(self.web_cfg.get("viewport_height", 932)),
        }
        timeout_ms = int(float(self.web_cfg.get("navigation_timeout_seconds", 65)) * 1000)
        settle_ms = int(float(self.web_cfg.get("settle_seconds", 14)) * 1000)

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=True,
                args=["--disable-dev-shm-usage", "--no-sandbox"],
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
                user_agent=(
                    "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"
                ),
            )
            page = await context.new_page()
            page.set_default_timeout(timeout_ms)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                await page.wait_for_timeout(2500)
                await self._dismiss_common_overlays(page)
                await self._dismiss_destructive_overlay(page)
                await self._select_timeframe(page, timeframe)
                await page.wait_for_timeout(settle_ms)
                await self._dismiss_common_overlays(page)
                await self._dismiss_destructive_overlay(page)
                await self._assert_clean_page(page)
                clip = await self._find_chart_clip(page, viewport)
                await page.screenshot(path=str(output_path), clip=clip, type="png", scale="device")
                self._validate_image(output_path)
            except Exception as exc:
                diagnostic = output_path.with_name(output_path.stem + "_diagnostic.png")
                try:
                    # Never leave a rejected image under the final filename. A diagnostic
                    # suffix makes it impossible for later publishing code to treat it as valid.
                    if output_path.exists():
                        diagnostic.unlink(missing_ok=True)
                        output_path.replace(diagnostic)
                    elif not diagnostic.exists():
                        await page.screenshot(path=str(diagnostic), full_page=False, type="png", scale="css")
                except Exception:
                    pass
                raise WebCaptureError(f"Binance mobile-web capture failed for {symbol} {timeframe}: {exc}") from exc
            finally:
                await context.close()
                await browser.close()

        return output_path

    async def _dismiss_common_overlays(self, page) -> None:
        labels = [
            re.compile(r"^(Accept|Accept all|Agree|Got it|I understand)$", re.I),
            re.compile(r"^(Continue in browser|Stay on web|Not now|Later)$", re.I),
        ]
        for label in labels:
            try:
                locator = page.get_by_role("button", name=label).first
                if await locator.is_visible(timeout=800):
                    await locator.click(timeout=1200)
            except Exception:
                continue
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass

    async def _page_visual_inspection(self, page) -> VisualCaptureInspection:
        screenshot = await page.screenshot(full_page=False, type="png", scale="css")
        with Image.open(io.BytesIO(screenshot)) as image:
            return inspect_capture_image(image)

    async def _dismiss_destructive_overlay(self, page) -> None:
        """Cancel the destructive chart dialog using DOM and visual safeguards."""
        body_text = ""
        try:
            body_text = await page.locator("body").inner_text(timeout=1200)
        except Exception:
            pass

        if contains_destructive_modal(body_text):
            try:
                cancel = page.get_by_role("button", name=re.compile(r"^Cancel$", re.I)).first
                if await cancel.is_visible(timeout=900):
                    await cancel.evaluate("(el) => el.click()")
                    await page.wait_for_timeout(500)
            except Exception:
                pass

        inspection = await self._page_visual_inspection(page)
        if not inspection.destructive_modal:
            return

        # Escape is safe and normally maps to Cancel even when the dialog lives in a
        # cross-origin chart frame that Playwright cannot inspect with page.inner_text().
        try:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(650)
        except Exception:
            pass
        inspection = await self._page_visual_inspection(page)
        if not inspection.destructive_modal:
            return

        # Final safe fallback: locate the yellow Confirm button visually, then click the
        # equally-sized button immediately to its left (Cancel). Never click the yellow box.
        if inspection.confirm_button_box:
            x1, y1, x2, y2 = inspection.confirm_button_box
            button_width = x2 - x1
            cancel_x = x1 - max(8, int(button_width * 0.06)) - button_width / 2
            cancel_y = (y1 + y2) / 2
            viewport = page.viewport_size or {"width": 430, "height": 932}
            if 12 <= cancel_x < viewport["width"] * 0.52 and viewport["height"] * 0.42 < cancel_y < viewport["height"] * 0.88:
                await page.mouse.click(cancel_x, cancel_y)
                await page.wait_for_timeout(700)

        if (await self._page_visual_inspection(page)).destructive_modal:
            raise WebCaptureError("Visual detector found the clear-drawings confirmation")

    async def _assert_clean_page(self, page) -> None:
        try:
            body_text = await page.locator("body").inner_text(timeout=1500)
        except Exception as exc:
            raise WebCaptureError(f"Could not validate Binance page text: {exc}") from exc
        if contains_destructive_modal(body_text):
            raise WebCaptureError("Destructive clear-drawings confirmation is still visible")
        if (await self._page_visual_inspection(page)).destructive_modal:
            raise WebCaptureError("Visual detector found the clear-drawings confirmation")

    async def _select_timeframe(self, page, timeframe: str) -> None:
        aliases = {
            "15m": ["15m", "15M"],
            "1h": ["1h", "1H"],
            "4h": ["4h", "4H"],
            "1d": ["1d", "1D"],
        }
        viewport = page.viewport_size or {
            "width": int(self.web_cfg.get("viewport_width", 430)),
            "height": int(self.web_cfg.get("viewport_height", 932)),
        }
        min_y = viewport["height"] * 0.20
        max_y = viewport["height"] * 0.47

        for text in aliases.get(timeframe.lower(), [timeframe]):
            try:
                candidates = page.get_by_text(text, exact=True)
                count = min(await candidates.count(), 16)
                ranked: list[tuple[float, Any]] = []
                for index in range(count):
                    locator = candidates.nth(index)
                    if not await locator.is_visible(timeout=700):
                        continue
                    box = await locator.bounding_box()
                    if not box:
                        continue
                    if not (min_y <= box["y"] <= max_y):
                        continue
                    if box["x"] < 8 or box["x"] > viewport["width"] * 0.76:
                        continue
                    if box["width"] > 78 or box["height"] > 54:
                        continue
                    metadata = await locator.evaluate(
                        """el => ({
                            aria: (el.getAttribute('aria-label') || '').toLowerCase(),
                            title: (el.getAttribute('title') || '').toLowerCase(),
                            cls: String(el.className || '').toLowerCase()
                        })"""
                    )
                    metadata_text = " ".join(str(value) for value in metadata.values())
                    if any(word in metadata_text for word in ("delete", "clear", "drawing", "remove")):
                        continue
                    # Prefer the compact toolbar row near one-third of the viewport.
                    score = abs((box["y"] + box["height"] / 2) - viewport["height"] * 0.34)
                    ranked.append((score, locator))

                for _, locator in sorted(ranked, key=lambda item: item[0]):
                    await locator.evaluate(
                        """el => {
                            const target = el.closest('button,[role="button"],a') || el;
                            target.dispatchEvent(new MouseEvent('click', {
                                bubbles: true, cancelable: true, view: window
                            }));
                        }"""
                    )
                    await page.wait_for_timeout(650)
                    await self._dismiss_destructive_overlay(page)
                    return
            except WebCaptureError:
                raise
            except Exception:
                continue
        raise WebCaptureError(f"Could not safely select timeframe {timeframe}")

    async def _find_chart_clip(self, page, viewport: dict[str, int]) -> dict[str, float]:
        selectors = ["iframe", "canvas", "[class*='chart']", "[data-testid*='chart']"]
        best: dict[str, float] | None = None
        best_area = 0.0
        for selector in selectors:
            try:
                count = min(await page.locator(selector).count(), 40)
                for index in range(count):
                    box = await page.locator(selector).nth(index).bounding_box()
                    if not box:
                        continue
                    area = float(box["width"] * box["height"])
                    if box["width"] >= viewport["width"] * 0.55 and box["height"] >= 220 and area > best_area:
                        best = box
                        best_area = area
            except Exception:
                continue

        if best:
            left = max(0.0, best["x"] - 8)
            top = max(0.0, best["y"] - 145)
            right = min(float(viewport["width"]), best["x"] + best["width"] + 8)
            bottom = min(float(viewport["height"]), best["y"] + best["height"] + 10)
            if right - left >= 250 and bottom - top >= 300:
                return {"x": left, "y": top, "width": right - left, "height": bottom - top}

        x1, y1, x2, y2 = [float(v) for v in self.web_cfg.get("fallback_crop_box", [0, 120, 430, 820])]
        x1 = max(0.0, min(x1, float(viewport["width"] - 1)))
        y1 = max(0.0, min(y1, float(viewport["height"] - 1)))
        x2 = max(x1 + 1, min(x2, float(viewport["width"])))
        y2 = max(y1 + 1, min(y2, float(viewport["height"])))
        return {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1}

    def _validate_image(self, path: Path) -> None:
        minimum = int(self.web_cfg.get("minimum_image_bytes", 45000))
        if not path.exists() or path.stat().st_size < minimum:
            raise WebCaptureError("Screenshot is missing or unexpectedly small")
        with Image.open(path) as image:
            width, height = image.size
            if width < 500 or height < 500:
                raise WebCaptureError(f"Screenshot dimensions are too small: {width}x{height}")
            extrema = image.convert("L").getextrema()
            if extrema is None or extrema[1] - extrema[0] < 18:
                raise WebCaptureError("Screenshot appears blank or nearly uniform")
            inspection = inspect_capture_image(image)
            if inspection.destructive_modal:
                raise WebCaptureError("Screenshot contains the clear-drawings confirmation")
            if inspection.chart_blank:
                raise WebCaptureError(
                    f"Chart appears blank or unloaded (candle pixel ratio {inspection.candle_pixel_ratio:.5f})"
                )
