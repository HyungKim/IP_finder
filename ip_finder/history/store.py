"""실행 스냅샷 저장소 (~/.ip_finder/history). 파일: runs/<run_id>.json, feedback.jsonl, train.jsonl.
스냅샷에는 문장 해시·라벨·점수·목록 여부만 들어가고 원문과 제목은 들어가지 않는다."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path


def text_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()[:16]


def make_run_id(started_at: str, source: Path) -> str:
    stamp = started_at.replace("-", "").replace(":", "").replace("T", "-")[:15]
    stem = "".join(ch for ch in source.stem if ch.isalnum())[:12] or "run"
    return f"{stamp}-{stem}"


class History:
    def __init__(self, root: Path | None):
        self.root = root
        if root is not None:
            (root / "runs").mkdir(parents=True, exist_ok=True)

    @property
    def enabled(self) -> bool:
        return self.root is not None

    # ---- 실행 ----
    def unique_run_id(self, run_id: str) -> str:
        """같은 초에 두 번 실행해도 ID가 겹치지 않게 한다."""
        if not self.enabled or not (self.root / "runs" / f"{run_id}.json").exists():
            return run_id
        n = 2
        while (self.root / "runs" / f"{run_id}-{n}.json").exists():
            n += 1
        return f"{run_id}-{n}"

    def save_run(self, snapshot: dict) -> None:
        if not self.enabled:
            return
        path = self.root / "runs" / f"{snapshot['run_id']}.json"
        path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=0), encoding="utf-8")

    def load_run(self, run_id: str) -> dict | None:
        if not self.enabled:
            return None
        path = self.root / "runs" / f"{run_id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def list_runs(self, limit: int = 200, full: bool = False) -> list[dict]:
        """최근 실행부터. full=False 면 문장 목록을 뺀 요약만."""
        if not self.enabled:
            return []
        out = []
        for path in sorted((self.root / "runs").glob("*.json"), reverse=True)[:limit]:
            try:
                d = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not full:
                d = {k: v for k, v in d.items() if k != "lines"}
            out.append(d)
        return out

    def previous_run(self, source_hash: str, source_name: str, before_run_id: str) -> dict | None:
        """같은 파일(내용 해시가 같거나, 없으면 이름이 같은)의 직전 실행."""
        if not self.enabled:
            return None
        by_name = None
        for d in self.list_runs(full=True):
            if d.get("run_id", "") >= before_run_id:
                continue
            if source_hash and d.get("source_hash") == source_hash:
                return d
            if by_name is None and d.get("source_name") == source_name:
                by_name = d
        return by_name

    # ---- 피드백 / 학습 이력 ----
    def _append(self, name: str, record: dict) -> None:
        if not self.enabled:
            return
        with open(self.root / name, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _read(self, name: str) -> list[dict]:
        if not self.enabled or not (self.root / name).exists():
            return []
        out = []
        for line in (self.root / name).read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out

    def log_feedback(self, record: dict) -> None:
        self._append("feedback.jsonl", {"time": datetime.now().isoformat(timespec="seconds"), **record})

    def log_train(self, record: dict) -> None:
        self._append("train.jsonl", {"time": datetime.now().isoformat(timespec="seconds"), **record})

    def feedback_log(self) -> list[dict]:
        return self._read("feedback.jsonl")

    def train_log(self) -> list[dict]:
        return self._read("train.jsonl")
