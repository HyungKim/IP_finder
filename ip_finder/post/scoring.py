"""문장 점수와 검토 목록/보류 결정 (정밀도 우선).

신뢰도(0~1): 판정 주체와 일치 여부로 정한다.
  - 골드 정답 반영(사람이 확정): 1.0, 페이지 가중치와 무관하게 점수 1.0
  - LLM 판정 + 분류기 일치(또는 LLM 재확인 일치): 1.0
  - LLM만 판정(llm 모드): 0.9
  - 분류기만(학습 분류기): 1위 확률
  - 분류기만(제로샷): min(0.9, 0.65 + 유사도 차이)
  - LLM 판정이 분류기와 불일치: 0.65
  - 판정 실패(?): 0
점수 = 신뢰도 × 페이지 가중치. 등급이 A~D 이고 점수 ≥ accept_score 이면 검토 목록, 아니면 보류(사유 기록).
"""
from __future__ import annotations

from ..config import Config
from ..models import LabeledLine

REVIEW_GRADES = ("A", "B", "C", "D")


def confidence(ll: LabeledLine, trained: bool) -> float:
    if ll.source == "gold":
        return 1.0
    if ll.label == "?" or ll.raw_label == "?":
        return 0.0
    if ll.source == "llm":
        if ll.clf_label == "":
            return 0.9
        if "불일치" in ll.notes:
            return 0.65
        return 1.0
    if ll.source == "verified":
        return 1.0
    if ll.clf_conf is None:
        return 0.9
    if trained:
        return max(0.0, min(1.0, ll.clf_top if ll.clf_top is not None else 0.5 + ll.clf_conf / 2))
    return min(0.9, 0.65 + max(0.0, ll.clf_conf))


def apply_scores(labeled: list[LabeledLine], cfg: Config, trained: bool) -> int:
    """confidence, score, hold_reason 을 채운다. 보류로 내려간 행 수를 돌려준다."""
    held = 0
    for ll in labeled:
        ll.page_weight = float(ll.page_weight)
        ll.confidence = round(float(confidence(ll, trained)), 3)
        ll.score = 1.0 if ll.source == "gold" else round(ll.confidence * ll.page_weight, 3)
        ll.hold_reason = ""
        if ll.label in REVIEW_GRADES and ll.score < cfg.accept_score:
            why = []
            if ll.page_weight < 1.0:
                why.append(f"가중치 {ll.page_weight:.2f}")
            if ll.confidence < 1.0:
                why.append(f"신뢰도 {ll.confidence:.2f}")
            ll.hold_reason = f"점수 {ll.score:.2f} < {cfg.accept_score:.2f} (" + ", ".join(why) + ")"
            held += 1
    return held


def in_review_list(ll: LabeledLine) -> bool:
    return ll.label in REVIEW_GRADES and not ll.hold_reason


def in_hold_list(ll: LabeledLine) -> bool:
    return ll.label in ("X?", "?") or (ll.label in REVIEW_GRADES and bool(ll.hold_reason))
