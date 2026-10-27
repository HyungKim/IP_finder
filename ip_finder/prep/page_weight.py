"""페이지 제목으로 관련성(높음/낮음)과 가중치를 정한다.

두 분류뿐이다. 제목이 '관련성 낮음' 키워드(현황·실적·고객·클레임·영업·회의 등)에 걸리면 낮음(가중치 low_relevance_weight, 기본 0.4),
아니면 높음(1.0). '관련성 높음' 키워드는 낮음보다 우선해 특정 제목을 강제로 높음으로 둔다.
문장 점수 = 판정 신뢰도 × 페이지 가중치이고, 점수가 accept_score 미만이면 검토 목록 대신 보류 시트로 간다.
page_weight_enabled = false 면 모든 페이지가 1.0 이다. 낮음 가중치를 0 으로 두면 낮음 페이지는 아예 판정하지 않는다."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..config import Config

HIGH, LOW = "높음", "낮음"


@dataclass
class PageWeight:
    weight: float
    reason: str       # "낮음 키워드 '현황'" / "높음 키워드 '개선'" / "기본(높음)" / "가중치 끔"
    relevance: str    # 높음 | 낮음


def _compile(patterns: list[str]) -> list[re.Pattern]:
    out = []
    for p in patterns:
        try:
            out.append(re.compile(str(p), re.IGNORECASE))
        except re.error:
            continue
    return out


def page_weight(title: str, cfg: Config) -> PageWeight:
    title = title or ""
    if not cfg.page_weight_enabled:
        return PageWeight(1.0, "가중치 끔", HIGH)
    for rx in _compile(cfg.high_relevance_patterns):
        m = rx.search(title)
        if m:
            return PageWeight(1.0, f"높음 키워드 '{m.group(0).strip()}'", HIGH)
    low = max(0.0, min(1.0, float(cfg.low_relevance_weight)))
    for rx in _compile(cfg.low_relevance_patterns):
        m = rx.search(title)
        if m:
            return PageWeight(low, f"낮음 키워드 '{m.group(0).strip()}'", LOW)
    return PageWeight(1.0, "기본(높음)", HIGH)


def apply_page_weights(doc, cfg: Config) -> None:
    """모든 페이지에 weight / weight_reason / relevance 를 채우고, 가중치 0인 페이지는 제외 처리한다."""
    for page in doc.pages:
        pw = page_weight(page.title, cfg)
        page.weight, page.weight_reason, page.relevance = float(pw.weight), pw.reason, pw.relevance
        if page.excluded_reason is None and pw.weight <= 0.0:
            page.excluded_reason = f"관련성 낮음, 가중치 0 ({pw.reason})"
