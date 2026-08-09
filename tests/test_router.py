from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from app.config import AccountConfig
from app.models import Signal
from app.router import AccountRouter


class RouterTest(unittest.TestCase):
    def make_signal(self, index: int) -> Signal:
        return Signal(
            signal_id=f"id{index}", symbol=f"COIN{index}USDT", base_asset=f"COIN{index}", timeframe="1h",
            side="LONG", setup="trend_pullback", score=90-index, current_price=1, entry_low=.99,
            entry_high=1.01, entry_mid=1, stop_loss=.95, tp1=1.07, tp2=1.13, tp3=1.2,
            stop_percent=5, tp1_percent=7, tp2_percent=13, tp3_percent=20, facts={},
            created_at=datetime.now(timezone.utc),
        )


    def make_timeframe_signal(self, index: int, timeframe: str, score: float) -> Signal:
        signal = self.make_signal(index)
        signal.timeframe = timeframe
        signal.score = score
        signal.signal_id = f"{timeframe}-{index}"
        return signal

    def test_timeframe_diversity_caps_five_post_batch_at_two_each(self) -> None:
        router = AccountRouter({
            "schedule": {
                "signals_per_account_per_hour": 5,
                "slot_spacing_minutes": 12,
                "max_signals_per_timeframe_per_account": 2,
                "strict_timeframe_diversity": True,
            }
        })
        accounts = [AccountConfig("a1", True, "casual", "K1", 0)]
        signals = [
            self.make_timeframe_signal(0, "4h", 100),
            self.make_timeframe_signal(1, "4h", 99),
            self.make_timeframe_signal(2, "4h", 98),
            self.make_timeframe_signal(3, "4h", 97),
            self.make_timeframe_signal(4, "1h", 96),
            self.make_timeframe_signal(5, "1h", 95),
            self.make_timeframe_signal(6, "15m", 94),
            self.make_timeframe_signal(7, "15m", 93),
        ]
        routed, shortages = router.route(signals, accounts, lambda s, a, style: s.timeframe)
        counts: dict[str, int] = {}
        for post in routed:
            counts[post.signal.timeframe] = counts.get(post.signal.timeframe, 0) + 1
        self.assertEqual(len(routed), 5)
        self.assertLessEqual(max(counts.values()), 2)
        self.assertEqual(set(counts), {"15m", "1h", "4h"})
        self.assertEqual(shortages["a1"], 0)

    def test_router_can_use_alternate_timeframe_for_same_symbol(self) -> None:
        router = AccountRouter({
            "schedule": {
                "signals_per_account_per_hour": 3,
                "slot_spacing_minutes": 12,
                "max_signals_per_timeframe_per_account": 1,
                "strict_timeframe_diversity": True,
            }
        })
        accounts = [AccountConfig("a1", True, "casual", "K1", 0)]
        same_4h = self.make_timeframe_signal(20, "4h", 100)
        same_4h.symbol = "SAMEUSDT"
        same_4h.base_asset = "SAME"
        same_1h = self.make_timeframe_signal(21, "1h", 97)
        same_1h.symbol = "SAMEUSDT"
        same_1h.base_asset = "SAME"
        signals = [
            same_4h,
            self.make_timeframe_signal(22, "4h", 99),
            self.make_timeframe_signal(23, "1h", 98),
            same_1h,
            self.make_timeframe_signal(24, "15m", 96),
        ]
        routed, _ = router.route(signals, accounts, lambda s, a, style: s.timeframe)
        self.assertEqual(len(routed), 3)
        self.assertEqual(len({post.signal.symbol for post in routed}), 3)
        self.assertEqual({post.signal.timeframe for post in routed}, {"15m", "1h", "4h"})


    def test_selected_leverage_slots_prefer_perpetual_eligible_signal(self) -> None:
        router = AccountRouter({
            "schedule": {
                "signals_per_account_per_hour": 1,
                "slot_spacing_minutes": 15,
                "max_signals_per_timeframe_per_account": 2,
                "strict_timeframe_diversity": True,
            },
            "captions": {
                "leverage": {
                    "enabled": True,
                    "daily_post_options": [96],
                    "slots_per_day": 96,
                    "prefer_perpetual_on_selected_slots": True,
                }
            },
        })
        accounts = [AccountConfig("a1", True, "casual", "K1", 0)]
        spot_only = self.make_signal(40)
        spot_only.score = 99
        spot_only.facts = {"perpetual_eligible": False}
        perpetual = self.make_signal(41)
        perpetual.score = 80
        perpetual.facts = {"perpetual_eligible": True}

        routed, _ = router.route(
            [spot_only, perpetual], accounts, lambda signal, account, style: signal.symbol
        )
        self.assertEqual(1, len(routed))
        self.assertEqual(perpetual.symbol, routed[0].signal.symbol)


    def test_account_specific_leverage_slots_do_not_sync_all_accounts(self) -> None:
        from app.caption_engine import _daily_leverage_slots

        day = date(2026, 8, 2)
        account_01_slots = _daily_leverage_slots(day, [30], account_id="account_01")
        account_02_slots = _daily_leverage_slots(day, [30], account_id="account_02")
        selected_slot = min(account_01_slots - account_02_slots)
        hour, quarter = divmod(selected_slot, 4)
        now = datetime(2026, 8, 2, hour, quarter * 15 + 3, tzinfo=timezone.utc)

        router = AccountRouter({
            "schedule": {
                "signals_per_account_per_hour": 1,
                "slot_spacing_minutes": 15,
                "max_signals_per_timeframe_per_account": 2,
                "strict_timeframe_diversity": True,
            },
            "captions": {
                "leverage": {
                    "enabled": True,
                    "daily_post_options": [30],
                    "slots_per_day": 96,
                    "prefer_perpetual_on_selected_slots": True,
                }
            },
        })
        accounts = [
            AccountConfig("account_01", True, "casual", "K1", 0),
            AccountConfig("account_02", True, "calm", "K2", 2),
        ]
        spot_high = self.make_signal(50)
        spot_high.score = 100
        spot_high.facts = {"perpetual_eligible": False}
        perp_first = self.make_signal(51)
        perp_first.score = 90
        perp_first.facts = {"perpetual_eligible": True}
        spot_second = self.make_signal(52)
        spot_second.score = 80
        spot_second.facts = {"perpetual_eligible": False}

        with patch("app.router.datetime") as mocked_datetime:
            mocked_datetime.now.return_value = now
            routed, _ = router.route(
                [spot_high, perp_first, spot_second],
                accounts,
                lambda signal, account, style: signal.symbol,
            )

        by_account = {post.account_id: post.signal for post in routed}
        self.assertTrue(by_account["account_01"].facts["perpetual_eligible"])
        self.assertFalse(by_account["account_02"].facts["perpetual_eligible"])

    def test_unique_global_allocation(self) -> None:
        router = AccountRouter({"schedule": {"signals_per_account_per_hour": 5, "slot_spacing_minutes": 12}})
        accounts = [
            AccountConfig("a1", True, "casual", "K1", 0),
            AccountConfig("a2", True, "calm", "K2", 2),
        ]
        signals = [self.make_signal(index) for index in range(10)]
        routed, shortages = router.route(signals, accounts, lambda s, a, style: f"${s.base_asset}")
        self.assertEqual(len(routed), 10)
        self.assertEqual(len({post.signal.symbol for post in routed}), 10)
        self.assertEqual(shortages["a1"], 0)
        self.assertEqual(shortages["a2"], 0)


if __name__ == "__main__":
    unittest.main()
