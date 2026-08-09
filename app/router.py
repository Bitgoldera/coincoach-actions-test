from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from .caption_engine import leverage_slot_active
from .config import AccountConfig
from .models import RoutedPost, Signal


class AccountRouter:
    """Allocate globally unique symbols while keeping each account's batch diverse."""

    def __init__(self, settings: dict) -> None:
        self.settings = settings

    def _select_for_account(
        self,
        signals: list[Signal],
        *,
        needed: int,
        used_symbols: set[str],
        max_per_timeframe: int,
        strict_timeframe_cap: bool,
    ) -> list[Signal]:
        assigned: list[Signal] = []
        local_symbols: set[str] = set()
        timeframe_counts: Counter[str] = Counter()

        # First pass: enforce the diversity cap. Because all signal/timeframe variants
        # remain in the pool, a lower-scoring 15m or 1h setup can be selected after the
        # first two 4h slots instead of the whole batch becoming one timeframe.
        for signal in signals:
            if len(assigned) >= needed:
                break
            if signal.symbol in used_symbols or signal.symbol in local_symbols:
                continue
            if max_per_timeframe > 0 and timeframe_counts[signal.timeframe] >= max_per_timeframe:
                continue
            assigned.append(signal)
            local_symbols.add(signal.symbol)
            timeframe_counts[signal.timeframe] += 1

        # Optional availability fallback. Production can disable strict mode if a thin
        # market temporarily cannot supply enough different timeframes. The default
        # configuration is strict, so a five-post batch stays 2/2/1 rather than 5/0/0.
        if len(assigned) < needed and not strict_timeframe_cap:
            for signal in signals:
                if len(assigned) >= needed:
                    break
                if signal.symbol in used_symbols or signal.symbol in local_symbols:
                    continue
                assigned.append(signal)
                local_symbols.add(signal.symbol)
                timeframe_counts[signal.timeframe] += 1

        return assigned

    def route(
        self,
        signals: list[Signal],
        accounts: list[AccountConfig],
        caption_builder,
    ) -> tuple[list[RoutedPost], dict[str, int]]:
        schedule = self.settings["schedule"]
        per_account = int(schedule["signals_per_account_per_hour"])
        spacing = int(schedule["slot_spacing_minutes"])
        max_per_timeframe = int(schedule.get("max_signals_per_timeframe_per_account", 0))
        strict_timeframe_cap = bool(schedule.get("strict_timeframe_diversity", True))
        active = [account for account in accounts if account.enabled]
        needed = per_account * len(active)

        now = datetime.now(timezone.utc)
        caption_cfg = self.settings.get("captions", {})
        leverage_cfg = caption_cfg.get("leverage", {})
        base_pool = sorted(signals, key=lambda item: item.score, reverse=True)

        hour_start = now.replace(minute=0, second=0, microsecond=0)
        routed: list[RoutedPost] = []
        shortages: dict[str, int] = {}
        used_symbols: set[str] = set()

        for account in active:
            prefer_perpetual = bool(
                leverage_cfg.get("prefer_perpetual_on_selected_slots", True)
            ) and leverage_slot_active(caption_cfg, now, account.id)

            # Each account has its own 30-slot daily leverage plan. During one of
            # those slots, perpetual-eligible candidates move to the front so the
            # planned caption is not silently lost to a spot-only symbol.
            if prefer_perpetual:
                account_pool = sorted(
                    base_pool,
                    key=lambda item: (
                        0 if bool(item.facts.get("perpetual_eligible", False)) else 1,
                        -item.score,
                    ),
                )
            else:
                account_pool = base_pool

            assigned = self._select_for_account(
                account_pool,
                needed=per_account,
                used_symbols=used_symbols,
                max_per_timeframe=max_per_timeframe,
                strict_timeframe_cap=strict_timeframe_cap,
            )
            used_symbols.update(signal.symbol for signal in assigned)
            shortages[account.id] = max(0, per_account - len(assigned))

            for index, signal in enumerate(assigned):
                minute = (account.hourly_offset_minutes + index * spacing) % 60
                slot_time = hour_start + timedelta(minutes=minute)
                if slot_time <= now:
                    slot_time += timedelta(hours=1)
                caption = caption_builder(signal, account.id, account.style)
                routed.append(
                    RoutedPost(
                        account_id=account.id,
                        style=account.style,
                        slot_time=slot_time,
                        signal=signal,
                        caption=caption,
                    )
                )

        shortages["global_needed"] = needed
        shortages["global_available_unique"] = len({signal.symbol for signal in base_pool})
        return routed, shortages
