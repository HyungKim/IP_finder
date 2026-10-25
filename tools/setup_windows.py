"""윈도우 설치 2단계. install.bat 가 가상환경을 만든 뒤 가상환경의 python 으로 이 스크립트를 실행한다.
표준 라이브러리만 쓴다. 패키지 설치 → Ollama 확인 → 모델 확인 → 환경 점검. 한글 안내는 모두 여기서 출력한다
(cmd.exe 는 UTF-8 배치 파일의 한글을 잘못 해석하므로 배치 파일에는 ASCII 만 둔다)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = os.environ.get("IP_FINDER_MODEL", "qwen3:4b-instruct")
EMBED_MODEL = os.environ.get("IP_FINDER_EMBED_MODEL", "bge-m3")   # hybrid/fast 모드용. 없어도 llm 모드로 동작
HOST = "http://127.0.0.1:11434"
REQ = ROOT / ("requirements-windows.txt" if sys.platform == "win32" else "requirements.txt")
WHEELS = ROOT / "wheels"


def say(msg: str = "") -> None:
    print(msg, flush=True)


def run(cmd: list[str], quiet: bool = False) -> int:
    kw = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL} if quiet else {}
    try:
        return subprocess.call(cmd, **kw)
    except OSError:
        return 1


def pip(*args: str, quiet: bool = False) -> int:
    return run([sys.executable, "-m", "pip", *args], quiet=quiet)


def step_packages() -> bool:
    if pip("--version", quiet=True) != 0:
        say("  pip 준비 중...")
        run([sys.executable, "-m", "ensurepip", "--upgrade"], quiet=True)
    if WHEELS.is_dir() and any(WHEELS.glob("*.whl")):
        say(f"[1/4] 패키지 설치 (오프라인: {WHEELS.name} 폴더의 wheel 사용)")
        rc = pip("install", "--no-index", "--find-links", str(WHEELS), "-r", str(REQ))
    else:
        say("[1/4] 패키지 설치 (온라인: PyPI)")
        pip("install", "--upgrade", "pip", quiet=True)
        rc = pip("install", "-r", str(REQ))
    if rc != 0:
        say("")
        say("[오류] 패키지 설치에 실패했습니다.")
        say("  인터넷이 막힌 PC라면 GitHub 릴리스의 wheel 번들(zip)을 받아 풀고,")
        say("  생긴 wheels 폴더를 install.bat 옆에 둔 뒤 install.bat 를 다시 실행하세요.")
        say("  다른 Python 버전이면 인터넷이 되는 윈도우 PC에서 tools\\download_wheels.bat 로 번들을 만듭니다.")
        return False
    return True


def ollama_tags() -> list[str] | None:
    try:
        with urllib.request.urlopen(HOST + "/api/tags", timeout=3) as r:
            return [m["name"] for m in json.loads(r.read()).get("models", [])]
    except Exception:
        return None


def step_ollama() -> bool:
    exe = shutil.which("ollama")
    if exe is None:
        say("")
        say("[오류] Ollama가 설치되어 있지 않습니다.")
        say("  https://ollama.com/download/windows 에서 설치한 뒤 install.bat 를 다시 실행하세요.")
        return False
    say(f"[2/4] Ollama 확인: {exe}")
    tags = ollama_tags()
    if tags is None:
        say("  Ollama 서버가 꺼져 있어 시작합니다. 새 창이 열리면 닫지 말고 최소화해 두세요...")
        flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        try:
            subprocess.Popen([exe, "serve"], creationflags=flags) if flags else subprocess.Popen([exe, "serve"])
        except OSError as e:
            say(f"[오류] Ollama 서버를 시작하지 못했습니다: {e}")
            return False
        for _ in range(20):
            time.sleep(1)
            tags = ollama_tags()
            if tags is not None:
                break
        if tags is None:
            say("[오류] Ollama 서버에 연결할 수 없습니다. Ollama 를 실행한 뒤 다시 시도하세요.")
            return False
    say("[3/4] 모델 확인")
    for name, size, required in ((MODEL, "약 2.5GB", True), (EMBED_MODEL, "약 1.2GB", False)):
        if name in tags or f"{name}:latest" in tags:
            say(f"  모델 {name} 있음")
            continue
        say(f"  모델 {name} 내려받는 중 ({size})...")
        if run([exe, "pull", name]) == 0:
            continue
        say("")
        say(f"[{'오류' if required else '주의'}] 모델 {name} 을 받지 못했습니다.")
        say(f"  인터넷이 막힌 PC라면 다른 PC에서 'ollama pull {name}' 을 실행한 뒤")
        say("  %USERPROFILE%\\.ollama\\models 폴더를 이 PC의 같은 위치로 복사하세요.")
        if required:
            return False
        say("  임베딩 모델이 없으면 hybrid/fast 모드 대신 llm 모드로 동작합니다 (느리지만 정상).")
    return True


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    os.chdir(ROOT)
    say(f"Python {sys.version.split()[0]}  ({sys.executable})")
    if not step_packages():
        return 1
    if not step_ollama():
        return 1
    say("[4/4] 환경 점검")
    rc = run([sys.executable, "-m", "ip_finder.cli", "check"])
    say("")
    if rc == 0:
        say("설치가 끝났습니다. 사용법:")
        say("  ui.bat                        (더블클릭하면 창이 뜹니다)")
        say("  extract.bat 보고서.pptx        (파일이나 폴더를 extract.bat 위로 끌어다 놓아도 됩니다)")
        say("  결과는 원본 옆에 '이름_검토후보.xlsx' 로 생깁니다.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
