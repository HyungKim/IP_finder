"""오프라인 테스트 공통 설정. 실제 Ollama를 호출하지 않는다 (가짜 LLM 클라이언트, 가짜 임베더)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from ip_finder.config import Config
from ip_finder.cues import CHANGE_VERBS, UNIT_RE, cue_features
from ip_finder.samples import make_all

_PLAN = re.compile(r"(예정|검토|계획|도입)")
_PROBLEM = re.compile(r"(발생|불가|원인|관측|한계|편차)")
_NONTECH = re.compile(r"(클레임|표준|일정|비용|담당|감사|불량률)")   # 불량률 줄은 실제 모델처럼 X로 → 안전장치 검증용
_MECHANISM = re.compile(r"(열팽창|브리지)")                      # 실제 4B의 오류를 흉내: 원인 설명을 A로
_LINE = re.compile(r"^\[\d+\]\s*(\([^)]*\)\s*)?")              # "[3] " 또는 "[3] (슬라이드 제목) " 제거


class FakeClient:
    """줄 내용으로 결정적으로 라벨을 매기는 가짜 LLM. 페이지 프롬프트와 묶음 프롬프트 둘 다 읽는다."""
    model = "fake-model"
    llm_seconds = 0.0

    def __init__(self):
        self.calls = 0
        self.inputs: list[str] = []

    def available(self):
        return True

    def chat_labels(self, system: str, user: str, n: int) -> list[str]:
        self.calls += 1
        self.inputs.append(user)
        lines = [ln for ln in user.splitlines() if ln.startswith("[") and not ln.startswith("[슬라이드")]
        assert len(lines) == n, (len(lines), n)
        out = []
        for ln in lines:
            text = _LINE.sub("", ln).strip()
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


class FakeEmbedder:
    """단서어 특성을 벡터로 쓰는 가짜 임베더. 원형 문장과 본문 문장이 같은 규칙으로 임베딩되므로 제로샷이 결정적으로 동작."""
    def __init__(self, available: bool = True):
        self.model = "fake-embed"
        self._available = available
        self.calls = 0
        self.cache_hits = 0
        self.seconds = 0.0

    def available(self):
        return self._available

    def embed(self, texts):
        self.calls += 1
        out = []
        for t in texts:
            f = cue_features(t, "general")[:9]           # 페이지 유형 차원 제외
            out.append([*f, 0.3 + 0.01 * (len(t) % 7)])  # 영벡터 방지용 상수 차원
        return out


@pytest.fixture(scope="session")
def sample_dir(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("samples")
    make_all(d)
    return d


@pytest.fixture
def cfg() -> Config:
    return Config(use_cache=False, mode="llm")


@pytest.fixture
def cfg_hybrid(tmp_path) -> Config:
    return Config(use_cache=False, mode="hybrid", classifier_path=str(tmp_path / "none.npz"))


@pytest.fixture
def fake_client() -> FakeClient:
    return FakeClient()


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder()
