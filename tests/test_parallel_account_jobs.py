from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import AccountConfig, AppConfig
from app.storage import Storage
from scripts.run_square_slot import configure_matrix_account


class ParallelAccountJobTests(unittest.TestCase):
    def make_config(self) -> AppConfig:
        return AppConfig(
            root=Path.cwd(),
            settings={},
            account_activation_mode="key_present",
            accounts=[
                AccountConfig("account_01", True, "punchy", "KEY_01", 0),
                AccountConfig("account_02", True, "casual", "KEY_02", 2),
                AccountConfig("account_03", True, "calm", "KEY_03", 4),
            ],
        )

    def test_matrix_job_activates_only_selected_account(self) -> None:
        config = self.make_config()
        with patch.dict(
            os.environ,
            {"ACTIVE_ACCOUNT_ID": "account_02", "BINANCE_SQUARE_KEY_ACTIVE": "secret-02"},
            clear=False,
        ):
            selected = configure_matrix_account(config)
            self.assertEqual(selected, "account_02")
            self.assertEqual([item.id for item in config.accounts], ["account_02"])
            self.assertEqual(os.environ["KEY_02"], "secret-02")
            self.assertEqual([item.id for item in config.active_accounts()], ["account_02"])

    def test_unknown_matrix_account_is_rejected(self) -> None:
        config = self.make_config()
        with patch.dict(
            os.environ,
            {"ACTIVE_ACCOUNT_ID": "account_99", "BINANCE_SQUARE_KEY_ACTIVE": "secret"},
            clear=False,
        ):
            with self.assertRaisesRegex(RuntimeError, "Unknown ACTIVE_ACCOUNT_ID"):
                configure_matrix_account(config)

    def test_storage_context_manager_releases_windows_database_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.db"
            with Storage(path) as storage:
                self.assertFalse(storage.symbol_in_cooldown("BTCUSDT", 1))
            path.unlink()
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
