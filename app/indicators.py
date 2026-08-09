from __future__ import annotations

from collections.abc import Sequence

from .models import Candle


def ema(values: Sequence[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2 / (period + 1)
    out = [float(values[0])]
    for value in values[1:]:
        out.append(alpha * float(value) + (1 - alpha) * out[-1])
    return out


def sma(values: Sequence[float], period: int) -> list[float]:
    if period <= 0:
        raise ValueError("period must be positive")
    out: list[float] = []
    running = 0.0
    for index, value in enumerate(values):
        running += float(value)
        if index >= period:
            running -= float(values[index - period])
        divisor = min(index + 1, period)
        out.append(running / divisor)
    return out


def rsi(values: Sequence[float], period: int = 14) -> list[float]:
    if len(values) < 2:
        return [50.0] * len(values)
    gains = [0.0]
    losses = [0.0]
    for previous, current in zip(values, values[1:]):
        delta = current - previous
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = ema(gains, period)
    avg_loss = ema(losses, period)
    result: list[float] = []
    for gain, loss in zip(avg_gain, avg_loss):
        if loss == 0:
            result.append(100.0 if gain > 0 else 50.0)
        else:
            rs = gain / loss
            result.append(100 - (100 / (1 + rs)))
    return result


def atr(candles: Sequence[Candle], period: int = 14) -> list[float]:
    if not candles:
        return []
    true_ranges = [candles[0].high - candles[0].low]
    for previous, current in zip(candles, candles[1:]):
        true_ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
    return ema(true_ranges, period)
