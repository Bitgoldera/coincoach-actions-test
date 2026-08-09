import unittest

from app.models import Candle, Candidate, MarketSymbol
from app.signal_engine import SignalEngine


class SignalRiskControlTest(unittest.TestCase):
    def setUp(self):
        self.settings = {
            "signals": {
                "minimum_stop_percent": 1.6,
                "maximum_stop_percent": 7.0,
                "maximum_stop_percent_by_timeframe": {"15m": 4.75, "1h": 6.0, "4h": 7.5},
                "maximum_tp_percent_by_timeframe": {
                    "15m": [3.0, 5.5, 8.0], "1h": [3.5, 6.5, 10.0], "4h": [5.0, 9.5, 14.0]
                },
                "entry_zone_atr_fraction": 0.15,
                "stop_buffer_atr_fraction": 0.22,
            }
        }

    def _candidate(self, lows, highs, timeframe="15m"):
        candles = []
        for i, (low, high) in enumerate(zip(lows, highs)):
            candles.append(Candle(i, 100, high, low, 100, 1000, 100000, i + 1))
        symbol = MarketSymbol("TESTUSDT", "TEST", "USDT", "TRADING", 0.01, 0.01, 8, price=100)
        return Candidate(symbol, timeframe, candles, "trend_pullback", "LONG", 70, {})

    def test_rejects_structural_stop_beyond_timeframe_cap(self):
        candidate = self._candidate([90] * 30, [101] * 30)
        self.assertIsNone(SignalEngine(self.settings).build_signal(candidate))

    def test_balanced_timeframe_tp_caps_are_applied(self):
        candidate = self._candidate([96.5] * 30, [101.0] * 30, timeframe="1h")
        signal = SignalEngine(self.settings).build_signal(candidate)
        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertLessEqual(signal.tp1_percent, 3.5)
        self.assertLessEqual(signal.tp2_percent, 6.5)
        self.assertLessEqual(signal.tp3_percent, 10.0)
        self.assertLess(signal.tp1_percent, signal.tp2_percent)
        self.assertLess(signal.tp2_percent, signal.tp3_percent)

    def test_short_targets_remain_ordered_with_closer_caps(self):
        candles = [
            Candle(i, 100, 103.5, 99.0, 100, 1000, 100000, i + 1)
            for i in range(30)
        ]
        symbol = MarketSymbol("TESTUSDT", "TEST", "USDT", "TRADING", 0.01, 0.01, 8, price=100)
        candidate = Candidate(symbol, "1h", candles, "trend_rejection", "SHORT", 70, {})
        signal = SignalEngine(self.settings).build_signal(candidate)
        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertGreater(signal.stop_loss, signal.entry_mid)
        self.assertGreater(signal.tp1, signal.tp2)
        self.assertGreater(signal.tp2, signal.tp3)
        self.assertLessEqual(signal.tp3_percent, 10.0)


if __name__ == "__main__":
    unittest.main()
