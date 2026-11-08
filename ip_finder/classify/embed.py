"""Ollama 임베딩 호출 (/api/embed). localhost 전용. 벡터는 캐시에 해시 키로 저장한다."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from ..cache import LabelCache
from ..ollama import AbortableHTTP, CancelledError, OllamaError, assert_local, resolve_model

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
        self.http = AbortableHTTP(self.host, timeout_sec)

    def cancel(self) -> None:
        self.http.cancel()

    def reset(self) -> None:
        self.http.reset()

    def available(self) -> bool:
        """모델이 설치돼 있으면 True. 'bge-m3' 가 'bge-m3:567m' 처럼 다른 꼬리표로만 있으면 그 이름으로 바꿔 쓴다."""
        try:
            found = resolve_model(self.host, self.model)
        except Exception:
            return False
        if found is None:
            return False
        if found != self.model and found != f"{self.model}:latest":
            self.model = found
        return True

    def _post(self, inputs: list[str]) -> list[list[float]]:
        body = {"model": self.model, "input": inputs, "keep_alive": self.keep_alive}
        t0 = time.time()
        try:
            res = self.http.post("/api/embed", body)
        except CancelledError:
            raise
        except OllamaError as e:
            raise OllamaError(f"임베딩 호출 실패: {e}") from e
        self.calls += 1
        self.seconds += time.time() - t0
        vecs = res.get("embeddings") or []
        if len(vecs) != len(inputs):
            raise OllamaError(f"임베딩 수 불일치: 기대 {len(inputs)}, 수신 {len(vecs)}")
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
