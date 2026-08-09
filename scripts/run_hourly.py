from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.config import load_config
from app.cycle import run_cycle


def seconds_until_next_hour() -> float:
    now = datetime.now(timezone.utc)
    return max(1.0, 3600 - (now.minute * 60 + now.second + now.microsecond / 1_000_000))


async def main() -> None:
    while True:
        # Reload .env and account status every cycle. Adding a new key activates that
        # account on the next cycle without changing source code.
        config = load_config()
        await run_cycle(config)
        await asyncio.sleep(seconds_until_next_hour())


if __name__ == "__main__":
    asyncio.run(main())
