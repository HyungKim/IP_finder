"""중지 토큰. UI 의 중지 버튼이 cancel() 을 부르면 진행 중인 Ollama 요청의 소켓을 끊고, 파이프라인은 다음 단계 전에 check() 로 멈춘다."""
from __future__ import annotations

import threading


class Cancelled(Exception):
    pass


class CancelToken:
    def __init__(self):
        self._flag = threading.Event()
        self._abortables: list = []
        self._lock = threading.Lock()

    def register(self, obj) -> None:
        """cancel() 메서드가 있는 객체(OllamaClient, OllamaEmbedder)를 등록한다."""
        with self._lock:
            if obj is not None and hasattr(obj, "cancel") and obj not in self._abortables:
                self._abortables.append(obj)

    def cancel(self) -> None:
        self._flag.set()
        with self._lock:
            objs = list(self._abortables)
        for o in objs:
            try:
                o.cancel()
            except Exception:
                pass

    @property
    def cancelled(self) -> bool:
        return self._flag.is_set()

    def check(self) -> None:
        if self._flag.is_set():
            raise Cancelled()

    def reset(self) -> None:
        self._flag.clear()
        with self._lock:
            objs = list(self._abortables)
        for o in objs:
            if hasattr(o, "reset"):
                try:
                    o.reset()
                except Exception:
                    pass
