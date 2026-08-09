from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


@dataclass(slots=True)
class AccountConfig:
    id: str
    enabled: bool
    style: str
    key_env: str
    hourly_offset_minutes: int

    def has_key(self) -> bool:
        return bool(os.getenv(self.key_env, "").strip())


@dataclass(slots=True)
class AppConfig:
    root: Path
    settings: dict[str, Any]
    accounts: list[AccountConfig]
    account_activation_mode: str

    def active_accounts(self) -> list[AccountConfig]:
        """
        Resolve accounts at runtime.

        key_present (production default): an account is active only when it is enabled
        in YAML and its configured Square key environment variable is non-empty.

        enabled_only (preview/testing): every YAML-enabled account is active even when
        no publishing key has been supplied.
        """
        if self.account_activation_mode == "enabled_only":
            return [account for account in self.accounts if account.enabled]
        return [account for account in self.accounts if account.enabled and account.has_key()]

    def account_statuses(self) -> list[dict[str, Any]]:
        active_ids = {account.id for account in self.active_accounts()}
        statuses: list[dict[str, Any]] = []
        for account in self.accounts:
            if not account.enabled:
                state = "disabled"
            elif account.id in active_ids:
                state = "active"
            else:
                state = "waiting_for_key"
            statuses.append({
                "id": account.id,
                "style": account.style,
                "enabled_in_config": account.enabled,
                "key_env": account.key_env,
                "key_present": account.has_key(),
                "state": state,
            })
        return statuses


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


def load_config(root: Path | None = None) -> AppConfig:
    root = root or Path(__file__).resolve().parents[1]

    # override=True lets a mounted .env file be updated between hourly cycles.
    # The worker reloads this configuration each cycle.
    load_dotenv(root / ".env", override=True)

    settings = _read_yaml(root / "config" / "settings.yaml")
    accounts_path = root / "config" / "accounts.yaml"
    if not accounts_path.exists():
        accounts_path = root / "config" / "accounts.example.yaml"
    accounts_raw = _read_yaml(accounts_path).get("accounts", [])
    accounts = [AccountConfig(**item) for item in accounts_raw]

    # Environment flags override YAML for safe deployment toggles.
    settings.setdefault("publishing", {})["enabled"] = (
        os.getenv("PUBLISH_ENABLED", str(settings.get("publishing", {}).get("enabled", False))).lower() == "true"
    )
    settings.setdefault("capture", {})["enabled"] = (
        os.getenv("MOBILE_CAPTURE_ENABLED", str(settings.get("capture", {}).get("enabled", False))).lower() == "true"
    )
    settings.setdefault("capture", {})["web_enabled"] = (
        os.getenv("WEB_CAPTURE_ENABLED", str(settings.get("capture", {}).get("web_enabled", False))).lower() == "true"
    )
    settings.setdefault("capture", {})["rendered_enabled"] = (
        os.getenv("RENDERED_CHART_ENABLED", str(settings.get("capture", {}).get("rendered_enabled", False))).lower() == "true"
    )

    activation_mode = os.getenv("ACCOUNT_ACTIVATION_MODE", "key_present").strip().lower()
    if activation_mode not in {"key_present", "enabled_only"}:
        raise ValueError("ACCOUNT_ACTIVATION_MODE must be 'key_present' or 'enabled_only'")

    return AppConfig(
        root=root,
        settings=settings,
        accounts=accounts,
        account_activation_mode=activation_mode,
    )
