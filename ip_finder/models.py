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
    weight: float = 1.0             # 페이지 가중치 (제목 규칙). 0이면 판정하지 않음
    weight_reason: str = ""         # 가중치를 정한 규칙
    relevance: str = "높음"          # 관련성: 높음 | 낮음 (제목 키워드)
    title_source: str = ""          # 제목을 찾은 방법: placeholder | font | first-line | 없음

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
    source: str = ""                # clf | llm | verified | gold
    clf_label: str = ""             # 1차 분류기 라벨 (cascade/fast)
    llm_label: str = ""             # 2차 LLM 라벨 (cascade/llm). 비어 있으면 LLM 이 보지 않음
    clf_conf: float | None = None   # 분류기 확신 (1위-2위 차이)
    clf_top: float | None = None    # 분류기 1위 점수 (학습 분류기는 확률)
    page_weight: float = 1.0        # 페이지 가중치
    confidence: float = 1.0         # 판정 신뢰도 0~1 (post.scoring)
    score: float = 1.0              # 신뢰도 × 가중치
    hold_reason: str = ""           # 비어 있지 않으면 검토 목록 대신 보류
    stage_out: int = 0              # 0 통과 / 1 분류기 1차에서 제외 / 2 LLM 2차(또는 후처리·골드)에서 제외

    @property
    def key(self) -> tuple[int, int]:
        return (self.page_no, self.line_idx)


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
    clf_lines: int = 0              # 분류기만으로 끝난 문장 수 (cascade: 1차에서 X 로 제외된 문장)
    llm_lines: int = 0              # LLM이 판정한 문장 수 (cascade: 1차 후보)
    llm_rejected: int = 0           # cascade: LLM 2차에서 대상 등급이 아니라고 본 후보 수
    target_grades: str = "A,B"      # 추출 대상 등급
    embed_sec: float = 0.0
    llm_sec: float = 0.0
    accept_score: float = 0.5       # 검토 목록 진입 점수
    page_weight_enabled: bool = True
    low_relevance_weight: float = 0.4
    pages_low: int = 0              # 관련성 낮음으로 분류된 페이지 수
    held_lines: int = 0             # 점수 미달로 보류된 A~D 문장 수
    gold_lines: int = 0             # 골드 정답을 그대로 쓴 문장 수
    gold_changed: int = 0           # 그중 모델 판정과 달랐던 문장 수
    gold_desc: str = ""             # 읽은 골드 요약 (파일 수, 문장 수)
    run_id: str = ""                # 이력 저장 ID
    prev_run_id: str = ""           # 같은 파일의 직전 실행 ID (변경 추적 기준)
    settings_diff: list[str] = field(default_factory=list)   # 직전 실행과 달라진 설정
    changes: dict = field(default_factory=dict)              # 직전 실행 대비 변경 요약
