"""오프라인 테스트 공통 설정. 실제 Ollama 를 호출하지 않는다 (가짜 임베더).
0단계는 LLM 이 없으므로 가짜 LLM 클라이언트도 없다."""
from __future__ import annotations

from pathlib import Path

import pytest

from ip_finder.config import Config
from ip_finder.cues import cue_features
from ip_finder.samples import make_all
from ip_finder.switches import set_all


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
def cfg(tmp_path) -> Config:
    """기준선: 스위치 전부 끔, proto 분류기, 가짜 임베딩."""
    return Config(use_cache=False, embed_model="fake-embed", history_path=str(tmp_path / "hist"), gold_paths=[str(tmp_path / "gold")],
                  classifier_dir=str(tmp_path / "clf"))


@pytest.fixture
def cfg_all(cfg) -> Config:
    """스위치 전부 켬 (cfg 와 별개의 복사본)."""
    c = cfg.copy()
    set_all(c, True)
    return c


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder()
