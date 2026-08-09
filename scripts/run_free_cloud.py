from __future__ import annotations

import asyncio
import json
import os
import re
import math
from collections import Counter, defaultdict
from pathlib import Path

from app.config import load_config
from app.cycle import run_cycle
from app.official_web_chart import OfficialBinanceWebChartCapture
from app.web_capture import WebCaptureError


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


_REQUIRED_LEVEL_LABELS = ("Entry:", "TP1:", "TP2:", "TP3:", "Stop Loss:")
_REMOVED_PUBLIC_LINES = ("NFA. DYOR.", "| Spot chart |", "| Futures |")


def clean_caption_format_valid(posts: list[dict]) -> bool:
    """Validate the user-approved clean caption format.

    Timeframe/market context and NFA/DYOR were intentionally removed from public
    captions. The validator now requires only the exact trade-level labels and rejects
    the removed legacy lines if an old caption template slips back in.
    """

    return all(
        all(token in str(post.get("caption", "")) for token in _REQUIRED_LEVEL_LABELS)
        and all(token not in str(post.get("caption", "")) for token in _REMOVED_PUBLIC_LINES)
        for post in posts
    )


def configure_preview_capture_safety(settings: dict) -> dict[str, bool | int | float]:
    """Use the proven non-destructive capture policy for a five-image preview.

    Preview runs are not publications, so old dry-run memory must not starve the next
    batch. The preview therefore ignores symbol cooldown, preserves the verified chart
    capture policy, and uses bounded retries plus reserve symbols for transient Binance page failures.
    """

    web = settings["capture"]["web"]
    web["allow_ma_overlay_for_capture_proof"] = True
    web["require_ma_overlay_removed"] = False
    web["skip_indicator_cleanup_for_proof"] = True
    web["require_network_timeframe_confirmation"] = False
    web["non_blocking_dialog_recovery_for_proof"] = True
    # The capture class already has its own internal retries. Two outer attempts are
    # enough; reserve symbols are faster and more reliable than retrying one bad page
    # six times while the whole five-post batch waits.
    web["preview_outer_capture_attempts"] = 2
    web["preview_retry_delay_seconds"] = max(
        0.0, float(web.get("preview_retry_delay_seconds", 2.0))
    )

    # GitHub restores preview memory between runs. That memory is useful for live posting,
    # but it can remove otherwise valid symbols from a manual five-post proof. A preview
    # must test the current market and capture pipeline, not be limited by earlier previews.
    settings.setdefault("signals", {})["symbol_cooldown_hours"] = 0

    return {
        "allow_ma_overlay_for_capture_proof": True,
        "require_ma_overlay_removed": False,
        "skip_indicator_cleanup_for_proof": True,
        "require_network_timeframe_confirmation": False,
        "non_blocking_dialog_recovery_for_proof": True,
        "preview_outer_capture_attempts": web["preview_outer_capture_attempts"],
        "preview_retry_delay_seconds": web["preview_retry_delay_seconds"],
    }


def configure_preview_candidate_reserve(
    settings: dict,
    *,
    reserve_per_account: int = 4,
) -> dict[str, int]:
    """Temporarily request extra routed posts so a failed chart can be replaced.

    The final public preview still contains the configured five posts per account.
    Extra posts exist only as reserve candidates and are discarded after five valid
    official Binance screenshots have been selected.
    """

    schedule = settings["schedule"]
    target_per_account = max(1, int(schedule["signals_per_account_per_hour"]))
    original_max_per_timeframe = max(0, int(schedule.get("max_signals_per_timeframe_per_account", 0)))
    timeframe_count = max(1, len(settings.get("market", {}).get("timeframes", [])))
    candidate_per_account = target_per_account + max(1, int(reserve_per_account))
    candidate_max_per_timeframe = max(
        original_max_per_timeframe,
        int(math.ceil(candidate_per_account / timeframe_count)),
    )

    schedule["signals_per_account_per_hour"] = candidate_per_account
    schedule["max_signals_per_timeframe_per_account"] = candidate_max_per_timeframe

    return {
        "target_per_account": target_per_account,
        "candidate_per_account": candidate_per_account,
        "final_max_per_timeframe": original_max_per_timeframe,
        "candidate_max_per_timeframe": candidate_max_per_timeframe,
    }


def candidate_slot_available(
    *,
    account_id: str,
    timeframe: str,
    selected_by_account: dict[str, int],
    selected_timeframes: dict[str, Counter[str]],
    target_per_account: int,
    max_per_timeframe: int,
) -> bool:
    """Return whether a reserve candidate can still enter the final preview."""

    if selected_by_account.get(account_id, 0) >= target_per_account:
        return False
    if max_per_timeframe > 0 and selected_timeframes[account_id][timeframe] >= max_per_timeframe:
        return False
    return True


async def capture_with_preview_retry(
    capture: OfficialBinanceWebChartCapture,
    symbol: str,
    timeframe: str,
    output_path: Path,
    *,
    outer_attempts: int,
    retry_delay_seconds: float,
) -> int:
    """Capture one chart, retrying only after the capture class exhausts its own attempts.

    Returns the successful outer-attempt number. The final exception is preserved so the
    artifact still contains the latest diagnostic screenshot and capture report.
    """

    attempts = max(1, int(outer_attempts))
    last_error: WebCaptureError | None = None
    diagnostic_path = output_path.with_name(output_path.stem + "_diagnostic.png")
    page_text_path = output_path.with_name(output_path.stem + "_page_text.txt")
    report_path = output_path.with_suffix(".capture.json")

    for attempt in range(1, attempts + 1):
        # Remove stale files from the previous outer attempt so a later success is not
        # counted together with an old diagnostic artifact.
        for stale_path in (output_path, diagnostic_path, page_text_path, report_path):
            stale_path.unlink(missing_ok=True)
        try:
            await capture.capture(symbol, timeframe, output_path)
            diagnostic_path.unlink(missing_ok=True)
            page_text_path.unlink(missing_ok=True)
            return attempt
        except WebCaptureError as exc:
            last_error = exc
            if attempt >= attempts:
                break
            await asyncio.sleep(max(0.0, float(retry_delay_seconds)))
    assert last_error is not None
    raise last_error


async def main() -> None:
    root = Path(__file__).resolve().parents[1]
    config = load_config(root)
    capture_policy = configure_preview_capture_safety(config.settings)
    candidate_plan = configure_preview_candidate_reserve(config.settings)

    try:
        preview = await run_cycle(config)
    finally:
        # Restore the public quota before validation/reporting. Reserve candidates are
        # an internal preview reliability mechanism, not extra public posts.
        config.settings["schedule"]["signals_per_account_per_hour"] = candidate_plan["target_per_account"]
        config.settings["schedule"]["max_signals_per_timeframe_per_account"] = candidate_plan["final_max_per_timeframe"]

    candidate_posts = list(preview.get("posts", []))
    active_accounts = max(0, int(preview.get("active_account_count", 0)))
    expected_posts = candidate_plan["target_per_account"] * active_accounts

    web_capture = OfficialBinanceWebChartCapture(root, config.settings)
    capture_errors: list[dict[str, str]] = []
    selected_posts: list[dict] = []
    selected_by_account: dict[str, int] = defaultdict(int)
    selected_timeframes: dict[str, Counter[str]] = defaultdict(Counter)
    considered_candidates = 0
    skipped_by_final_cap = 0

    for post in candidate_posts:
        account_id = str(post["account_id"])
        signal = post["signal"]
        timeframe = str(signal["timeframe"]).lower()

        if not candidate_slot_available(
            account_id=account_id,
            timeframe=timeframe,
            selected_by_account=selected_by_account,
            selected_timeframes=selected_timeframes,
            target_per_account=candidate_plan["target_per_account"],
            max_per_timeframe=candidate_plan["final_max_per_timeframe"],
        ):
            skipped_by_final_cap += 1
            continue

        considered_candidates += 1
        final_index = len(selected_posts) + 1
        filename = safe_name(f"{final_index:02d}_{signal['symbol']}_{signal['timeframe']}.png")
        output_path = root / "output" / "charts" / filename

        try:
            outer_attempt = await capture_with_preview_retry(
                web_capture,
                signal["symbol"],
                signal["timeframe"],
                output_path,
                outer_attempts=int(capture_policy["preview_outer_capture_attempts"]),
                retry_delay_seconds=float(capture_policy["preview_retry_delay_seconds"]),
            )
            post["image_path"] = str(output_path.relative_to(root)).replace("\\", "/")
            post["image_status"] = "official_binance_mobile_web_live_verified"
            post["capture_outer_attempt"] = outer_attempt
            report_path = output_path.with_suffix(".capture.json")
            if report_path.exists():
                post["capture_report"] = str(report_path.relative_to(root)).replace("\\", "/")
            selected_posts.append(post)
            selected_by_account[account_id] += 1
            selected_timeframes[account_id][timeframe] += 1
        except WebCaptureError as exc:
            diagnostic_path = output_path.with_name(output_path.stem + "_diagnostic.png")
            page_text_path = output_path.with_name(output_path.stem + "_page_text.txt")
            report_path = output_path.with_suffix(".capture.json")
            capture_errors.append({
                "symbol": signal["symbol"],
                "timeframe": signal["timeframe"],
                "error": str(exc),
            })
            # This candidate is being replaced by the next reserve candidate. Keep the
            # error in JSON, but do not clutter a successful five-post artifact with a
            # rejected diagnostic image or stale final-slot filename.
            for rejected_path in (output_path, diagnostic_path, page_text_path, report_path):
                rejected_path.unlink(missing_ok=True)

        if expected_posts > 0 and len(selected_posts) >= expected_posts:
            break

    posts = selected_posts
    preview["posts"] = posts
    preview["candidate_posts_generated"] = len(candidate_posts)
    preview["reserve_candidates_considered"] = considered_candidates
    preview["reserve_capture_failures"] = len(capture_errors)
    preview["reserve_candidates_skipped_by_final_cap"] = skipped_by_final_cap
    preview["candidate_plan"] = candidate_plan

    preview["capture_provider"] = "official_binance_mobile_web_live_verified"
    preview["capture_policy"] = capture_policy
    preview["capture_errors"] = capture_errors
    preview["publishing_attempted"] = False
    preview["warning"] = (
        "Images are screenshots of Binance's official mobile Spot web chart. "
        "Each accepted image must match the signal symbol, exact timeframe and fresh Binance price. "
        "They are not custom-rendered charts. Publishing remains disabled in this preview."
    )

    preview_dir = root / "output" / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    (preview_dir / "latest_cycle.json").write_text(json.dumps(preview, indent=2, default=str), encoding="utf-8")

    public_posts: list[str] = []
    for post in posts:
        public_posts.append(post["caption"])
        public_posts.append(
            f"IMAGE: {post.get('image_path') or post.get('diagnostic_path') or post.get('image_status', 'none')}"
        )
        public_posts.append("=" * 72)
    (preview_dir / "public_posts.txt").write_text("\n\n".join(public_posts), encoding="utf-8")

    valid_images = sum(1 for post in posts if post.get("image_path"))
    diagnostic_images = sum(1 for post in posts if post.get("diagnostic_path"))
    timeframe_distribution = Counter(post["signal"]["timeframe"] for post in posts)
    max_per_timeframe = int(
        config.settings["schedule"].get("max_signals_per_timeframe_per_account", 0)
    )
    configured_timeframes = {
        str(value).lower() for value in config.settings["market"].get("timeframes", [])
    }
    required_distinct_timeframes = min(3, len(configured_timeframes), expected_posts)
    timeframe_cap_valid = (
        max_per_timeframe <= 0
        or all(count <= max_per_timeframe for count in timeframe_distribution.values())
    )
    timeframe_diversity_valid = (
        timeframe_cap_valid
        and len(timeframe_distribution) >= required_distinct_timeframes
    )
    caption_format_valid = clean_caption_format_valid(posts)
    preview["timeframe_distribution"] = dict(sorted(timeframe_distribution.items()))
    preview["preview_signal_cooldown_hours"] = int(
        config.settings["signals"].get("symbol_cooldown_hours", 0)
    )
    preview["required_distinct_timeframes"] = required_distinct_timeframes
    preview["timeframe_diversity_valid"] = timeframe_diversity_valid
    preview["caption_format_valid"] = caption_format_valid
    preview["valid_images"] = valid_images
    preview["diagnostic_images"] = diagnostic_images
    preview["image_failures"] = max(0, expected_posts - valid_images)
    preview["reserve_capture_failures"] = len(capture_errors)
    preview["expected_posts"] = expected_posts
    (preview_dir / "latest_cycle.json").write_text(
        json.dumps(preview, indent=2, default=str), encoding="utf-8"
    )
    summary = [
        "# CoinCoach official Binance mobile-web live preview",
        "",
        f"- Active accounts: {preview.get('active_account_count', 0)}",
        f"- Generated posts: {len(posts)}",
        f"- Valid official Binance images: {valid_images}",
        f"- Rejected/diagnostic images: {diagnostic_images}",
        f"- Final image shortages: {max(0, expected_posts - valid_images)}",
        f"- Reserve candidate capture failures replaced: {len(capture_errors)}",
        f"- Candidate posts generated: {len(candidate_posts)}",
        f"- Reserve candidates considered: {considered_candidates}",
        f"- Expected posts: {expected_posts}",
        f"- Timeframe distribution: {dict(sorted(timeframe_distribution.items()))}",
        f"- Required distinct timeframes: {required_distinct_timeframes}",
        f"- Timeframe diversity valid: {timeframe_diversity_valid}",
        "- Preview symbol cooldown: disabled",
        f"- Clean caption format valid: {caption_format_valid}",
        "- Image provider: official_binance_mobile_web_live_verified",
        "- Publishing attempted: no",
        "",
        "## Public captions",
    ]
    for post in posts:
        image_label = post.get("image_path") or post.get("diagnostic_path") or "image failed"
        summary.extend(["", "```text", post["caption"], "```", f"Image: `{image_label}`"])
    summary_path = preview_dir / "github_summary.md"
    summary_path.write_text("\n".join(summary), encoding="utf-8")

    github_summary = os.getenv("GITHUB_STEP_SUMMARY")
    if github_summary:
        Path(github_summary).write_text(summary_path.read_text(encoding="utf-8"), encoding="utf-8")

    print(json.dumps({
        "active_accounts": preview.get("active_account_count", 0),
        "posts": len(posts),
        "valid_images": valid_images,
        "diagnostic_images": diagnostic_images,
        "image_failures": max(0, expected_posts - valid_images),
        "reserve_capture_failures": len(capture_errors),
        "candidate_posts_generated": len(candidate_posts),
        "reserve_candidates_considered": considered_candidates,
        "expected_posts": expected_posts,
        "timeframe_distribution": dict(sorted(timeframe_distribution.items())),
        "required_distinct_timeframes": required_distinct_timeframes,
        "timeframe_diversity_valid": timeframe_diversity_valid,
        "preview_signal_cooldown_hours": int(
            config.settings["signals"].get("symbol_cooldown_hours", 0)
        ),
        "caption_format_valid": caption_format_valid,
        "image_provider": "official_binance_mobile_web_live_verified",
        "capture_policy": capture_policy,
        "publishing_attempted": False,
        "artifact": "output/",
    }, indent=2))

    failures: list[str] = []
    if len(posts) != expected_posts:
        failures.append(f"generated {len(posts)}/{expected_posts} required posts")
    if not timeframe_diversity_valid:
        failures.append(
            f"timeframe cap exceeded: {dict(sorted(timeframe_distribution.items()))}"
        )
    if not caption_format_valid:
        failures.append(
            "one or more captions contain removed context/risk lines or are missing trade levels"
        )
    if valid_images != len(posts):
        failures.append(f"only {valid_images}/{len(posts)} chart images passed validation")
    if failures:
        raise SystemExit("; ".join(failures) + ". Publishing remains blocked.")


if __name__ == "__main__":
    asyncio.run(main())
