from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.config import AccountConfig, AppConfig


class AccountActivationTest(unittest.TestCase):
    def make_config(self, mode: str = "key_present") -> AppConfig:
        return AppConfig(
            root=None,  # type: ignore[arg-type]
            settings={},
            account_activation_mode=mode,
            accounts=[
                AccountConfig("account_01", True, "punchy", "KEY_01", 0),
                AccountConfig("account_02", True, "casual", "KEY_02", 2),
                AccountConfig("account_03", False, "calm", "KEY_03", 4),
            ],
        )

    def test_only_keyed_enabled_account_is_active(self) -> None:
        with patch.dict(os.environ, {"KEY_01": "secret", "KEY_02": "", "KEY_03": "secret"}, clear=False):
            config = self.make_config()
            self.assertEqual([account.id for account in config.active_accounts()], ["account_01"])
            states = {item["id"]: item["state"] for item in config.account_statuses()}
            self.assertEqual(states["account_01"], "active")
            self.assertEqual(states["account_02"], "waiting_for_key")
            self.assertEqual(states["account_03"], "disabled")

    def test_enabled_only_mode_is_for_preview(self) -> None:
        with patch.dict(os.environ, {"KEY_01": "", "KEY_02": "", "KEY_03": ""}, clear=False):
            config = self.make_config("enabled_only")
            self.assertEqual([account.id for account in config.active_accounts()], ["account_01", "account_02"])


if __name__ == "__main__":
    unittest.main()
