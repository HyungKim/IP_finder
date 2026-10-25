"""제목으로 페이지 유형을 추정한다. LLM 입력의 힌트 한 줄, 분류기 특성, 제목 기반 보정이 함께 쓴다.
한 유형에만 해당할 때 힌트를 주고, 여러 유형이 섞인 제목('문제점 및 개선 방안')은 힌트를 주지 않는다."""
from __future__ import annotations

import re

PAGE_TYPES: list[tuple[str, re.Pattern, str]] = [
    ("problem", re.compile(r"(원인|문제|배경|현황|이슈|과제|불량|한계)"), "과제·원인 설명 페이지. 원인이나 현상 설명은 C"),
    ("result", re.compile(r"(결과|검증|효과|성능|평가|비교|시험|테스트)"), "결과·효과 페이지. 수치 결과는 B"),
    ("means", re.compile(r"(개선|방안|대책|설계|구조|알고리즘|적용|구현|방법)"), "수단 설명 페이지. 구체적 수단은 A"),
    ("plan", re.compile(r"(계획|향후|로드맵|검토\s*사항|추진)"), "계획 페이지. 예정·검토는 D"),
]
TYPE_KEYS = ["problem", "result", "means", "plan", "general"]
HINT_BY_KEY = {k: h for k, _, h in PAGE_TYPES}


def page_type(title: str) -> tuple[str, str | None]:
    """(유형 키, 힌트 문장 또는 None)"""
    hits = [(k, h) for k, rx, h in PAGE_TYPES if rx.search(title or "")]
    if len(hits) == 1:
        return hits[0]
    return "general", None
