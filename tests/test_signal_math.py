from __future__ import annotations

import unittest

from app.models import Candle, Candidate, MarketSymbol
from app.signal_engine import SignalEngine


class SignalMathTest(unittest.TestCase):
    def test_variable_targets_are_in_order(self) -> None:
        candles = []
        price = 100.0
        for index in range(100):
            price *= 1.002
            candles.append(Candle(index, price * 0.995, price * 1.01, price * 0.99, price, 1000 + index, 100000, index + 1))
        symbol = MarketSymbol("TESTUSDT", "TEST", "USDT", "TRADING", 0.01, 0.01, 8, price=price)
        candidate = Candidate(symbol, "1h", candles, "trend_pullback", "LONG", 75.0, {"momentum": "returning"})
        engine = SignalEngine({"signals": {
            "entry_zone_atr_fraction": 0.15,
            "stop_buffer_atr_fraction": 0.22,
            "minimum_stop_percent": 1.6,
            "maximum_stop_percent": 8.5,
        }})
        signal = engine.build_signal(candidate)
        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertLess(signal.stop_loss, signal.entry_mid)
        self.assertLess(signal.tp1, signal.tp2)
        self.assertLess(signal.tp2, signal.tp3)
        self.assertNotEqual(signal.tp1_percent, round(signal.tp1_percent))


if __name__ == "__main__":
    unittest.main()
