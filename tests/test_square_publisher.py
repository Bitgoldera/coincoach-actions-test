from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import AccountConfig
from app.square_publisher import SquarePublishError, SquarePublisher
from scripts.run_square_slot import configure_live_candidate_reserve, configure_live_capture_safety


class SquarePublisherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.account = AccountConfig(
            id="account_01",
            enabled=True,
            style="punchy",
            key_env="TEST_SQUARE_KEY",
            hourly_offset_minutes=0,
        )

    def test_disabled_publisher_never_calls_node(self) -> None:
        publisher = SquarePublisher({"publishing": {"enabled": False}})
        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary) / "chart.png"
            image.write_bytes(b"png")
            self.assertEqual(
                publisher.publish_image(self.account, "hello", image),
                "DRY_RUN: publishing disabled",
            )

    def test_live_requires_real_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = Path(temporary) / "skill"
            (skill / "scripts").mkdir(parents=True)
            (skill / "scripts" / "post-image.mjs").write_text("", encoding="utf-8")
            image = Path(temporary) / "chart.png"
            image.write_bytes(b"png")
            settings = {
                "publishing": {
                    "enabled": True,
                    "official_skill_dir_env": "TEST_SKILL_DIR",
                    "request_timeout_seconds": 30,
                }
            }
            with patch.dict(os.environ, {"TEST_SKILL_DIR": str(skill), "TEST_SQUARE_KEY": ""}, clear=False):
                with self.assertRaises(SquarePublishError):
                    SquarePublisher(settings).publish_image(self.account, "hello", image)

    def test_live_candidate_reserve_requests_extra_posts(self) -> None:
        settings = {
            "market": {"timeframes": ["15m", "1h", "4h"]},
            "schedule": {
                "signals_per_account_per_hour": 1,
                "max_signals_per_timeframe_per_account": 2,
            },
        }
        plan = configure_live_candidate_reserve(
            settings, target_per_account=1, reserve_per_account=4
        )
        self.assertEqual(plan["candidate_per_account"], 5)
        self.assertEqual(settings["schedule"]["signals_per_account_per_hour"], 5)
        self.assertGreaterEqual(
            settings["schedule"]["max_signals_per_timeframe_per_account"], 2
        )

    def test_live_capture_policy_matches_verified_non_destructive_mode(self) -> None:
        settings = {"capture": {"web": {}}}
        with patch.dict(os.environ, {}, clear=False):
            policy = configure_live_capture_safety(settings)
        web = settings["capture"]["web"]
        self.assertTrue(web["allow_ma_overlay_for_capture_proof"])
        self.assertTrue(web["skip_indicator_cleanup_for_proof"])
        self.assertFalse(web["require_network_timeframe_confirmation"])
        self.assertEqual(policy["outer_capture_attempts"], 2)

    @patch("app.square_publisher.subprocess.run")
    def test_live_uses_official_image_script(self, run_mock) -> None:
        run_mock.return_value.returncode = 0
        run_mock.return_value.stdout = "Success!\nID: 123"
        run_mock.return_value.stderr = ""
        with tempfile.TemporaryDirectory() as temporary:
            skill = Path(temporary) / "skill"
            (skill / "scripts").mkdir(parents=True)
            script = skill / "scripts" / "post-image.mjs"
            script.write_text("", encoding="utf-8")
            image = Path(temporary) / "chart.png"
            image.write_bytes(b"png")
            settings = {
                "publishing": {
                    "enabled": True,
                    "official_skill_dir_env": "TEST_SKILL_DIR",
                    "request_timeout_seconds": 30,
                }
            }
            with patch.dict(
                os.environ,
                {"TEST_SKILL_DIR": str(skill), "TEST_SQUARE_KEY": "secret-value"},
                clear=False,
            ):
                output = SquarePublisher(settings).publish_image(self.account, "hello", image)
            self.assertIn("Success!", output)
            args = run_mock.call_args.args[0]
            self.assertEqual(args[0], "node")
            self.assertEqual(Path(args[1]), script)
            self.assertIn("--images", args)
            self.assertNotIn("secret-value", args)


if __name__ == "__main__":
    unittest.main()
