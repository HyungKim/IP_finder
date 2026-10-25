"""Ollama 임베딩 호출 (/api/embed). localhost 전용. 벡터는 캐시에 해시 키로 저장한다."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from ..cache import LabelCache
from ..llm.ollama_client import LLMError, assert_local

BATCH = 32


class OllamaEmbedder:
    def __init__(self, host: str, model: str, *, timeout_sec: int = 300, keep_alive: str = "30m",
                 cache: LabelCache | None = None):
        assert_local(host)
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout_sec
        self.keep_alive = keep_alive
        self.cache = cache
        self.calls = 0
        self.cache_hits = 0
        self.seconds = 0.0

    def available(self) -> bool:
        try:
            with urllib.request.urlopen(self.host + "/api/tags", timeout=10) as r:
                names = [m["name"] for m in json.loads(r.read()).get("models", [])]
            return self.model in names or f"{self.model}:latest" in names
        except Exception:
            return False

    def _post(self, inputs: list[str]) -> list[list[float]]:
        body = {"model": self.model, "input": inputs, "keep_alive": self.keep_alive}
        req = urllib.request.Request(self.host + "/api/embed", data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                res = json.loads(r.read())
        except urllib.error.URLError as e:
            raise LLMError(f"임베딩 호출 실패 ({self.host}): {e.reason}") from e
        self.calls += 1
        self.seconds += time.time() - t0
        vecs = res.get("embeddings") or []
        if len(vecs) != len(inputs):
            raise LLMError(f"임베딩 수 불일치: 기대 {len(inputs)}, 수신 {len(vecs)}")
        return vecs

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float] | None] = [None] * len(texts)
        todo: list[int] = []
        for i, t in enumerate(texts):
            key = LabelCache.key(self.model, "embed", t)
            v = self.cache.get_vec(key) if self.cache is not None else None
            if v is not None:
                out[i] = v
                self.cache_hits += 1
            else:
                todo.append(i)
        for start in range(0, len(todo), BATCH):
            idxs = todo[start:start + BATCH]
            vecs = self._post([texts[i] for i in idxs])
            for i, v in zip(idxs, vecs):
                out[i] = v
                if self.cache is not None:
                    self.cache.set_vec(LabelCache.key(self.model, "embed", texts[i]), v)
        return [v if v is not None else [] for v in out]
