import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from app.web_capture import (
    BinanceWebMobileCapture,
    WebCaptureError,
    build_binance_url,
    contains_destructive_modal,
    inspect_capture_image,
    symbol_parts,
)


class WebCaptureHelpersTest(unittest.TestCase):
    def test_symbol_parts(self):
        self.assertEqual(symbol_parts("FETUSDT"), ("FET", "USDT"))

    def test_build_url(self):
        template = "https://www.binance.com/en/trade/{base}_{quote}?type=spot"
        self.assertEqual(
            build_binance_url(template, "AAVEUSDT"),
            "https://www.binance.com/en/trade/AAVE_USDT?type=spot",
        )

    def test_detects_destructive_drawings_modal_text(self):
        self.assertTrue(contains_destructive_modal("All drawings will be permanently deleted."))
        self.assertTrue(contains_destructive_modal("Please confirm that you want to delete all drawings."))
        self.assertFalse(contains_destructive_modal("Chart loaded normally"))

    def test_visual_detector_finds_destructive_modal(self):
        image = Image.new("RGB", (860, 1394), (14, 18, 23))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((85, 320, 775, 1005), radius=36, fill=(31, 40, 52))
        draw.ellipse((350, 390, 510, 550), outline=(252, 213, 53), width=12)
        draw.ellipse((386, 426, 474, 514), fill=(252, 213, 53))
        draw.rounded_rectangle((438, 860, 726, 956), radius=20, fill=(252, 213, 53))
        result = inspect_capture_image(image)
        self.assertTrue(result.destructive_modal)
        self.assertIsNotNone(result.confirm_button_box)

    def test_visual_detector_marks_blank_chart(self):
        image = Image.new("RGB", (860, 1394), (13, 18, 24))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 860, 280), fill=(17, 22, 28))
        draw.line((0, 600, 860, 600), fill=(38, 45, 55), width=2)
        result = inspect_capture_image(image)
        self.assertFalse(result.destructive_modal)
        self.assertTrue(result.chart_blank)

    def test_visual_detector_accepts_candle_activity(self):
        image = Image.new("RGB", (860, 1394), (13, 18, 24))
        draw = ImageDraw.Draw(image)
        for index in range(55):
            x = 40 + index * 14
            top = 430 + (index % 8) * 22
            bottom = top + 90
            color = (27, 160, 110) if index % 2 else (195, 45, 65)
            draw.line((x, top - 22, x, bottom + 22), fill=color, width=4)
            draw.rectangle((x - 5, top, x + 5, bottom), fill=color)
            draw.rectangle((x - 5, 1120, x + 5, 1250 - (index % 6) * 12), fill=color)
        result = inspect_capture_image(image)
        self.assertFalse(result.destructive_modal)
        self.assertFalse(result.chart_blank)

    def test_invalid_capture_is_rejected_and_can_be_quarantined(self):
        settings = {
            "market": {"quote_asset": "USDT"},
            "capture": {
                "web_enabled": True,
                "web": {"minimum_image_bytes": 1000},
            },
        }
        capture = BinanceWebMobileCapture(Path("."), settings)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.png"
            image = Image.new("RGB", (860, 1394), (13, 18, 24))
            image.save(path)
            with self.assertRaises(WebCaptureError):
                capture._validate_image(path)

    def test_invalid_symbol(self):
        with self.assertRaises(WebCaptureError):
            symbol_parts("USDT")


class SymbolQuoteResolutionTest(unittest.TestCase):
    def test_resolves_usdt_and_usdc_pairs(self):
        from app.web_capture import resolve_symbol_quote

        self.assertEqual("USDT", resolve_symbol_quote("BTCUSDT", ["USDT", "USDC"]))
        self.assertEqual("USDC", resolve_symbol_quote("LINKUSDC", ["USDT", "USDC"]))

    def test_rejects_unknown_quote(self):
        from app.web_capture import WebCaptureError, resolve_symbol_quote

        with self.assertRaises(WebCaptureError):
            resolve_symbol_quote("BTCBUSD", ["USDT", "USDC"])


if __name__ == "__main__":
    unittest.main()
