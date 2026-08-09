from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from typing import Callable

from .models import Signal
from .storage import Storage


STYLE_OPENERS = {
    "punchy": [
        "quick one here", "this one looks clean", "watching this setup", "keeping it simple",
        "one to watch", "small setup here", "eyes on this one", "worth a look here",
    ],
    "casual": [
        "alright", "okay", "not gonna lie", "this one caught my eye",
        "just noticed this", "looking at this one", "this is getting interesting", "keeping watch here",
    ],
    "calm": [
        "watching", "keeping an eye on", "worth watching", "still tracking",
        "quietly watching", "this level on", "the structure on", "the current range on",
    ],
    "reactive": [
        "looks like", "that move on", "this bounce on", "the reaction on",
        "seeing a shift on", "momentum on", "that rejection on", "price action on",
    ],
    "direct": [
        "long setup on", "short setup on", "taking the long side on", "the short side looks cleaner on",
        "watching long on", "watching short on", "leaning long on", "leaning short on",
    ],
    "chart_reader": [
        "the chart on", "buyers are showing up on", "sellers are leaning on", "structure on",
        "the candles on", "price action on", "the trend on", "the current range on",
    ],
}

SETUP_OBSERVATIONS = {
    "breakout_continuation": [
        "just pushed through the level and buyers are still holding it",
        "is holding above the breakout and momentum is staying firm",
        "reclaimed resistance and the next move could open from here",
        "is trying to build above the breakout instead of giving it back",
    ],
    "breakdown_continuation": [
        "lost support and sellers are still pressing the move",
        "is staying heavy below the broken level",
        "keeps failing to recover support, so the short side still looks cleaner",
        "broke the floor and the bounce is still looking weak",
    ],
    "trend_pullback": [
        "pulled back without breaking structure and buyers are stepping back in",
        "is holding the dip better than expected",
        "gave a controlled pullback and the trend is trying to continue",
        "is finding buyers again around the pullback zone",
    ],
    "trend_rejection": [
        "bounced into resistance and sellers showed up again",
        "is struggling to hold the recovery",
        "keeps rejecting the same area, so the short side is worth watching",
        "tried to recover but the bounce is losing energy again",
    ],
    "rebound_continuation": [
        "is recovering nicely here and buyers are stepping back in",
        "is building again after the rebound",
        "held the low and momentum is slowly returning",
        "is starting to recover after defending the lower zone",
    ],
    "resistance_rejection": [
        "looks tired around this level and sellers are coming back",
        "just rejected again, so the short side makes more sense here",
        "is losing strength near resistance",
        "failed to hold the push and is slipping back under resistance",
    ],
}


def _pick(options: list[str], seed: bytes, offset: int) -> str:
    return options[seed[offset % len(seed)] % len(options)]


def _fmt(value: float) -> str:
    if value >= 1000:
        return f"{value:.2f}"
    if value >= 1:
        return f"{value:.4f}".rstrip("0").rstrip(".")
    if value >= 0.01:
        return f"{value:.5f}".rstrip("0").rstrip(".")
    return f"{value:.8f}".rstrip("0").rstrip(".")


def _format_timeframe(value: str) -> str:
    normalized = str(value).strip().lower()
    labels = {"15m": "15M", "1h": "1H", "4h": "4H", "1d": "1D"}
    return labels.get(normalized, str(value).upper())


def _format_signal_detail_lines(
    signal: Signal,
    seed: bytes,
    *,
    vary_layout: bool = True,
) -> list[str]:
    """Format the exact signal levels using one of several readable layouts.

    Layout choice is deterministic for a signal/account/style seed. Numbers never
    change; only line breaks and separators vary so a batch does not look templated.
    """

    entry = f"Entry: {_fmt(signal.entry_low)}–{_fmt(signal.entry_high)}"
    tp1 = f"TP1: {_fmt(signal.tp1)}"
    tp2 = f"TP2: {_fmt(signal.tp2)}"
    tp3 = f"TP3: {_fmt(signal.tp3)}"
    stop = f"Stop Loss: {_fmt(signal.stop_loss)}"

    if not vary_layout:
        return [entry, f"{tp1} | {tp2} | {tp3}", stop]

    layout = seed[19 % len(seed)] % 6
    if layout == 0:
        return [entry, f"{tp1} | {tp2} | {tp3}", stop]
    if layout == 1:
        return [entry, f"{tp1} / {tp2} / {tp3}", stop]
    if layout == 2:
        return [f"{entry} | {stop}", f"{tp1} / {tp2} / {tp3}"]
    if layout == 3:
        return [entry, f"{tp1} → {tp2} → {tp3}", stop]
    if layout == 4:
        return [f"{entry}  •  {stop}", f"{tp1} | {tp2} | {tp3}"]
    return [f"{entry} | {tp1} / {tp2} / {tp3} | {stop}"]


def _market_context(settings: dict, side: str) -> str:
    market_type = str(settings.get("market", {}).get("market_type", "spot")).strip().lower()
    caption_cfg = settings.get("captions", {})
    if market_type in {"future", "futures", "perpetual", "perp"}:
        return str(caption_cfg.get("futures_context_label", "Futures"))
    # A SHORT opinion can still be based on a Spot chart, so call it a setup rather
    # than implying that a native Spot short order is being placed.
    return str(caption_cfg.get("spot_context_label", "Spot chart"))


def _used_openers(recent_phrases: set[str], openers: list[str]) -> set[str]:
    used: set[str] = set()
    for phrase in recent_phrases:
        normalized = phrase.lower().strip()
        for opener in openers:
            opener_lower = opener.lower()
            if normalized.startswith(opener_lower):
                used.add(opener)
    return used


def _used_observations(recent_phrases: set[str], observations: list[str]) -> set[str]:
    used: set[str] = set()
    for phrase in recent_phrases:
        normalized = phrase.lower()
        for observation in observations:
            if observation.lower() in normalized:
                used.add(observation)
    return used


def _compose_line(style: str, opener: str, cashtag: str, observation: str, use_guys: bool) -> str:
    base = f"{cashtag} {observation}"

    # "guys" replaces the opener instead of stacking with it. This prevents awkward
    # constructions such as "guys, worth a look, $XRP...".
    if use_guys:
        return f"guys, {base}"

    if style in {"punchy", "casual"}:
        return f"{opener}, {base}"

    if style == "calm":
        if opener in {"watching", "keeping an eye on", "worth watching", "still tracking", "quietly watching"}:
            return f"{opener} {cashtag}, {observation}"
        return f"{opener} {cashtag}, {observation}"

    if style == "reactive":
        if opener == "looks like":
            return f"looks like {base}"
        return f"{opener} {cashtag}, {observation}"

    if style == "direct":
        return f"{opener} {cashtag}, {observation}"

    if style == "chart_reader":
        return f"{opener} {cashtag}, {observation}"

    return f"{opener}, {base}"


def _slot_index_utc(now: datetime, slots_per_day: int = 96) -> int:
    """Map the current UTC time to one of the 96 fifteen-minute live slots."""

    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    utc_now = now.astimezone(timezone.utc)
    index = (utc_now.hour * 60 + utc_now.minute) // 15
    return max(0, min(slots_per_day - 1, index))


def _daily_leverage_slots(
    day: date,
    daily_options: list[int],
    *,
    slots_per_day: int = 96,
    account_id: str = "global",
) -> set[int]:
    """Choose a deterministic per-account daily subset without persistent state.

    Every account receives its own distribution, so leverage captions do not appear
    on all Binance accounts during the same 15-minute slots. The configured quota is
    still exact for each account when all scheduled slots run.
    """

    valid_options = sorted({
        max(0, min(slots_per_day, int(value)))
        for value in daily_options
    })
    if not valid_options:
        return set()
    scope = str(account_id).strip() or "global"
    day_seed = hashlib.sha256(
        f"coincoach-leverage-day:{scope}:{day.isoformat()}".encode()
    ).digest()
    quota = valid_options[int.from_bytes(day_seed[:2], "big") % len(valid_options)]
    ranked = sorted(
        range(slots_per_day),
        key=lambda slot: hashlib.sha256(
            f"coincoach-leverage-slot:{scope}:{day.isoformat()}:{slot}".encode()
        ).digest(),
    )
    return set(ranked[:quota])


def _leverage_value(signal: Signal, seed: bytes, leverage_cfg: dict) -> int:
    # bStock / tokenized TradFi gets a hard 5x override. Normal crypto keeps
    # the configured leverage ladder (including the existing high-leverage values).
    market_tags = {str(tag).lower() for tag in signal.facts.get("market_tags", [])}
    if "tradfi" in market_tags or "bstock" in market_tags:
        return 5
    by_timeframe = leverage_cfg.get("values_by_timeframe", {})
    values = by_timeframe.get(signal.timeframe, leverage_cfg.get("values", [20, 30, 40, 50, 70, 100]))
    normalized = [int(value) for value in values if int(value) > 0]
    if not normalized:
        normalized = [10]
    return normalized[seed[23 % len(seed)] % len(normalized)]


def _inject_leverage_phrase(opening: str, signal: Signal, leverage: int, seed: bytes) -> str:
    """Blend leverage naturally inside the opening sentence.

    Leverage is never emitted as a standalone line, sentence prefix, or sentence
    ending. It sits beside the cashtag as a human-sounding aside while the original
    market observation remains the main point of the line.
    """

    cashtag = f"${signal.base_asset}"
    clauses = [
        f"with leverage near {leverage}x",
        f"with the setup mapped around {leverage}x",
        f"keeping leverage around {leverage}x",
        f"with roughly {leverage}x on the setup",
        f"with a {leverage}x leverage plan",
        f"while I keep leverage near {leverage}x",
        f"with leverage sitting around {leverage}x",
        f"with {leverage}x as the working leverage",
    ]
    clause = clauses[seed[24 % len(seed)] % len(clauses)]

    position = opening.find(cashtag)
    if position >= 0:
        end = position + len(cashtag)
        before = opening[:end]
        after = opening[end:]
        if after.startswith(","):
            return f"{before}, {clause}{after}"
        return f"{before}, {clause},{after}"

    if "," in opening:
        first, rest = opening.split(",", 1)
        return f"{first}, {clause}, {rest.lstrip()}"
    return f"{opening} while {clause} remains in view"


def leverage_slot_active(
    caption_cfg: dict,
    now: datetime,
    account_id: str = "global",
) -> bool:
    leverage_cfg = caption_cfg.get("leverage", {})
    if not bool(leverage_cfg.get("enabled", False)):
        return False
    slots_per_day = int(leverage_cfg.get("slots_per_day", 96))
    daily_options = [
        int(value)
        for value in leverage_cfg.get("daily_post_options", [30])
    ]
    utc_now = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    slot_index = _slot_index_utc(utc_now, slots_per_day)
    return slot_index in _daily_leverage_slots(
        utc_now.date(),
        daily_options,
        slots_per_day=slots_per_day,
        account_id=account_id,
    )


def _maybe_add_leverage(
    opening: str,
    signal: Signal,
    seed: bytes,
    caption_cfg: dict,
    now: datetime,
    account_id: str,
) -> str:
    leverage_cfg = caption_cfg.get("leverage", {})
    if not leverage_slot_active(caption_cfg, now, account_id):
        return opening
    if bool(leverage_cfg.get("require_perpetual_eligible", True)) and not bool(
        signal.facts.get("perpetual_eligible", False)
    ):
        return opening

    leverage = _leverage_value(signal, seed, leverage_cfg)
    return _inject_leverage_phrase(opening, signal, leverage, seed)


def _hashtag_line(signal: Signal, seed: bytes, hashtag_cfg: dict) -> str:
    """Build exactly four hashtags: asset + one variant from each configured group."""
    groups = hashtag_cfg or {}
    binance = list(groups.get("binance", ["#Binance", "#binance"]))
    write2earn = list(groups.get("write2earn", ["#Write2Earn", "#Write2Earn!"]))
    crypto = list(groups.get("crypto", ["#crypto", "#Crypto"]))
    asset = str(signal.base_asset).strip().upper().replace(" ", "")
    def choose(options: list[str], offset: int) -> str:
        valid = [str(value).strip() for value in options if str(value).strip()]
        return valid[seed[offset % len(seed)] % len(valid)] if valid else ""
    return " ".join(part for part in (f"#{asset}", choose(binance, 7), choose(write2earn, 13), choose(crypto, 29)) if part)


class CaptionEngine:
    def __init__(
        self,
        storage: Storage,
        settings: dict,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.storage = storage
        self.settings = settings
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def generate(self, signal: Signal, account_id: str, style: str) -> str:
        seed = hashlib.sha256(f"{signal.signal_id}:{account_id}:{style}".encode()).digest()
        max_recent = int(self.settings["captions"]["maximum_recent_phrases"])
        recent = self.storage.recent_phrases(account_id, max_recent)
        openers = STYLE_OPENERS.get(style, STYLE_OPENERS["casual"])
        observations = SETUP_OBSERVATIONS.get(signal.setup, ["is setting up around this level"])
        cashtag = f"${signal.base_asset}"
        used_openers = _used_openers(recent, openers)
        used_observations = _used_observations(recent, observations)

        # Use "guys" only occasionally and never as the default voice.
        guys_probability = float(self.settings["captions"].get("guys_probability", 0.05))
        guys_unit = int.from_bytes(seed[:2], "big") / 65535
        use_guys = guys_unit < guys_probability and not any(p.lower().startswith("guys") for p in recent)

        candidates: list[tuple[str, str, str]] = []
        attempts = max(len(openers), len(observations)) * 8
        for index in range(attempts):
            opener = _pick(openers, seed, index + 2)
            observation = _pick(observations, seed, index + 11)

            if style == "direct":
                if signal.side == "SHORT" and opener in {
                    "long setup on", "taking the long side on", "watching long on", "leaning long on"
                }:
                    opener = "watching short on"
                elif signal.side == "LONG" and opener in {
                    "short setup on", "the short side looks cleaner on", "watching short on", "leaning short on"
                }:
                    opener = "watching long on"

            line = _compose_line(style, opener, cashtag, observation, use_guys and index == 0)
            line = line.replace("  ", " ").strip()
            candidates.append((opener, observation, line))

        # Prefer a fresh full line, opener, and observation. This stops a five-post
        # batch from sounding like the same template with a different coin ticker.
        opening = None
        for opener, observation, line in candidates:
            if line not in recent and opener not in used_openers and observation not in used_observations:
                opening = line
                break

        if opening is None:
            for opener, observation, line in candidates:
                if line not in recent and observation not in used_observations:
                    opening = line
                    break

        if opening is None:
            opening = next((line for _, _, line in candidates if line not in recent), candidates[0][2])

        caption_cfg = self.settings.get("captions", {})
        opening = _maybe_add_leverage(
            opening, signal, seed, caption_cfg, self.now_provider(), account_id
        )
        self.storage.remember_phrase(account_id, opening)
        signal_detail_lines = _format_signal_detail_lines(
            signal,
            seed,
            vary_layout=bool(caption_cfg.get("vary_signal_detail_layout", True)),
        )

        parts = [opening, ""]

        # Direction / market / timeframe context is optional. CoinCoach's default public
        # format keeps the caption cleaner and lets the official chart show the timeframe.
        if bool(caption_cfg.get("include_context_line", False)):
            direction = "Long" if signal.side == "LONG" else "Short"
            timeframe = _format_timeframe(signal.timeframe)
            market_context = _market_context(self.settings, signal.side)
            direction_label = (
                f"{direction} setup"
                if market_context.lower().startswith("spot")
                else direction
            )
            parts.append(f"{direction_label} | {market_context} | {timeframe}")

        parts.extend(signal_detail_lines)

        # Risk-note text is also opt-in. The default no longer appends "NFA. DYOR.".
        risk_note = str(caption_cfg.get("risk_note", "")).strip()
        if bool(caption_cfg.get("include_risk_note", False)) and risk_note:
            parts.extend(["", risk_note])

        parts.extend(["", _hashtag_line(signal, seed, caption_cfg.get("hashtags", {}))])
        return "\n".join(parts)
