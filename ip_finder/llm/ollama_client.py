"""Ollama 호출. localhost 외의 호스트는 생성 단계에서 거부한다. 표준 라이브러리만 쓴다.
진행 중인 요청은 cancel() 로 즉시 끊을 수 있다 (소켓을 닫으면 Ollama 도 생성을 중단한다)."""
from __future__ import annotations

import http.client
import json
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
GRADES = ["A", "B", "C", "D", "X"]


class LLMError(RuntimeError):
    pass


class CancelledError(LLMError):
    """사용자가 중지해 요청을 끊음."""


class AbortableHTTP:
    """http.client 기반 POST. 다른 스레드에서 cancel() 하면 진행 중인 요청의 소켓을 닫아 즉시 돌아온다."""

    def __init__(self, host: str, timeout: int):
        parsed = urllib.parse.urlparse(host)
        self._host, self._port = parsed.hostname or "127.0.0.1", parsed.port or 11434
        self._timeout = timeout
        self._conn: http.client.HTTPConnection | None = None
        self._lock = threading.Lock()
        self._cancelled = False

    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True
            conn = self._conn
        if conn is not None:
            try:
                if conn.sock is not None:
                    conn.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                conn.close()
            except OSError:
                pass

    def reset(self) -> None:
        with self._lock:
            self._cancelled = False

    def post(self, path: str, body: dict) -> dict:
        with self._lock:
            if self._cancelled:
                raise CancelledError("중지됨")
            conn = http.client.HTTPConnection(self._host, self._port, timeout=self._timeout)
            self._conn = conn
        try:
            conn.request("POST", path, body=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})
            res = conn.getresponse()
            data = res.read()
            if res.status >= 400:
                raise LLMError(f"Ollama 응답 {res.status}: {data[:200]!r}")
            return json.loads(data)
        except (OSError, http.client.HTTPException, ValueError) as e:
            with self._lock:
                cancelled = self._cancelled
            if cancelled:
                raise CancelledError("중지됨") from e
            raise LLMError(f"Ollama 호출 실패 ({self._host}:{self._port}): {e}") from e
        finally:
            with self._lock:
                self._conn = None
            try:
                conn.close()
            except OSError:
                pass


def assert_local(host: str) -> None:
    parsed = urllib.parse.urlparse(host)
    name = (parsed.hostname or "").lower()
    if name not in LOCAL_HOSTS:
        raise LLMError(f"외부 호스트 금지: {host!r}. 로컬 Ollama(127.0.0.1)만 허용합니다.")


def label_schema(n: int) -> dict:
    return {
        "type": "object",
        "properties": {"labels": {"type": "array", "items": {"type": "string", "enum": GRADES},
                                  "minItems": n, "maxItems": n}},
        "required": ["labels"],
    }


class OllamaClient:
    def __init__(self, host: str, model: str, *, timeout_sec: int = 600, keep_alive: str = "30m",
                 num_ctx: int = 2048, retries: int = 2):
        assert_local(host)
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout_sec
        self.keep_alive = keep_alive
        self.num_ctx = num_ctx
        self.retries = retries
        self.calls = 0
        self.prompt_tokens = 0
        self.output_tokens = 0
        self.llm_seconds = 0.0
        self.http = AbortableHTTP(self.host, timeout_sec)

    def cancel(self) -> None:
        """진행 중인 호출을 즉시 끊는다. 다음 호출 전에 reset() 하지 않으면 이후 호출도 바로 CancelledError."""
        self.http.cancel()

    def reset(self) -> None:
        self.http.reset()

    # ----- 상태 확인 -----
    def _get(self, path: str) -> dict:
        with urllib.request.urlopen(self.host + path, timeout=10) as r:
            return json.loads(r.read())

    def available(self) -> bool:
        try:
            self._get("/api/tags")
            return True
        except Exception:
            return False

    def installed_models(self) -> list[str]:
        try:
            return [m["name"] for m in self._get("/api/tags").get("models", [])]
        except Exception:
            return []

    def has_model(self) -> bool:
        names = self.installed_models()
        return self.model in names or f"{self.model}:latest" in names

    # ----- 호출 -----
    def _post(self, path: str, body: dict) -> dict:
        return self.http.post(path, body)

    def chat_labels(self, system: str, user: str, n: int) -> list[str]:
        """n개 줄에 대한 라벨 배열을 돌려준다. 길이와 값은 JSON 스키마로 강제한다."""
        body = {
            "model": self.model, "stream": False, "think": False, "keep_alive": self.keep_alive,
            "format": label_schema(n),
            "options": {"temperature": 0, "num_ctx": self.num_ctx, "num_predict": 6 * n + 24},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            t0 = time.time()
            try:
                res = self._post("/api/chat", body)
                self.calls += 1
                self.llm_seconds += time.time() - t0
                self.prompt_tokens += int(res.get("prompt_eval_count") or 0)
                self.output_tokens += int(res.get("eval_count") or 0)
                labels = json.loads(res["message"]["content"]).get("labels", [])
                if len(labels) != n:
                    raise LLMError(f"라벨 수 불일치: 기대 {n}, 수신 {len(labels)}")
                return [str(x).strip().upper() for x in labels]
            except CancelledError:
                raise
            except (KeyError, ValueError, LLMError) as e:
                last = e
                if "호출 실패" in str(e):
                    raise LLMError(f"Ollama에 연결할 수 없습니다 ({self.host}): {e}") from e
                time.sleep(0.5)
        raise LLMError(f"라벨 호출 실패({self.retries + 1}회): {last}")
