from __future__ import annotations

import asyncio
import tempfile
import time
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from app.official_web_chart import (
    KlineIntervalTracker,
    OfficialBinanceWebChartCapture,
    TIMEFRAME_ALIASES,
    extract_kline_interval,
    extract_kline_interval_from_payload,
    normalize_timeframe,
    parse_numeric_text,
    price_deviation_percent,
    snapshot_is_fresh,
    square_mobile_clip,
    tall_mobile_clip,
)
from app.web_capture import WebCaptureError


class OfficialMobileWebHelpersTest(unittest.TestCase):
    def test_normalize_supported_timeframes(self) -> None:
        self.assertEqual(normalize_timeframe("15M"), "15m")
        self.assertEqual(normalize_timeframe("1H"), "1h")
        self.assertEqual(normalize_timeframe("4h"), "4h")

    def test_rejects_unsupported_timeframe(self) -> None:
        with self.assertRaises(WebCaptureError):
            normalize_timeframe("30s")

    def test_aliases_are_explicit(self) -> None:
        self.assertEqual(TIMEFRAME_ALIASES["15m"], ("15m", "15M"))
        self.assertIn("1H", TIMEFRAME_ALIASES["1h"])

    def test_extracts_interval_only_from_kline_requests(self) -> None:
        self.assertEqual(
            extract_kline_interval(
                "https://api.binance.com/api/v3/uiKlines?symbol=BTCUSDT&interval=15m&limit=500"
            ),
            "15m",
        )
        self.assertEqual(
            extract_kline_interval(
                "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=4h"
            ),
            "4h",
        )
        self.assertEqual(
            extract_kline_interval(
                "wss://stream.binance.com/stream?streams=btcusdt@kline_1h"
            ),
            "1h",
        )
        self.assertIsNone(
            extract_kline_interval(
                "https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT&interval=1h"
            )
        )

    def test_extracts_interval_from_multiplexed_websocket_payload(self) -> None:
        self.assertEqual(
            extract_kline_interval_from_payload(
                '{"method":"SUBSCRIBE","params":["btcusdt@kline_15m"],"id":7}'
            ),
            "15m",
        )
        self.assertEqual(
            extract_kline_interval_from_payload(
                b'{"stream":"ethusdt@kline_4h","data":{"e":"kline"}}'
            ),
            "4h",
        )
        self.assertIsNone(
            extract_kline_interval_from_payload(
                '{"method":"SUBSCRIBE","params":["btcusdt@ticker"],"id":8}'
            )
        )

    def test_kline_tracker_accepts_websocket_frames(self) -> None:
        tracker = KlineIntervalTracker()
        marker = tracker.mark()
        tracker.observe_payload(
            '{"method":"SUBSCRIBE","params":["btcusdt@kline_1h"],"id":9}'
        )
        self.assertTrue(tracker.seen_after("1h", marker))
        self.assertEqual(tracker.latest_interval(), "1h")

    def test_kline_tracker_uses_marker_for_new_requests(self) -> None:
        tracker = KlineIntervalTracker()
        tracker.observe_url(
            "https://api.binance.com/api/v3/uiKlines?symbol=BTCUSDT&interval=1d"
        )
        marker = tracker.mark()
        tracker.observe_url(
            "https://api.binance.com/api/v3/uiKlines?symbol=BTCUSDT&interval=4h"
        )
        self.assertFalse(tracker.seen_after("1d", marker))
        self.assertTrue(tracker.seen_after("4h", marker))
        self.assertEqual(tracker.latest_interval(), "4h")

    def test_numeric_price_parser_handles_commas_and_decimals(self) -> None:
        self.assertEqual(parse_numeric_text("64,200.32"), [64200.32])
        self.assertEqual(parse_numeric_text("Rs20,361.42 -1.32%"), [20361.42, 1.32])
        self.assertEqual(parse_numeric_text("0.001869"), [0.001869])

    def test_price_deviation(self) -> None:
        self.assertAlmostEqual(price_deviation_percent(100.5, 100), 0.5)
        self.assertEqual(price_deviation_percent(0, 100), float("inf"))

    def test_snapshot_freshness_is_timeframe_aware(self) -> None:
        now = 2_000_000_000_000
        self.assertTrue(snapshot_is_fresh(now - 10 * 60 * 1000, "15m", now, 60))
        self.assertFalse(snapshot_is_fresh(now - 18 * 60 * 1000, "15m", now, 60))
        self.assertTrue(snapshot_is_fresh(now - 3 * 60 * 60 * 1000, "4h", now, 60))

    def test_mobile_crop_is_square_and_within_viewport(self) -> None:
        clip = square_mobile_clip(
            viewport_width=430,
            viewport_height=932,
            price_header_y=38,
            timeframe_y=290,
            chart_bottom=760,
            top_padding=14,
            minimum_chart_pixels=170,
        )
        self.assertEqual(clip["width"], 430)
        self.assertEqual(clip["height"], 430)
        self.assertEqual(clip["y"], 24)
        self.assertGreaterEqual(clip["y"], 0)
        self.assertLessEqual(clip["y"] + clip["height"], 932)


    def test_mobile_crop_legacy_keyword_is_supported(self) -> None:
        clip = square_mobile_clip(
            viewport_width=430,
            viewport_height=932,
            timeframe_y=290,
            chart_bottom=760,
            header_above_timeframe=205,
        )
        self.assertEqual(clip["width"], 430)
        self.assertEqual(clip["height"], 430)
        self.assertGreaterEqual(clip["y"], 0)

    def test_tall_crop_starts_below_pair_and_uses_four_by_five_ratio(self) -> None:
        clip = tall_mobile_clip(
            viewport_width=430,
            viewport_height=932,
            pair_bottom_y=-4,
            timeframe_y=285,
            chart_bottom=900,
            aspect_ratio=0.8,
            top_padding=4,
            minimum_chart_pixels=250,
        )
        self.assertEqual(clip["width"], 430)
        self.assertAlmostEqual(clip["height"], 537.5)
        self.assertEqual(clip["y"], 0)
        self.assertLessEqual(clip["y"] + clip["height"], 932)

    def test_tall_crop_supports_safe_down_shift_and_jitter(self) -> None:
        clip = tall_mobile_clip(
            viewport_width=430,
            viewport_height=932,
            pair_bottom_y=-4,
            timeframe_y=285,
            chart_bottom=900,
            aspect_ratio=0.8,
            top_padding=4,
            minimum_chart_pixels=250,
            base_down_shift_pixels=32,
            vertical_jitter_pixels=18,
            timeframe_safe_margin_pixels=85,
        )
        self.assertEqual(clip["y"], 50)
        self.assertLessEqual(clip["y"], 200)
        self.assertLessEqual(clip["y"] + clip["height"], 932)

    def test_tall_crop_never_cuts_detected_live_price(self) -> None:
        clip = tall_mobile_clip(
            viewport_width=430,
            viewport_height=932,
            pair_bottom_y=-4,
            price_top_y=18,
            timeframe_y=285,
            chart_bottom=900,
            aspect_ratio=0.8,
            top_padding=4,
            minimum_chart_pixels=250,
            base_down_shift_pixels=32,
            vertical_jitter_pixels=18,
            timeframe_safe_margin_pixels=85,
            price_safe_padding_pixels=10,
        )
        self.assertEqual(clip["y"], 8)
        self.assertLessEqual(clip["y"], 18 - 10)

    def test_disabled_capture_refuses_to_run(self) -> None:
        settings = {
            "market": {"quote_asset": "USDT"},
            "capture": {
                "web_enabled": False,
                "web": {"url_template": "https://www.binance.com/en/trade/{base}_{quote}?type=spot"},
            },
        }
        capture = OfficialBinanceWebChartCapture(Path("."), settings)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(WebCaptureError):
                asyncio.run(capture.capture("BTCUSDT", "15m", Path(directory) / "btc.png"))

    def test_production_square_clip_uses_full_mobile_width(self) -> None:
        clip = tall_mobile_clip(
            viewport_width=430,
            viewport_height=932,
            pair_bottom_y=-4,
            timeframe_y=188,
            chart_bottom=850,
            price_top_y=10,
            aspect_ratio=1.0,
            top_padding=4,
            minimum_chart_pixels=220,
            base_down_shift_pixels=8,
            vertical_jitter_pixels=4,
            timeframe_safe_margin_pixels=85,
            price_safe_padding_pixels=10,
        )
        self.assertEqual(clip["width"], 430)
        self.assertEqual(clip["height"], 430)
        self.assertGreaterEqual(clip["y"], 0)
        self.assertLessEqual(clip["y"] + clip["height"], 932)

    def test_output_normalization_creates_1080_square(self) -> None:
        settings = {
            "market": {"quote_asset": "USDT"},
            "capture": {
                "web_enabled": True,
                "web": {
                    "output_width_pixels": 1080,
                    "output_height_pixels": 1080,
                },
            },
        }
        capture = OfficialBinanceWebChartCapture(Path("."), settings)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mobile.png"
            image = Image.new("RGB", (860, 900), "#1e2329")
            draw = ImageDraw.Draw(image)
            for x in range(80, 790, 22):
                draw.line((x, 250, x, 700), fill="#2ebd85", width=4)
                draw.rectangle((x - 5, 390, x + 5, 500), fill="#f6465d")
            image.save(path)
            capture._normalize_output(path)
            with Image.open(path) as result:
                self.assertEqual(result.size, (1080, 1080))


class ExactMobileTimeframeBrowserTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            self.skipTest("Playwright is not installed")
        self._playwright = await async_playwright().start()
        try:
            self._browser = await self._playwright.chromium.launch(headless=True)
        except Exception as first_exc:
            try:
                self._browser = await self._playwright.chromium.launch(
                    headless=True, executable_path="/usr/bin/chromium", args=["--no-sandbox"]
                )
            except Exception as exc:
                await self._playwright.stop()
                self.skipTest(f"Chromium is not installed: {first_exc}; fallback: {exc}")
        self._context = await self._browser.new_context(
            viewport={"width": 430, "height": 932},
            screen={"width": 430, "height": 932},
            is_mobile=True,
            has_touch=True,
            user_agent=(
                "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36"
            ),
        )
        self._page = await self._context.new_page()
        self.settings = {
            "market": {"quote_asset": "USDT"},
            "capture": {
                "web_enabled": True,
                "web": {
                    "viewport_width": 430,
                    "viewport_height": 932,
                    "maximum_mobile_viewport_width": 540,
                    "url_template": "https://www.binance.com/en/trade/{base}_{quote}?type=spot",
                },
            },
        }
        self.capture = OfficialBinanceWebChartCapture(Path("."), self.settings)

    async def asyncTearDown(self) -> None:
        if hasattr(self, "_context"):
            await self._context.close()
        if hasattr(self, "_browser"):
            await self._browser.close()
        if hasattr(self, "_playwright"):
            await self._playwright.stop()

    async def _set_mock_mobile_chart(self, selected: str = "1d") -> None:
        await self._page.set_content(
            f"""
            <html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head><body style='margin:0;background:#1e2329;color:#9aa4b2;font-family:Arial'>
              <div id='price' style='position:absolute;top:35px;left:25px;font-size:48px;color:#2ebd85'>64,200.32</div>
              <div id='stats' style='position:absolute;top:35px;right:25px;font-size:18px'>24h High 64,744.81</div>
              <div id='row' style='position:absolute;top:260px;left:20px;width:390px;height:48px;display:flex;gap:24px;align-items:center'>
                <button data-tf='15m' style='border:0;background:transparent;color:{'#fff' if selected == '15m' else '#8b949e'}'>15m</button>
                <button data-tf='1h' style='border:0;background:transparent;color:{'#fff' if selected == '1h' else '#8b949e'}'>1h</button>
                <button data-tf='4h' style='border:0;background:transparent;color:{'#fff' if selected == '4h' else '#8b949e'}'>4h</button>
                <button data-tf='1d' style='border:0;background:transparent;color:{'#fff' if selected == '1d' else '#8b949e'}'>1D</button>
                <span>More</span>
              </div>
              <button id='danger' title='Delete drawings' style='position:absolute;top:260px;right:3px'>trash</button>
              <canvas id='chart' width='400' height='500' style='position:absolute;top:310px;left:15px;width:400px;height:500px;background:#171b22'></canvas>
              <script>
                document.querySelectorAll('[data-tf]').forEach(el => el.addEventListener('click', () => {{
                  document.querySelectorAll('[data-tf]').forEach(item => item.style.color = 'rgb(139, 148, 158)');
                  el.style.color = 'rgb(255, 255, 255)';
                  document.body.dataset.clicked = el.dataset.tf;
                }}));
                document.querySelector('#danger').addEventListener('click', () => document.body.dataset.clicked='danger');
                const c=document.querySelector('#chart').getContext('2d');
                for(let x=20;x<390;x+=16){{c.fillStyle=x%32===0?'#2ebd85':'#f6465d';c.fillRect(x,120+(x%70),5,120);}}
              </script>
            </body></html>
            """
        )

    async def test_safe_selector_clicks_exact_timeframe_not_delete_control(self) -> None:
        await self._set_mock_mobile_chart(selected="1d")
        element = await self.capture._safe_timeframe_element(self._page, "4h")
        await element.click()
        self.assertEqual(await self._page.locator("body").get_attribute("data-clicked"), "4h")
        selected, reason = await self.capture._verify_selected_timeframe(self._page, "4h")
        self.assertTrue(selected, reason)

    async def test_exact_timeframe_force_fallback_handles_temporary_cover(self) -> None:
        await self._set_mock_mobile_chart(selected="1d")
        element = await self.capture._safe_timeframe_element(self._page, "4h")
        box = await element.bounding_box()
        self.assertIsNotNone(box)
        await self._page.evaluate(
            """box => {
              const cover = document.createElement('div');
              cover.id = 'temporary-cover';
              cover.style.position = 'fixed';
              cover.style.left = `${box.x}px`;
              cover.style.top = `${box.y}px`;
              cover.style.width = `${box.width}px`;
              cover.style.height = `${box.height}px`;
              cover.style.zIndex = '9999';
              cover.style.pointerEvents = 'auto';
              cover.style.background = 'rgba(0,0,0,.01)';
              document.body.appendChild(cover);
            }""",
            box,
        )
        mode = await self.capture._click_exact_timeframe_control(self._page, element, "4h")
        self.assertEqual(mode, "dom_exact_control_after_cover")
        self.assertEqual(await self._page.locator("body").get_attribute("data-clicked"), "4h")
        self.assertNotEqual(await self._page.locator("body").get_attribute("data-clicked"), "danger")

    async def test_selected_timeframe_uses_visual_state(self) -> None:
        await self._set_mock_mobile_chart(selected="1h")
        selected, reason = await self.capture._verify_selected_timeframe(self._page, "1h")
        self.assertTrue(selected, reason)
        wrong, _ = await self.capture._verify_selected_timeframe(self._page, "4h")
        self.assertFalse(wrong)

    async def test_mobile_layout_verification_accepts_mobile_context(self) -> None:
        await self._set_mock_mobile_chart(selected="15m")
        await self.capture._assert_mobile_layout(self._page, {"width": 430, "height": 932})

    async def test_visible_price_prefers_large_current_price(self) -> None:
        await self._set_mock_mobile_chart(selected="15m")
        value = await self.capture._find_visible_live_price(self._page, 64200.30)
        self.assertAlmostEqual(value, 64200.32, places=2)


    async def test_ma_cleanup_clicks_rightmost_legend_control(self) -> None:
        await self._page.set_content(
            """
            <html><body style='margin:0;background:#1e2329;color:#aaa'>
              <div id='legend' style='position:absolute;top:330px;left:30px;width:360px;height:42px'>
                <span id='ma' style='display:inline-block;font-size:18px'>MA(7) 64,000 MA(25) 64,100 MA(99) 64,200</span>
                <button id='eye' aria-label='Hide indicator' style='width:24px;height:24px'>E</button>
                <button id='gear' aria-label='Indicator settings' style='width:24px;height:24px'>G</button>
                <button id='close' aria-label='Remove indicator' style='width:24px;height:24px'>X</button>
              </div>
              <script>
                document.querySelector('#close').addEventListener('click', () => {
                  document.querySelector('#legend').remove();
                  document.body.dataset.removed='yes';
                });
              </script>
            </body></html>
            """
        )
        removed = await self.capture._try_disable_moving_average_overlays(self._page)
        self.assertTrue(removed)
        self.assertEqual(await self._page.locator('body').get_attribute('data-removed'), 'yes')

    async def test_position_mobile_chart_card_scrolls_below_pair_name(self) -> None:
        await self._page.set_content(
            """
            <html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head><body style='margin:0;min-height:1800px;background:#1e2329;color:#fff'>
              <div id='pair' style='position:absolute;top:180px;left:24px;font-size:34px'>BTC/USDT</div>
              <div style='position:absolute;top:245px;left:24px;font-size:52px'>64,200.32</div>
              <div style='position:absolute;top:520px;left:20px;width:390px;height:48px'>
                <span>15m</span><span>1h</span><span>4h</span><span>1D</span>
              </div>
              <canvas width='400' height='700' style='position:absolute;top:580px;left:15px;width:400px;height:700px'></canvas>
            </body></html>
            """
        )
        await self.capture._position_mobile_chart_card(self._page, "BTCUSDT")
        pair_bottom = await self._page.locator('#pair').evaluate("el => el.getBoundingClientRect().bottom")
        self.assertLessEqual(pair_bottom, 2)

    async def test_hidden_destructive_text_is_not_treated_as_visible_modal(self) -> None:
        await self._page.set_content(
            """
            <html><body style='margin:0;background:#1e2329;color:#fff'>
              <div role='dialog' style='display:none'>
                All drawings will be permanently deleted
                <button>Confirm</button>
              </div>
              <div style='font-size:32px'>BTC/USDT</div>
            </body></html>
            """
        )
        self.assertFalse(await self.capture._destructive_dialog_visible(self._page))
        await self.capture._assert_page_clean(self._page)

    async def test_visible_chart_panel_with_dialog_class_is_not_a_modal(self) -> None:
        await self._page.set_content(
            """
            <html><body style='margin:0;background:#1e2329;color:#fff'>
              <div class='chart-dialog-menu' style='position:absolute;left:20px;top:200px;width:390px;height:250px'>
                Delete all drawings
                <button>Clear</button>
              </div>
              <div style='font-size:32px'>BTC/USDT</div>
            </body></html>
            """
        )
        self.assertFalse(await self.capture._destructive_dialog_visible(self._page))

    async def test_visible_destructive_dialog_is_cancelled_safely(self) -> None:
        await self._page.set_content(
            """
            <html><body style='margin:0;background:#1e2329;color:#fff'>
              <div id='modal' role='dialog' aria-modal='true'
                   style='position:fixed;left:40px;top:180px;width:350px;height:220px;background:#2b3139;padding:20px'>
                <p>All drawings will be permanently deleted</p>
                <button id='cancel'>Cancel</button>
                <button id='confirm'>Confirm</button>
              </div>
              <script>
                document.querySelector('#cancel').addEventListener('click', () => {
                  document.querySelector('#modal').style.display='none';
                });
              </script>
            </body></html>
            """
        )
        self.assertTrue(await self.capture._destructive_dialog_visible(self._page))
        await self.capture._cancel_destructive_dialog(self._page)
        self.assertFalse(await self.capture._destructive_dialog_visible(self._page))


    async def test_visible_destructive_warning_without_dialog_role_is_cancelled(self) -> None:
        await self._page.set_content(
            """
            <html><body style='margin:0;background:#1e2329;color:#fff'>
              <div id='modal' style='position:fixed;left:40px;top:180px;width:350px;height:500px;background:#2b3139;padding:20px'>
                <p>All drawings will be permanently deleted.</p>
                <p>Please confirm that you want to delete all drawings.</p>
                <button id='cancel' style='position:absolute;top:430px'>Cancel</button>
                <button id='confirm' style='position:absolute;top:430px;left:160px'>Confirm</button>
              </div>
              <script>
                document.querySelector('#cancel').addEventListener('click', () => {
                  document.querySelector('#modal').style.display='none';
                });
              </script>
            </body></html>
            """
        )
        self.assertTrue(await self.capture._destructive_dialog_visible(self._page))
        await self.capture._cancel_destructive_dialog(self._page)
        self.assertFalse(await self.capture._destructive_dialog_visible(self._page))

    async def test_clear_chart_hover_never_clicks_toolbar_coordinates(self) -> None:
        await self._page.set_content(
            """
            <html><body style='margin:0;background:#1e2329;color:#fff'>
              <button id='danger' style='position:fixed;right:0;top:0;width:30px;height:30px'>X</button>
              <canvas id='chart' width='430' height='700' style='position:absolute;top:100px;left:0;width:430px;height:700px'></canvas>
              <script>
                document.querySelector('#danger').addEventListener('click', () => {
                  document.body.dataset.dangerClicked='yes';
                });
              </script>
            </body></html>
            """
        )
        await self.capture._clear_chart_hover(self._page)
        self.assertIsNone(await self._page.locator('body').get_attribute('data-danger-clicked'))

    async def test_mobile_geometry_finds_timeframe_and_chart(self) -> None:
        await self._set_mock_mobile_chart(selected="15m")
        geometry = await self.capture._mobile_chart_geometry(
            self._page, {"width": 430, "height": 932}
        )
        self.assertGreater(geometry["timeframe_y"], 200)
        self.assertGreater(geometry["chart_bottom"], geometry["timeframe_y"])


if __name__ == "__main__":
    unittest.main()
