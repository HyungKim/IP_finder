"""공통 데이터 모델. 리더가 Document 를 만들고, 전처리·분류·후처리가 이를 채운다."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

GRADES = ("A", "B", "C", "D", "X")


@dataclass
class Line:
    idx: int                        # 전처리 후 페이지 내 번호(1부터). 제거된 줄은 0
    text: str
    level: int = 0                  # 불릿 계층. 0이 최상위
    source: str = "body"            # body | table | diagram(도형·SmartArt·차트 제목 안의 글)
    removed_by: str | None = None   # 전처리 규칙 이름. None 이면 분류기에 보낸다
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
    title_source: str = ""          # 제목을 찾은 방법: placeholder | font | bold | first-line | raw | 없음

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
    notes: list[str] = field(default_factory=list)   # 리더가 남기는 안내(다단 감지, 회전 문자, 표 개수 등). 실행 정보의 경고로 나간다
    reader: str = "layout"          # layout | raw  (레이아웃 분석 스위치)


@dataclass
class LabeledLine:
    page_no: int
    page_title: str
    section: str
    line_idx: int
    text: str
    label: str                      # A B C D X, 보류는 "X?", 판정 실패는 "?"
    raw_label: str                  # 후처리 전 라벨 (분류기 판정 그대로)
    notes: list[str] = field(default_factory=list)   # 보정(A→C), 분할, 표, 도형, 단서어: ..., 골드 반영
    source: str = "clf"             # clf | gold
    clf_label: str = ""             # 분류기 라벨
    clf_conf: float | None = None   # 분류기가 낸 신뢰도 0~1 (1위 라벨의 확률 추정)
    clf_margin: float | None = None # 1위 - 2위 점수 차이 (비고에 표시)
    page_weight: float = 1.0        # 페이지 가중치
    confidence: float = 1.0         # 판정 신뢰도 0~1 (post.scoring)
    score: float = 1.0              # 신뢰도 × 가중치
    hold_reason: str = ""           # 비어 있지 않으면 검토 목록 대신 보류
    stage_out: int = 0              # 0 통과 / 1 분류기에서 대상 등급 밖 / 2 후처리·골드가 대상 등급 밖으로 바꿈

    @property
    def key(self) -> tuple[int, int]:
        return (self.page_no, self.line_idx)


@dataclass
class RunInfo:
    source: str
    started_at: str
    elapsed_sec: float = 0.0
    version: str = ""
    reader: str = "layout"          # layout | raw
    switches: dict = field(default_factory=dict)   # {스위치 이름: 켬 여부}
    pages_total: int = 0
    pages_labeled: int = 0
    pages_excluded: int = 0
    pages_image: int = 0
    cache_hits: int = 0
    warnings: list[str] = field(default_factory=list)
    embed_model: str = ""
    classifier_name: str = ""       # 설정의 분류기 키 (proto, knn, ...)
    classifier: str = ""            # 사람이 읽는 분류기 설명 (학습 시각·문장 수 포함)
    clf_lines: int = 0              # 분류기가 판정한 문장 수
    target_grades: str = "A,B"
    embed_sec: float = 0.0
    classify_sec: float = 0.0
    accept_score: float = 0.5
    page_weight_enabled: bool = False
    low_relevance_weight: float = 0.4
    pages_low: int = 0              # 관련성 낮음으로 분류된 페이지 수
    held_lines: int = 0             # 점수 미달로 보류된 A~D 문장 수
    gold_lines: int = 0             # 골드 정답을 그대로 쓴 문장 수
    gold_changed: int = 0           # 그중 분류기 판정과 달랐던 문장 수
    gold_desc: str = ""             # 읽은 골드 요약 (파일 수, 문장 수)
    run_id: str = ""                # 이력 저장 ID
    prev_run_id: str = ""           # 같은 파일의 직전 실행 ID (변경 추적 기준)
    settings_diff: list[str] = field(default_factory=list)   # 직전 실행과 달라진 설정
    changes: dict = field(default_factory=dict)              # 직전 실행 대비 변경 요약
