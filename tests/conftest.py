"""오프라인 테스트 공통 설정. 실제 Ollama를 호출하지 않는다 (가짜 클라이언트)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from ip_finder.config import Config
from ip_finder.cues import CHANGE_VERBS, UNIT_RE
from ip_finder.samples import make_all

_PLAN = re.compile(r"(예정|검토|계획|도입)")
_PROBLEM = re.compile(r"(발생|불가|원인|관측|한계|편차)")
_NONTECH = re.compile(r"(클레임|표준|일정|비용|담당|감사|불량률)")   # 불량률 줄은 실제 모델처럼 X로 → 안전장치 검증용
_MECHANISM = re.compile(r"(열팽창|브리지)")                      # 실제 4B의 오류를 흉내: 원인 설명을 A로


class FakeClient:
    """줄 내용으로 결정적으로 라벨을 매기는 가짜 LLM. 호출 수와 입력을 기록한다."""
    model = "fake-model"

    def __init__(self):
        self.calls = 0
        self.inputs: list[str] = []

    def available(self):
        return True

    def chat_labels(self, system: str, user: str, n: int) -> list[str]:
        self.calls += 1
        self.inputs.append(user)
        lines = [ln for ln in user.splitlines()[1:] if ln.strip()]
        assert len(lines) == n, (len(lines), n)
        out = []
        for ln in lines:
            text = re.sub(r"^\[\d+\]\s*", "", ln)
            if _NONTECH.search(text):
                out.append("X")
            elif _MECHANISM.search(text):
                out.append("A")
            elif _PLAN.search(text):
                out.append("D")
            elif CHANGE_VERBS.search(text):
                out.append("A")
            elif UNIT_RE.search(text):
                out.append("B")
            elif _PROBLEM.search(text):
                out.append("C")
            else:
                out.append("X")
        return out


@pytest.fixture(scope="session")
def sample_dir(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("samples")
    make_all(d)
    return d


@pytest.fixture
def cfg() -> Config:
    return Config(use_cache=False)


@pytest.fixture
def fake_client() -> FakeClient:
    return FakeClient()
