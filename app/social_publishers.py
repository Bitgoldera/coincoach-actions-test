from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

import httpx


class SocialPublishError(RuntimeError):
    """Raised for one social destination without affecting Square publishing."""


@dataclass(frozen=True, slots=True)
class SocialPlatformConfig:
    account_id: str
    syndication_enabled: bool
    live_approved: bool
    discord_enabled: bool
    facebook_enabled: bool
    instagram_enabled: bool
    threads_enabled: bool
    request_timeout_seconds: float
    pending_retry_limit: int
    state_path: Path

    @property
    def enabled_platforms(self) -> tuple[str, ...]:
        enabled: list[str] = []
        if self.discord_enabled:
            enabled.append("discord")
        if self.facebook_enabled:
            enabled.append("facebook")
        if self.instagram_enabled:
            enabled.append("instagram")
        if self.threads_enabled:
            enabled.append("threads")
        return tuple(enabled)


def _truthy(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _safe_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _safe_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _has_credentials(*names: str) -> bool:
    return all(bool(os.getenv(name, "").strip()) for name in names)


def load_social_config(root: Path, account_id: str) -> SocialPlatformConfig:
    """Load social destinations for this account only.

    A social destination is considered connected only when its explicit enable
    switch is true *and* all credentials required by that destination are
    present. This lets one shared codebase run Binance-only for accounts with
    no social credentials, while automatically syndicating the confirmed
    Square post for accounts that have connected destinations.
    """
    state_value = os.getenv("SOCIAL_STATE_PATH", "").strip()
    if state_value:
        state_path = Path(state_value)
        if not state_path.is_absolute():
            state_path = root / state_path
    else:
        state_path = root / "data" / "state" / account_id / "social_delivery_state.json"

    discord_enabled = _truthy("DISCORD_PUBLISH_ENABLED") and _has_credentials(
        "DISCORD_WEBHOOK_URL"
    )
    meta_ready = _has_credentials(
        "CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET",
        "META_GRAPH_API_VERSION",
    )
    facebook_enabled = _truthy("FACEBOOK_PUBLISH_ENABLED") and meta_ready and _has_credentials(
        "FACEBOOK_PAGE_ID", "FACEBOOK_PAGE_ACCESS_TOKEN"
    )
    instagram_enabled = _truthy("INSTAGRAM_PUBLISH_ENABLED") and meta_ready and _has_credentials(
        "INSTAGRAM_USER_ID", "INSTAGRAM_ACCESS_TOKEN"
    )
    threads_enabled = _truthy("THREADS_PUBLISH_ENABLED") and _has_credentials(
        "THREADS_USER_ID", "THREADS_ACCESS_TOKEN",
        "CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET",
    )

    return SocialPlatformConfig(
        account_id=account_id,
        syndication_enabled=_truthy("SOCIAL_SYNDICATION_ENABLED"),
        live_approved=_truthy("SOCIAL_LIVE_APPROVED"),
        discord_enabled=discord_enabled,
        facebook_enabled=facebook_enabled,
        instagram_enabled=instagram_enabled,
        threads_enabled=threads_enabled,
        request_timeout_seconds=_safe_float(
            "SOCIAL_REQUEST_TIMEOUT_SECONDS", 45.0, 5.0, 180.0
        ),
        pending_retry_limit=_safe_int("SOCIAL_PENDING_RETRY_LIMIT", 1, 0, 10),
        state_path=state_path,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_error(exc: Exception) -> str:
    text = str(exc).replace("\r", " ").replace("\n", " ").strip()
    return text[:600] or exc.__class__.__name__


def _redact_url(raw_url: str) -> str:
    try:
        parts = urlsplit(raw_url)
        return urlunsplit((parts.scheme, parts.netloc, "/***", "", ""))
    except Exception:
        return "***"


class SocialStateStore:
    """Small persistent outbox stored inside the existing per-account cache."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.media_dir = path.parent / "social_pending_media"

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "deliveries": {}}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": 1, "deliveries": {}}
        if not isinstance(value, dict):
            return {"version": 1, "deliveries": {}}
        value.setdefault("version", 1)
        value.setdefault("deliveries", {})
        if not isinstance(value["deliveries"], dict):
            value["deliveries"] = {}
        return value

    def save(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def retain_image(self, delivery_id: str, image_path: Path) -> Path:
        self.media_dir.mkdir(parents=True, exist_ok=True)
        suffix = image_path.suffix.lower() or ".png"
        retained = self.media_dir / f"{delivery_id}{suffix}"
        if image_path.resolve() != retained.resolve():
            shutil.copy2(image_path, retained)
        return retained

    def delete_retained_image(self, value: str | None) -> None:
        if not value:
            return
        try:
            Path(value).unlink(missing_ok=True)
        except OSError:
            return

    def prune(self, state: dict[str, Any], keep_days: int = 7) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
        deliveries = state.get("deliveries", {})
        for delivery_id, item in list(deliveries.items()):
            if item.get("status") != "complete":
                continue
            completed_at = item.get("completed_at")
            try:
                completed = datetime.fromisoformat(str(completed_at))
            except (TypeError, ValueError):
                completed = cutoff - timedelta(seconds=1)
            if completed < cutoff:
                self.delete_retained_image(item.get("retained_image_path"))
                deliveries.pop(delivery_id, None)


class CloudinaryImageHost:
    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def upload(self, image_path: Path, delivery_id: str) -> str:
        cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "").strip()
        api_key = os.getenv("CLOUDINARY_API_KEY", "").strip()
        api_secret = os.getenv("CLOUDINARY_API_SECRET", "").strip()
        if not cloud_name or not api_key or not api_secret:
            raise SocialPublishError(
                "Meta destinations require CLOUDINARY_CLOUD_NAME, "
                "CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET"
            )

        timestamp = int(time.time())
        folder = os.getenv("CLOUDINARY_FOLDER", "coincoach-signals").strip()
        public_id = f"signal_{delivery_id}"
        signed_parameters = {
            "folder": folder,
            "overwrite": "true",
            "public_id": public_id,
            "timestamp": str(timestamp),
        }
        signature_base = "&".join(
            f"{key}={signed_parameters[key]}" for key in sorted(signed_parameters)
        )
        signature = hashlib.sha1(
            f"{signature_base}{api_secret}".encode("utf-8")
        ).hexdigest()
        endpoint = f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload"

        with image_path.open("rb") as handle:
            response = self.client.post(
                endpoint,
                data={
                    **signed_parameters,
                    "api_key": api_key,
                    "signature": signature,
                },
                files={"file": (image_path.name, handle, "image/png")},
            )
        self._raise_for_status(response, "Cloudinary image upload")
        payload = response.json()
        secure_url = str(payload.get("secure_url", "")).strip()
        if not secure_url:
            raise SocialPublishError("Cloudinary response did not include secure_url")
        return secure_url

    @staticmethod
    def _raise_for_status(response: httpx.Response, action: str) -> None:
        if response.is_success:
            return
        detail = response.text[:300].replace("\n", " ")
        raise SocialPublishError(f"{action} failed ({response.status_code}): {detail}")


class SocialSyndicator:
    """Fan out one confirmed Square post for the active account.

    Binance Square remains the source of truth: this class is called only after
    a Square publish succeeds, and any social failure is isolated from that
    already-confirmed Square result.
    """

    def __init__(
        self,
        root: Path,
        account_id: str,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.root = root
        self.account_id = account_id
        self.config = load_social_config(root, account_id)
        self._owns_client = client is None
        self.client = client or httpx.Client(
            timeout=self.config.request_timeout_seconds,
            follow_redirects=True,
        )
        self.store = SocialStateStore(self.config.state_path)
        self.image_host = CloudinaryImageHost(self.client)

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> "SocialSyndicator":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def publish_after_square(
        self,
        *,
        caption: str,
        image_path: Path,
        signal: dict[str, Any],
    ) -> dict[str, Any]:
        report: dict[str, Any] = {
            "source_account_id": self.account_id,
            "enabled": self.config.syndication_enabled,
            "approved": self.config.live_approved,
            "enabled_platforms": list(self.config.enabled_platforms),
            "status": "not_run",
            "deliveries": [],
        }

        if not self.config.syndication_enabled:
            report["status"] = "disabled"
            return report
        if not self.config.live_approved:
            report["status"] = "blocked_missing_social_approval"
            return report
        if not self.config.enabled_platforms:
            report["status"] = "disabled_no_platforms"
            return report
        if not image_path.exists():
            report["status"] = "failed_missing_image"
            report["error"] = f"Image does not exist: {image_path}"
            return report

        state = self.store.load()
        self.store.prune(state)
        delivery = self._ensure_delivery(state, caption, image_path, signal)
        report["deliveries"].append(self._deliver(state, delivery))

        retried = 0
        for pending in self._pending_deliveries(state, exclude_id=delivery["id"]):
            if retried >= self.config.pending_retry_limit:
                break
            report["deliveries"].append(self._deliver(state, pending))
            retried += 1

        self.store.save(state)
        current = state["deliveries"][delivery["id"]]
        report["status"] = (
            "complete" if current.get("status") == "complete" else "partial_failure"
        )
        report["delivery_id"] = delivery["id"]
        report["retried_pending_deliveries"] = retried
        return report

    def _ensure_delivery(
        self,
        state: dict[str, Any],
        caption: str,
        image_path: Path,
        signal: dict[str, Any],
    ) -> dict[str, Any]:
        hasher = hashlib.sha256()
        hasher.update(self.account_id.encode("utf-8"))
        hasher.update(caption.encode("utf-8"))
        with image_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        delivery_id = hasher.hexdigest()[:24]
        deliveries = state.setdefault("deliveries", {})
        existing = deliveries.get(delivery_id)
        if isinstance(existing, dict):
            return existing

        retained = self.store.retain_image(delivery_id, image_path)
        platforms = {
            platform: {
                "status": "pending",
                "attempts": 0,
                "last_error": None,
                "remote_id": None,
            }
            for platform in self.config.enabled_platforms
        }
        delivery = {
            "id": delivery_id,
            "source_account_id": self.account_id,
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
            "completed_at": None,
            "status": "pending",
            "caption": caption,
            "signal": {
                "symbol": signal.get("symbol"),
                "timeframe": signal.get("timeframe"),
                "direction": signal.get("direction"),
            },
            "retained_image_path": str(retained),
            "public_image_url": None,
            "platforms": platforms,
        }
        deliveries[delivery_id] = delivery
        self.store.save(state)
        return delivery

    def _pending_deliveries(
        self, state: dict[str, Any], *, exclude_id: str
    ) -> Iterable[dict[str, Any]]:
        items = [
            item
            for delivery_id, item in state.get("deliveries", {}).items()
            if delivery_id != exclude_id and item.get("status") != "complete"
        ]
        return sorted(items, key=lambda item: str(item.get("created_at", "")))

    def _deliver(self, state: dict[str, Any], delivery: dict[str, Any]) -> dict[str, Any]:
        retained = Path(str(delivery.get("retained_image_path", "")))
        summary: dict[str, Any] = {
            "delivery_id": delivery["id"],
            "platforms": {},
        }

        for platform in self.config.enabled_platforms:
            platform_state = delivery.setdefault("platforms", {}).setdefault(
                platform,
                {"status": "pending", "attempts": 0, "last_error": None, "remote_id": None},
            )
            if platform_state.get("status") == "published":
                summary["platforms"][platform] = dict(platform_state)
                continue

            platform_state["attempts"] = int(platform_state.get("attempts", 0)) + 1
            platform_state["last_attempt_at"] = _utc_now()
            try:
                remote_id = self._publish_platform(platform, delivery, retained)
            except Exception as exc:  # isolated by destination on purpose
                platform_state["status"] = "failed"
                platform_state["last_error"] = _safe_error(exc)
            else:
                platform_state["status"] = "published"
                platform_state["last_error"] = None
                platform_state["remote_id"] = remote_id
                platform_state["published_at"] = _utc_now()
            delivery["updated_at"] = _utc_now()
            self.store.save(state)
            summary["platforms"][platform] = dict(platform_state)

        relevant_states = [
            delivery.get("platforms", {}).get(platform, {}).get("status")
            for platform in self.config.enabled_platforms
        ]
        if relevant_states and all(value == "published" for value in relevant_states):
            delivery["status"] = "complete"
            delivery["completed_at"] = _utc_now()
            self.store.delete_retained_image(delivery.get("retained_image_path"))
            delivery["retained_image_path"] = None
        else:
            delivery["status"] = "pending_retry"
        delivery["updated_at"] = _utc_now()
        self.store.save(state)
        summary["status"] = delivery["status"]
        return summary

    def _publish_platform(
        self, platform: str, delivery: dict[str, Any], retained: Path
    ) -> str:
        if platform == "discord":
            return self._publish_discord(delivery["caption"], retained)

        image_url = str(delivery.get("public_image_url") or "").strip()
        if not image_url:
            image_url = self.image_host.upload(retained, delivery["id"])
            delivery["public_image_url"] = image_url

        if platform == "facebook":
            return self._publish_facebook(delivery["caption"], image_url)
        if platform == "instagram":
            return self._publish_instagram(delivery["caption"], image_url)
        if platform == "threads":
            return self._publish_threads(delivery["caption"], image_url)
        raise SocialPublishError(f"Unsupported social platform: {platform}")

    def _publish_discord(self, caption: str, image_path: Path) -> str:
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
        if not webhook_url:
            raise SocialPublishError("Missing DISCORD_WEBHOOK_URL")
        separator = "&" if "?" in webhook_url else "?"
        endpoint = f"{webhook_url}{separator}wait=true"
        payload = {
            "content": caption[:2000],
            "allowed_mentions": {"parse": []},
        }
        with image_path.open("rb") as handle:
            response = self.client.post(
                endpoint,
                data={"payload_json": json.dumps(payload)},
                files={"files[0]": (image_path.name, handle, "image/png")},
            )
        self._raise_for_status(response, "Discord webhook", secret_url=webhook_url)
        body = response.json() if response.content else {}
        return str(body.get("id", "published"))

    def _meta_endpoint(self, object_path: str) -> str:
        base = os.getenv("META_GRAPH_BASE_URL", "https://graph.facebook.com").rstrip("/")
        version = os.getenv("META_GRAPH_API_VERSION", "").strip().strip("/")
        if not version:
            raise SocialPublishError("Missing META_GRAPH_API_VERSION repository variable")
        return f"{base}/{version}/{object_path.lstrip('/')}"

    def _publish_facebook(self, caption: str, image_url: str) -> str:
        page_id = os.getenv("FACEBOOK_PAGE_ID", "").strip()
        access_token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "").strip()
        if not page_id or not access_token:
            raise SocialPublishError(
                "Missing FACEBOOK_PAGE_ID or FACEBOOK_PAGE_ACCESS_TOKEN"
            )
        response = self.client.post(
            self._meta_endpoint(f"{page_id}/photos"),
            data={
                "url": image_url,
                "message": caption,
                "published": "true",
                "access_token": access_token,
            },
        )
        self._raise_for_status(response, "Facebook Page photo publish")
        payload = response.json()
        return str(payload.get("post_id") or payload.get("id") or "published")

    def _publish_instagram(self, caption: str, image_url: str) -> str:
        user_id = os.getenv("INSTAGRAM_USER_ID", "").strip()
        access_token = (
            os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip()
            or os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "").strip()
        )
        if not user_id or not access_token:
            raise SocialPublishError(
                "Missing INSTAGRAM_USER_ID or INSTAGRAM_ACCESS_TOKEN"
            )
        create = self.client.post(
            self._meta_endpoint(f"{user_id}/media"),
            data={
                "image_url": image_url,
                "caption": caption[:2200],
                "access_token": access_token,
            },
        )
        self._raise_for_status(create, "Instagram media container creation")
        container_id = str(create.json().get("id", "")).strip()
        if not container_id:
            raise SocialPublishError("Instagram did not return a media container id")
        self._wait_for_meta_container(container_id, access_token, "Instagram")
        publish = self.client.post(
            self._meta_endpoint(f"{user_id}/media_publish"),
            data={"creation_id": container_id, "access_token": access_token},
        )
        self._raise_for_status(publish, "Instagram media publish")
        return str(publish.json().get("id") or "published")

    def _threads_endpoint(self, object_path: str) -> str:
        base = os.getenv(
            "THREADS_API_BASE_URL", "https://graph.threads.net/v1.0"
        ).rstrip("/")
        return f"{base}/{object_path.lstrip('/')}"

    def _publish_threads(self, caption: str, image_url: str) -> str:
        user_id = os.getenv("THREADS_USER_ID", "").strip()
        access_token = os.getenv("THREADS_ACCESS_TOKEN", "").strip()
        if not user_id or not access_token:
            raise SocialPublishError("Missing THREADS_USER_ID or THREADS_ACCESS_TOKEN")
        create = self.client.post(
            self._threads_endpoint(f"{user_id}/threads"),
            data={
                "media_type": "IMAGE",
                "image_url": image_url,
                "text": caption[:500],
                "access_token": access_token,
            },
        )
        self._raise_for_status(create, "Threads media container creation")
        container_id = str(create.json().get("id", "")).strip()
        if not container_id:
            raise SocialPublishError("Threads did not return a media container id")
        self._wait_for_threads_container(container_id, access_token)
        publish = self.client.post(
            self._threads_endpoint(f"{user_id}/threads_publish"),
            data={"creation_id": container_id, "access_token": access_token},
        )
        self._raise_for_status(publish, "Threads publish")
        return str(publish.json().get("id") or "published")

    def _wait_for_meta_container(
        self, container_id: str, access_token: str, platform: str
    ) -> None:
        attempts = _safe_int("META_CONTAINER_STATUS_ATTEMPTS", 10, 1, 30)
        delay = _safe_float("META_CONTAINER_STATUS_DELAY_SECONDS", 2.0, 0.0, 15.0)
        for attempt in range(attempts):
            response = self.client.get(
                self._meta_endpoint(container_id),
                params={"fields": "status_code,status", "access_token": access_token},
            )
            self._raise_for_status(response, f"{platform} container status")
            payload = response.json()
            status = str(payload.get("status_code") or payload.get("status") or "").upper()
            if status in {"FINISHED", "PUBLISHED"}:
                return
            if status in {"ERROR", "EXPIRED"}:
                raise SocialPublishError(f"{platform} container entered status {status}")
            if attempt + 1 < attempts:
                time.sleep(delay)
        raise SocialPublishError(f"{platform} container was not ready before timeout")

    def _wait_for_threads_container(self, container_id: str, access_token: str) -> None:
        attempts = _safe_int("THREADS_CONTAINER_STATUS_ATTEMPTS", 10, 1, 30)
        delay = _safe_float("THREADS_CONTAINER_STATUS_DELAY_SECONDS", 2.0, 0.0, 15.0)
        for attempt in range(attempts):
            response = self.client.get(
                self._threads_endpoint(container_id),
                params={"fields": "status,error_message", "access_token": access_token},
            )
            self._raise_for_status(response, "Threads container status")
            payload = response.json()
            status = str(payload.get("status") or "").upper()
            if status in {"FINISHED", "PUBLISHED"}:
                return
            if status in {"ERROR", "EXPIRED"}:
                detail = str(payload.get("error_message") or status)
                raise SocialPublishError(f"Threads container failed: {detail}")
            if attempt + 1 < attempts:
                time.sleep(delay)
        raise SocialPublishError("Threads container was not ready before timeout")

    @staticmethod
    def _raise_for_status(
        response: httpx.Response,
        action: str,
        *,
        secret_url: str | None = None,
    ) -> None:
        if response.is_success:
            return
        detail = response.text[:300].replace("\n", " ")
        if secret_url:
            detail = detail.replace(secret_url, _redact_url(secret_url))
        raise SocialPublishError(f"{action} failed ({response.status_code}): {detail}")
