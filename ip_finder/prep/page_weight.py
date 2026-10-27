"""페이지 제목으로 페이지 가중치(0~1)를 정한다.

가중치는 "이 페이지의 문장이 특허 검토 후보일 가능성"이다. 문장 점수 = 판정 신뢰도 × 페이지 가중치이며,
점수가 accept_score 미만이면 검토 목록 대신 보류 시트로 간다. 가중치 0은 페이지를 아예 판정하지 않는다.

우선순위: 설정의 키워드 규칙(page_weights, 먼저 맞는 것) → 제목 유형별 기본값(page_type_weights, 여러 유형이면 최대) → default_page_weight.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..config import Config
from .page_type import PAGE_TYPES

# 유형별 기본 가중치. 회사 템플릿에 맞게 ip_finder.toml 의 [page_type_weights] 로 바꾼다.
DEFAULT_TYPE_WEIGHTS = {
    "means": 1.0,     # 개선안·설계·구조·알고리즘
    "result": 0.9,    # 결과·검증·효과
    "problem": 0.8,   # 원인·문제·배경
    "plan": 0.75,     # 계획·향후
    "status": 0.4,    # 현황·실적·진행 (기술 내용이 드묾)
    "general": 0.8,   # 유형을 모르는 제목
}


@dataclass
class PageWeight:
    weight: float
    reason: str       # "키워드 '현황'" / "유형 means" / "기본값"


def _rules(cfg: Config) -> list[tuple[re.Pattern, float]]:
    out = []
    for item in cfg.page_weights:
        try:
            pattern, weight = item[0], float(item[1])
        except (TypeError, ValueError, IndexError):
            continue
        out.append((re.compile(str(pattern), re.IGNORECASE), max(0.0, min(1.0, weight))))
    return out


def page_weight(title: str, cfg: Config) -> PageWeight:
    title = title or ""
    for rx, w in _rules(cfg):
        m = rx.search(title)
        if m:
            return PageWeight(w, f"키워드 '{m.group(0).strip()}'")
    type_weights = {**DEFAULT_TYPE_WEIGHTS, **{k: float(v) for k, v in cfg.page_type_weights.items()}}
    hits = [k for k, rx, _ in PAGE_TYPES if rx.search(title)]
    if hits:
        best = max(hits, key=lambda k: type_weights.get(k, type_weights["general"]))
        return PageWeight(type_weights.get(best, type_weights["general"]), "유형 " + "+".join(hits))
    return PageWeight(float(cfg.default_page_weight if cfg.default_page_weight is not None else type_weights["general"]), "기본값")


def apply_page_weights(doc, cfg: Config) -> None:
    """모든 페이지에 weight / weight_reason 을 채우고, 가중치 0인 페이지는 제외 처리한다."""
    for page in doc.pages:
        pw = page_weight(page.title, cfg)
        page.weight, page.weight_reason = float(pw.weight), pw.reason
        if page.excluded_reason is None and pw.weight <= 0.0:
            page.excluded_reason = f"가중치 0 ({pw.reason})"
