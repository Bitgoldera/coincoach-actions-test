from __future__ import annotations

import unittest

from scripts.run_free_cloud import (
    candidate_slot_available,
    capture_with_preview_retry,
    clean_caption_format_valid,
    configure_preview_candidate_reserve,
    configure_preview_capture_safety,
)


class FreeCloudPreviewCapturePolicyTest(unittest.TestCase):
    def test_preview_uses_proven_non_destructive_capture_policy(self) -> None:
        settings = {
            "signals": {"symbol_cooldown_hours": 6},
            "capture": {
                "web": {
                    "allow_ma_overlay_for_capture_proof": False,
                    "require_ma_overlay_removed": True,
                    "skip_indicator_cleanup_for_proof": False,
                    "require_network_timeframe_confirmation": True,
                    "non_blocking_dialog_recovery_for_proof": False,
                }
            }
        }

        policy = configure_preview_capture_safety(settings)
        web = settings["capture"]["web"]

        self.assertTrue(web["allow_ma_overlay_for_capture_proof"])
        self.assertFalse(web["require_ma_overlay_removed"])
        self.assertTrue(web["skip_indicator_cleanup_for_proof"])
        self.assertFalse(web["require_network_timeframe_confirmation"])
        self.assertTrue(web["non_blocking_dialog_recovery_for_proof"])
        self.assertEqual(web["preview_outer_capture_attempts"], 2)
        self.assertEqual(web["preview_retry_delay_seconds"], 2.0)
        self.assertEqual(settings["signals"]["symbol_cooldown_hours"], 0)
        self.assertEqual(policy, web)


class _FakeCapture:
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    async def capture(self, symbol: str, timeframe: str, output_path) -> None:
        from app.web_capture import WebCaptureError

        self.calls += 1
        if self.calls <= self.failures:
            raise WebCaptureError(f"temporary failure for {symbol} {timeframe}")


class FreeCloudPreviewRetryTest(unittest.IsolatedAsyncioTestCase):
    async def test_outer_retry_recovers_transient_capture_failure(self) -> None:
        from pathlib import Path

        fake = _FakeCapture(failures=1)
        attempt = await capture_with_preview_retry(
            fake,  # type: ignore[arg-type]
            "BTCUSDT",
            "1h",
            Path("output.png"),
            outer_attempts=2,
            retry_delay_seconds=0,
        )
        self.assertEqual(attempt, 2)
        self.assertEqual(fake.calls, 2)

    async def test_outer_retry_preserves_final_failure(self) -> None:
        from pathlib import Path
        from app.web_capture import WebCaptureError

        fake = _FakeCapture(failures=3)
        with self.assertRaises(WebCaptureError):
            await capture_with_preview_retry(
                fake,  # type: ignore[arg-type]
                "BTCUSDT",
                "1h",
                Path("output.png"),
                outer_attempts=2,
                retry_delay_seconds=0,
            )
        self.assertEqual(fake.calls, 2)


class FreeCloudCleanCaptionValidationTest(unittest.TestCase):
    def test_clean_varied_caption_is_accepted(self) -> None:
        posts = [{"caption": (
            "keeping it simple, $RE is finding buyers again\n\n"
            "Entry: 0.4955–0.4984 | Stop Loss: 0.4873\n"
            "TP1: 0.5124 / TP2: 0.5229 / TP3: 0.542"
        )}]
        self.assertTrue(clean_caption_format_valid(posts))

    def test_removed_legacy_lines_are_rejected(self) -> None:
        base = (
            "Entry: 1–2\nTP1: 3 / TP2: 4 / TP3: 5\nStop Loss: 0.5"
        )
        self.assertFalse(clean_caption_format_valid([{"caption": base + "\nNFA. DYOR."}]))
        self.assertFalse(clean_caption_format_valid([{"caption": "Long setup | Spot chart | 1H\n" + base}]))


class FreeCloudPreviewReserveCandidateTest(unittest.TestCase):
    def test_preview_requests_four_reserve_candidates_and_restores_final_cap(self) -> None:
        settings = {
            "schedule": {
                "signals_per_account_per_hour": 5,
                "max_signals_per_timeframe_per_account": 2,
            },
            "market": {"timeframes": ["15m", "1h", "4h"]},
        }
        plan = configure_preview_candidate_reserve(settings)
        self.assertEqual(plan["target_per_account"], 5)
        self.assertEqual(plan["candidate_per_account"], 9)
        self.assertEqual(plan["final_max_per_timeframe"], 2)
        self.assertEqual(plan["candidate_max_per_timeframe"], 3)
        self.assertEqual(settings["schedule"]["signals_per_account_per_hour"], 9)
        self.assertEqual(settings["schedule"]["max_signals_per_timeframe_per_account"], 3)

    def test_final_selection_rejects_third_signal_from_same_timeframe(self) -> None:
        from collections import Counter, defaultdict

        selected_by_account = {"main": 2}
        selected_timeframes = defaultdict(Counter)
        selected_timeframes["main"]["4h"] = 2
        self.assertFalse(candidate_slot_available(
            account_id="main",
            timeframe="4h",
            selected_by_account=selected_by_account,
            selected_timeframes=selected_timeframes,
            target_per_account=5,
            max_per_timeframe=2,
        ))
        self.assertTrue(candidate_slot_available(
            account_id="main",
            timeframe="1h",
            selected_by_account=selected_by_account,
            selected_timeframes=selected_timeframes,
            target_per_account=5,
            max_per_timeframe=2,
        ))


if __name__ == "__main__":
    unittest.main()
