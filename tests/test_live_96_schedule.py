from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml


class Live96ScheduleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.workflow_path = cls.root / ".github" / "workflows" / "live-square-96-per-day.yml"
        cls.workflow_text = cls.workflow_path.read_text(encoding="utf-8")
        cls.worker_path = cls.root / "cloudflare_scheduler" / "src" / "index.js"
        cls.worker_text = cls.worker_path.read_text(encoding="utf-8")
        cls.wrangler_path = cls.root / "cloudflare_scheduler" / "wrangler.toml"
        cls.wrangler_text = cls.wrangler_path.read_text(encoding="utf-8")
        cls.settings = yaml.safe_load((cls.root / "config" / "settings.yaml").read_text())

    def test_github_cron_is_removed_from_live_workflow(self) -> None:
        self.assertNotRegex(self.workflow_text, r"(?m)^\s*schedule:\s*$")
        self.assertNotIn("cron:", self.workflow_text)

    def test_live_workflow_accepts_cloudflare_dispatch(self) -> None:
        self.assertIn("workflow_dispatch:", self.workflow_text)
        self.assertIn("trigger_source:", self.workflow_text)
        self.assertIn("cloudflare", self.workflow_text)
        self.assertIn("CLOUDFLARE_SLOT", self.workflow_text)

    def test_external_runs_use_repository_kill_switch(self) -> None:
        self.assertIn("vars.COINCOACH_LIVE_96_ENABLED == 'true'", self.workflow_text)

    def test_each_run_publishes_only_one_post_per_account(self) -> None:
        self.assertIn('POSTS_PER_ACCOUNT_PER_RUN: "1"', self.workflow_text)
        self.assertIn('LIVE_EXPECTED_POSTS_PER_HOUR: "4"', self.workflow_text)
        self.assertIn('PER_ACCOUNT_DAILY_LIMIT: "96"', self.workflow_text)

    def test_api_accounts_are_parallel_matrix_jobs(self) -> None:
        self.assertIn("strategy:", self.workflow_text)
        self.assertIn("fail-fast: false", self.workflow_text)
        self.assertIn("max-parallel: 6", self.workflow_text)
        for index in range(1, 7):
            self.assertIn(f"account_0{index}", self.workflow_text)
            self.assertIn(f"BINANCE_SQUARE_KEY_ACCOUNT_0{index}", self.workflow_text)
        self.assertIn("BINANCE_SQUARE_KEY_ACTIVE", self.workflow_text)
        self.assertIn("ACTIVE_ACCOUNT_ID", self.workflow_text)
        self.assertIn('STATELESS_SLOT_ROTATION: "true"', self.workflow_text)

    def test_each_api_account_has_isolated_state(self) -> None:
        self.assertIn("data/state/${{ matrix.account_id }}/coincoach.db", self.workflow_text)
        self.assertIn("data/state/${{ matrix.account_id }}/publish_ledger.json", self.workflow_text)
        self.assertIn("coincoach-live-state-${{ matrix.account_id }}-", self.workflow_text)

    def test_social_syndication_is_per_account_and_optional(self) -> None:
        self.assertNotIn("SOCIAL_SOURCE_ACCOUNT_ID", self.workflow_text)
        self.assertNotIn("matrix.account_id == 'account_02'", self.workflow_text)
        self.assertIn('SOCIAL_SYNDICATION_ENABLED: "true"', self.workflow_text)
        self.assertIn("vars.COINCOACH_SOCIAL_LIVE_APPROVED", self.workflow_text)
        for index in range(1, 7):
            suffix = f"ACCOUNT_0{index}"
            self.assertIn(f"DISCORD_WEBHOOK_URL_{suffix}", self.workflow_text)
            self.assertIn(f"FACEBOOK_PAGE_ID_{suffix}", self.workflow_text)
            self.assertIn(f"INSTAGRAM_USER_ID_{suffix}", self.workflow_text)
            self.assertIn(f"THREADS_USER_ID_{suffix}", self.workflow_text)
            self.assertIn(f"CLOUDINARY_CLOUD_NAME_{suffix}", self.workflow_text)
        self.assertIn("social_delivery_state.json", self.workflow_text)

    def test_cloudflare_has_four_evenly_spaced_base_slots(self) -> None:
        match = re.search(r'crons\s*=\s*\["([0-9,]+) \* \* \* \*"\]', self.wrangler_text)
        self.assertIsNotNone(match)
        minutes = [int(value) for value in match.group(1).split(",")]
        self.assertEqual(minutes, [6, 21, 36, 51])
        wrapped = minutes + [minutes[0] + 60]
        self.assertEqual([b - a for a, b in zip(wrapped, wrapped[1:])], [15, 15, 15, 15])

    def test_cloudflare_jitter_is_capped_at_two_minutes(self) -> None:
        self.assertIn('JITTER_MAX_SECONDS = "120"', self.wrangler_text)
        self.assertIn("value > 120", self.worker_text)
        self.assertIn("Math.random()", self.worker_text)

    def test_worker_uses_workflow_dispatch_and_secret_token(self) -> None:
        self.assertIn("/actions/workflows/", self.worker_text)
        self.assertIn("/dispatches", self.worker_text)
        self.assertIn('requireValue(env, "GITHUB_TOKEN")', self.worker_text)
        self.assertNotRegex(self.worker_text, r"github_pat_[A-Za-z0-9_]+")
        self.assertNotRegex(self.worker_text, r"ghp_[A-Za-z0-9]+")

    def test_project_settings_match_requested_cadence(self) -> None:
        self.assertEqual(self.settings["schedule"]["signals_per_account_per_hour"], 4)
        self.assertEqual(self.settings["schedule"]["slot_spacing_minutes"], 15)
        self.assertEqual(self.settings["publishing"]["per_account_daily_limit"], 96)


if __name__ == "__main__":
    unittest.main()
