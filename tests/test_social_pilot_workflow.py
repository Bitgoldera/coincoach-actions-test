from __future__ import annotations

import unittest
from pathlib import Path

import yaml


class SocialPilotWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.path = cls.root / ".github" / "workflows" / "manual-account-02-social-pilot.yml"
        cls.text = cls.path.read_text(encoding="utf-8")
        cls.data = yaml.safe_load(cls.text)

    def test_workflow_is_valid_yaml_and_manual_only(self) -> None:
        self.assertIsInstance(self.data, dict)
        self.assertIn("workflow_dispatch:", self.text)
        self.assertNotIn("schedule:", self.text)

    def test_pilot_targets_only_account_02(self) -> None:
        self.assertIn("ACTIVE_ACCOUNT_ID: account_02", self.text)
        self.assertIn("BINANCE_SQUARE_KEY_ACCOUNT_02", self.text)
        self.assertNotIn("matrix:", self.text)
        self.assertNotIn("BINANCE_SQUARE_KEY_ACCOUNT_01", self.text)

    def test_pilot_requires_explicit_confirmation_and_one_destination(self) -> None:
        self.assertIn("POST_ACCOUNT_02_SOCIAL_PILOT", self.text)
        self.assertIn("Select at least one social destination", self.text)
        self.assertIn('SOCIAL_SYNDICATION_ENABLED: "true"', self.text)
        self.assertIn('SOCIAL_LIVE_APPROVED: "true"', self.text)

    def test_pilot_validates_social_result_after_square(self) -> None:
        square_index = self.text.index("python -m scripts.run_square_slot")
        validation_index = self.text.index("python -m scripts.validate_social_pilot")
        self.assertLess(square_index, validation_index)


if __name__ == "__main__":
    unittest.main()
