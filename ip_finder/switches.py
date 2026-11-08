"""켜고 끄는 스위치 목록. 읽기·전처리·후처리의 규칙 하나하나가 스위치이고, 기본값은 전부 끔(기준선)이다.

사다리 실행(ladder)은 이 목록의 순서대로 한 칸씩 켜 가며 결과가 어떻게 달라지는지 비교한다.
스위치를 추가하려면 Config 에 bool 필드를 만들고 여기 SWITCHES 에 한 줄을 넣으면 CLI·UI·사다리·실행 정보에 모두 나타난다."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Switch:
    name: str        # 짧은 영문 키. 사다리 설정 파일과 CLI(--on/--off)에서 쓴다
    field: str       # Config 의 필드 이름
    label: str       # 한글 이름 (Excel·UI)
    group: str       # 읽기 | 줄 규칙 | 페이지 규칙 | 후처리
    off: str         # 껐을 때 무엇이 일어나는가
    on: str          # 켰을 때 무엇이 일어나는가


SWITCHES: list[Switch] = [
    Switch("layout", "layout_analysis", "레이아웃 분석", "읽기",
           "PDF 는 PyMuPDF 가 주는 줄을 순서대로, PPTX 는 도형 순서대로 문단을 그대로 읽는다",
           "다단 읽기 순서, 문단 묶기, 제목·표·도형 구분, ▪·| 로 나열된 항목 나누기"),
    Switch("short_line", "rule_short_line", "짧은 줄 제외", "줄 규칙",
           "모든 줄을 판정한다", "공백 제외 글자수가 short_line_chars(기본 10) 이하인 줄은 후보에서 뺀다"),
    Switch("korean", "rule_require_korean", "한글 없음 제외", "줄 규칙",
           "영어·숫자·기호만 있는 줄도 판정한다", "한글이 한 글자도 없는 줄은 후보에서 뺀다"),
    Switch("split_long", "rule_split_long", "긴 줄 분할", "줄 규칙",
           "줄을 그대로 둔다", "split_len(기본 80자)을 넘는 줄은 문장 부호에서 나눈다"),
    Switch("repeated", "rule_repeated_line", "반복·고정 문구 제외", "줄 규칙",
           "반복되는 줄도 판정한다", "repeated_line_min_pages(기본 3)쪽 이상 같은 줄과 stoplist 의 문구는 후보에서 뺀다"),
    Switch("pattern", "rule_pattern_lines", "패턴 줄 제외", "줄 규칙",
           "숫자만·담당자·짧은 일정/금액 줄도 판정한다", "숫자만, '담당:' 으로 시작, 30자 이하의 일정·금액 줄은 후보에서 뺀다"),
    Switch("page_exclude", "rule_page_exclude", "페이지 제외", "페이지 규칙",
           "모든 쪽을 판정한다", "제목이 page_exclude_patterns(목차·일정·비용·감사 등)에 걸리는 쪽은 통째로 뺀다"),
    Switch("cover", "rule_cover", "표지 제외", "페이지 규칙",
           "1쪽도 판정한다", "1쪽에 남은 줄이 cover_max_lines(기본 4) 이하이면 표지로 보고 뺀다"),
    Switch("page_weight", "page_weight_enabled", "페이지 가중치", "페이지 규칙",
           "모든 쪽의 가중치 1.0", "제목이 관련성 낮음 키워드에 걸리는 쪽은 가중치 low_relevance_weight(기본 0.4)"),
    Switch("title_fix", "title_fix", "제목 기반 보정", "후처리",
           "분류기 등급 그대로", "원인·문제 유형 쪽에서 변경 동사 없는 A 는 C 로 내린다"),
    Switch("safety_net", "safety_net", "안전망", "후처리",
           "X 는 그대로 제외", "X 인데 기술 단서어가 있으면 X? 로 보류 시트에 남긴다"),
]
BY_NAME = {s.name: s for s in SWITCHES}
BY_FIELD = {s.field: s for s in SWITCHES}
GROUPS = ["읽기", "줄 규칙", "페이지 규칙", "후처리"]


def switch_state(cfg) -> dict[str, bool]:
    """{스위치 이름: 켬 여부} (SWITCHES 순서)."""
    return {s.name: bool(getattr(cfg, s.field)) for s in SWITCHES}


def set_switch(cfg, name: str, on: bool) -> None:
    if name not in BY_NAME:
        raise ValueError(f"모르는 스위치: {name} (가능: {', '.join(BY_NAME)})")
    setattr(cfg, BY_NAME[name].field, bool(on))


def set_all(cfg, on: bool) -> None:
    for s in SWITCHES:
        setattr(cfg, s.field, bool(on))


def describe(cfg) -> str:
    """실행 정보·로그용 한 줄. 예: '켬: 레이아웃 분석, 짧은 줄 제외 / 끔: 나머지 9개'"""
    state = switch_state(cfg)
    on = [BY_NAME[n].label for n, v in state.items() if v]
    off = [BY_NAME[n].label for n, v in state.items() if not v]
    if not on:
        return "전부 끔 (기준선)"
    if not off:
        return "전부 켬"
    return f"켬: {', '.join(on)} / 끔: {', '.join(off)}"


def table_rows(cfg) -> list[tuple[str, str, str, str]]:
    """(묶음, 이름, 켬/끔, 지금 일어나는 일) — Excel 실행 정보와 CLI switches 명령이 쓴다."""
    rows = []
    for s in SWITCHES:
        on = bool(getattr(cfg, s.field))
        rows.append((s.group, s.label, "켬" if on else "끔", s.on if on else s.off))
    return rows
