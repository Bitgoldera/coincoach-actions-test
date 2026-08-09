from __future__ import annotations

import json
import os
from dataclasses import asdict
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import Signal


class Storage:
    def __init__(self, path: str | Path | None = None) -> None:
        path = path or os.getenv("DATABASE_PATH", "data/coincoach.db")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS signals (
                signal_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                account_id TEXT,
                timeframe TEXT NOT NULL,
                side TEXT NOT NULL,
                setup TEXT NOT NULL,
                score REAL NOT NULL,
                payload_json TEXT NOT NULL,
                caption TEXT,
                image_path TEXT,
                status TEXT NOT NULL DEFAULT 'generated',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS phrase_memory (
                phrase TEXT NOT NULL,
                account_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_signals_symbol_time ON signals(symbol, created_at);
            CREATE INDEX IF NOT EXISTS idx_phrase_memory_account_time ON phrase_memory(account_id, created_at);
            """
        )
        self.connection.commit()

    def symbol_in_cooldown(self, symbol: str, hours: int) -> bool:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        row = self.connection.execute(
            "SELECT 1 FROM signals WHERE symbol = ? AND created_at >= ? LIMIT 1", (symbol, cutoff)
        ).fetchone()
        return row is not None

    def recent_phrases(self, account_id: str, limit: int = 100) -> set[str]:
        rows = self.connection.execute(
            "SELECT phrase FROM phrase_memory WHERE account_id = ? ORDER BY created_at DESC LIMIT ?",
            (account_id, limit),
        ).fetchall()
        return {str(row["phrase"]) for row in rows}

    def remember_phrase(self, account_id: str, phrase: str) -> None:
        self.connection.execute(
            "INSERT INTO phrase_memory(phrase, account_id, created_at) VALUES (?, ?, ?)",
            (phrase, account_id, datetime.now(timezone.utc).isoformat()),
        )
        self.connection.commit()

    def save_signal(self, signal: Signal, account_id: str, caption: str, image_path: str | None, status: str) -> None:
        payload = json.dumps(asdict(signal), default=str)
        self.connection.execute(
            """
            INSERT OR REPLACE INTO signals(
                signal_id, symbol, account_id, timeframe, side, setup, score,
                payload_json, caption, image_path, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal.signal_id, signal.symbol, account_id, signal.timeframe, signal.side,
                signal.setup, signal.score, payload, caption, image_path, status,
                signal.created_at.isoformat(),
            ),
        )
        self.connection.commit()

    def close(self) -> None:
        connection = getattr(self, "connection", None)
        if connection is not None:
            connection.close()
            self.connection = None  # type: ignore[assignment]

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

