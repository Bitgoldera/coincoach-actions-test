from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .config import AccountConfig


class SquarePublishError(RuntimeError):
    pass


class SquarePublisher:
    """Adapter around Binance's official Square posting scripts."""

    def __init__(self, settings: dict) -> None:
        self.settings = settings

    def publish_image(self, account: AccountConfig, text: str, image_path: Path) -> str:
        if not self.settings["publishing"]["enabled"]:
            return "DRY_RUN: publishing disabled"
        skill_dir = Path(os.getenv(self.settings["publishing"]["official_skill_dir_env"], ""))
        script = skill_dir / "scripts" / "post-image.mjs"
        if not script.exists():
            raise SquarePublishError(f"Official post-image.mjs not found at {script}")
        key = os.getenv(account.key_env, "")
        if not key:
            raise SquarePublishError(f"Missing Square key in environment variable {account.key_env}")
        env = os.environ.copy()
        env["BINANCE_SQUARE_OPENAPI_KEY"] = key
        result = subprocess.run(
            ["node", str(script), "--text", text, "--images", str(image_path)],
            cwd=str(skill_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0:
            raise SquarePublishError(result.stderr.strip() or result.stdout.strip() or "Unknown Square publish error")
        return result.stdout.strip()
