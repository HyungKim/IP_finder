"""라벨 캐시 (SQLite). 키는 해시, 값은 라벨 배열. 원문 텍스트는 저장하지 않는다."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path


class LabelCache:
    def __init__(self, path: Path | None):
        self.path = path
        self._mem: dict[str, list[str]] = {}
        self._conn: sqlite3.Connection | None = None
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(path))
            self._conn.execute("CREATE TABLE IF NOT EXISTS labels (key TEXT PRIMARY KEY, labels TEXT NOT NULL, created TEXT NOT NULL)")
            self._conn.commit()

    @staticmethod
    def key(model: str, prompt_version: str, user_text: str) -> str:
        return hashlib.sha256(f"{model}\n{prompt_version}\n{user_text}".encode("utf-8")).hexdigest()

    def get(self, key: str) -> list[str] | None:
        if self._conn is None:
            return self._mem.get(key)
        row = self._conn.execute("SELECT labels FROM labels WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def set(self, key: str, labels: list[str]) -> None:
        if self._conn is None:
            self._mem[key] = list(labels)
            return
        self._conn.execute("INSERT OR REPLACE INTO labels (key, labels, created) VALUES (?, ?, ?)",
                           (key, json.dumps(labels), datetime.now().isoformat(timespec="seconds")))
        self._conn.commit()

    def __len__(self) -> int:
        if self._conn is None:
            return len(self._mem)
        return int(self._conn.execute("SELECT COUNT(*) FROM labels").fetchone()[0])

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
