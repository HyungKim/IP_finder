"""Ollama 와 주고받는 HTTP. 표준 라이브러리만 쓰고, 127.0.0.1 바깥 호스트는 만들 때부터 거부한다.
0단계에서는 임베딩(/api/embed)만 쓴다. 진행 중인 요청은 cancel() 로 소켓을 끊어 즉시 돌아온다 (UI 중지 버튼)."""
from __future__ import annotations

import http.client
import json
import socket
import threading
import urllib.parse
import urllib.request

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


class OllamaError(RuntimeError):
    """Ollama 호출 실패 (연결 불가, 오류 응답, 응답 형식 불일치)."""


class CancelledError(OllamaError):
    """사용자가 중지해 요청을 끊음."""


def assert_local(host: str) -> None:
    """호스트가 로컬 주소가 아니면 예외. 사내 자료가 바깥으로 나가지 않게 하는 첫 번째 방어선."""
    parsed = urllib.parse.urlparse(host)
    name = (parsed.hostname or "").lower()
    if name not in LOCAL_HOSTS:
        raise OllamaError(f"외부 호스트 금지: {host!r}. 로컬 Ollama(127.0.0.1)만 허용합니다.")


def installed_models(host: str, timeout: int = 10) -> list[str]:
    """설치된 모델 이름 목록. 연결이 안 되면 빈 목록."""
    try:
        with urllib.request.urlopen(host.rstrip("/") + "/api/tags", timeout=timeout) as r:
            return [m["name"] for m in json.loads(r.read()).get("models", [])]
    except Exception:
        return []


def server_available(host: str, timeout: int = 10) -> bool:
    try:
        with urllib.request.urlopen(host.rstrip("/") + "/api/tags", timeout=timeout):
            return True
    except Exception:
        return False


def resolve_model(host: str, model: str) -> str | None:
    """설치된 모델 중 model 에 해당하는 실제 이름. 'bge-m3' 는 'bge-m3:latest' 로, 그것도 없으면 'bge-m3:567m' 처럼
    같은 이름에 다른 꼬리표(tag) 하나만 있을 때 그것으로 푼다. 없으면 None."""
    names = installed_models(host)
    if model in names:
        return model
    if f"{model}:latest" in names:
        return f"{model}:latest"
    base = model.split(":")[0]
    same = [n for n in names if n.split(":")[0] == base]
    return same[0] if len(same) == 1 else None


def explain_missing_model(host: str, model: str) -> str:
    """임베딩 모델을 쓸 수 없을 때 사람이 바로 고칠 수 있게 원인을 적는다."""
    if not server_available(host):
        return (f"Ollama 서버에 연결할 수 없습니다 ({host}). Ollama 를 실행하세요 (윈도우: 시작 메뉴의 Ollama, 또는 명령창에서 ollama serve). "
                f"실행 중인데도 안 되면 설정 host 와 Ollama 의 포트(기본 11434)가 같은지 확인하세요.")
    names = installed_models(host)
    base = model.split(":")[0]
    same = [n for n in names if n.split(":")[0] == base and n != model]
    msg = f"Ollama 는 실행 중이지만 모델 {model} 이 없습니다. 설치된 모델: {', '.join(names) or '없음'}."
    if same:
        msg += f" 같은 이름의 다른 꼬리표 {', '.join(same)} 가 있습니다 → 설정 embed_model = \"{same[0]}\" 로 두거나 ollama cp {same[0]} {base}."
    else:
        msg += (f" → 이 PC 에서 'ollama pull {model}' (약 1.2GB). 인터넷이 막힌 PC 면 다른 PC 에서 pull 한 뒤 "
                f"%USERPROFILE%\\.ollama\\models 폴더(blobs, manifests)를 이 PC 의 같은 위치로 복사하고 Ollama 를 다시 시작하세요.")
    return msg


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
                raise OllamaError(f"Ollama 응답 {res.status}: {data[:200]!r}")
            return json.loads(data)
        except (OSError, http.client.HTTPException, ValueError) as e:
            with self._lock:
                cancelled = self._cancelled
            if cancelled:
                raise CancelledError("중지됨") from e
            raise OllamaError(f"Ollama 호출 실패 ({self._host}:{self._port}): {e}") from e
        finally:
            with self._lock:
                self._conn = None
            try:
                conn.close()
            except OSError:
                pass
