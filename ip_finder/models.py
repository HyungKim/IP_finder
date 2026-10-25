"""공통 데이터 모델. 리더가 Document를 만들고, 전처리·라벨링·후처리가 이를 채운다."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

GRADES = ("A", "B", "C", "D", "X")


@dataclass
class Line:
    idx: int                        # 전처리 후 페이지 내 번호(1부터). 제거된 줄은 0
    text: str
    level: int = 0                  # 불릿 계층. 0이 최상위
    source: str = "body"            # body | table
    removed_by: str | None = None   # 전처리 규칙 이름. None이면 LLM에 보냄
    split_from: int | None = None   # 긴 줄을 나눈 경우 원래 줄의 순번

    @property
    def active(self) -> bool:
        return self.removed_by is None and bool(self.text.strip())


@dataclass
class Page:
    no: int
    title: str
    lines: list[Line] = field(default_factory=list)
    has_graphics: bool = False      # 그림·도형 등 텍스트가 아닌 요소 존재
    excluded_reason: str | None = None
    section: str = ""

    def active_lines(self) -> list[Line]:
        return [ln for ln in self.lines if ln.active]

    @property
    def has_body(self) -> bool:
        return any(ln.text.strip() for ln in self.lines)


@dataclass
class Document:
    path: Path
    kind: str                       # pdf | pptx
    pages: list[Page]
    title: str = ""


@dataclass
class LabeledLine:
    page_no: int
    page_title: str
    section: str
    line_idx: int
    text: str
    label: str                      # A B C D X, 보류는 "X?", 판정 실패는"?"
    raw_label: str                  # 후처리 전 라벨 (분류기 또는 LLM)
    notes: list[str] = field(default_factory=list)   # 보정(A→C), 분할, 단서어: ...
    source: str = ""                # clf | llm
    clf_label: str = ""             # 분류기 라벨 (hybrid/fast)
    clf_conf: float | None = None   # 분류기 확신 (1위-2위 차이)


@dataclass
class RunInfo:
    source: str
    model: str
    prompt_version: str
    started_at: str
    elapsed_sec: float = 0.0
    pages_total: int = 0
    pages_labeled: int = 0
    pages_excluded: int = 0
    pages_image: int = 0
    llm_calls: int = 0
    cache_hits: int = 0
    warnings: list[str] = field(default_factory=list)
    mode: str = ""
    embed_model: str = ""
    classifier: str = ""            # 제로샷 | 학습(경로)
    threshold: float | None = None
    clf_lines: int = 0              # 분류기 판정을 채택한 문장 수
    llm_lines: int = 0              # LLM이 판정한 문장 수
    embed_sec: float = 0.0
    llm_sec: float = 0.0
