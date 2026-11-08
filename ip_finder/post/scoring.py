"""문장 점수와 검토 목록/보류 결정 (정밀도 우선).

신뢰도(0~1):
  - 골드 정답 반영(사람이 확정): 1.0, 페이지 가중치와 무관하게 점수 1.0
  - 분류기 판정: 분류기가 낸 신뢰도(1위 등급이 맞을 확률의 추정) 그대로
  - 판정 실패(?): 0
점수 = 신뢰도 × 페이지 가중치. 대상 등급으로 통과(stage_out == 0)하고 점수 ≥ accept_score 이면 검토 목록, 아니면 보류(사유 기록).

문장의 '상태'는 네 가지 중 하나다: 검토 목록 / 보류 / 분류기 제외 / 후처리 제외. (전처리·페이지 규칙에 걸린 줄은 분류기에 가지 않으므로
LabeledLine 이 아니며, Excel '전처리 제외' 시트에 따로 나온다.)"""
from __future__ import annotations

from ..config import Config
from ..models import LabeledLine

REVIEW_GRADES = ("A", "B", "C", "D")
STATUS_REVIEW, STATUS_HOLD, STATUS_CLF_OUT, STATUS_POST_OUT = "검토 목록", "보류", "분류기 제외", "후처리 제외"
STATUS_PREP_OUT, STATUS_PAGE_OUT = "전처리 제외", "페이지 제외"
STATUSES = (STATUS_REVIEW, STATUS_HOLD, STATUS_CLF_OUT, STATUS_POST_OUT, STATUS_PREP_OUT, STATUS_PAGE_OUT)


def confidence(ll: LabeledLine) -> float:
    if ll.source == "gold":
        return 1.0
    if ll.label == "?" or ll.raw_label == "?":
        return 0.0
    if ll.clf_conf is None:
        return 0.9
    return max(0.0, min(1.0, float(ll.clf_conf)))


def apply_scores(labeled: list[LabeledLine], cfg: Config) -> int:
    """confidence, score, hold_reason 을 채운다. 보류로 내려간 행 수를 돌려준다."""
    held = 0
    for ll in labeled:
        ll.page_weight = float(ll.page_weight)
        ll.confidence = round(float(confidence(ll)), 3)
        ll.score = 1.0 if ll.source == "gold" else round(ll.confidence * ll.page_weight, 3)
        ll.hold_reason = ""
        if ll.stage_out == 0 and ll.label in REVIEW_GRADES and ll.score < cfg.accept_score:
            why = []
            if ll.page_weight < 1.0:
                why.append(f"가중치 {ll.page_weight:.2f}")
            if ll.confidence < 1.0:
                why.append(f"신뢰도 {ll.confidence:.2f}")
            ll.hold_reason = f"점수 {ll.score:.2f} < {cfg.accept_score:.2f} (" + ", ".join(why) + ")"
            held += 1
    return held


def in_review_list(ll: LabeledLine) -> bool:
    """검토 목록: 통과 + 대상 등급 + 점수 기준 이상."""
    return ll.stage_out == 0 and ll.label in REVIEW_GRADES and not ll.hold_reason


def in_hold_list(ll: LabeledLine) -> bool:
    """보류: 점수 미달, 판정 실패, 분류기는 X 였지만 기술 단서어가 있는 X?."""
    if ll.stage_out == 0:
        return ll.label in ("X?", "?") or (ll.label in REVIEW_GRADES and bool(ll.hold_reason))
    return ll.stage_out == 1 and ll.label == "X?"


def is_stage1_out(ll: LabeledLine) -> bool:
    """분류기가 대상 등급 밖으로 본 문장 (X? 는 보류로 가므로 제외)."""
    return ll.stage_out == 1 and ll.label != "X?"


def is_stage2_out(ll: LabeledLine) -> bool:
    """분류기는 통과시켰지만 후처리(보정)나 골드가 대상 등급 밖으로 바꾼 문장."""
    return ll.stage_out == 2


def status_of(ll: LabeledLine) -> str:
    if in_review_list(ll):
        return STATUS_REVIEW
    if in_hold_list(ll):
        return STATUS_HOLD
    if is_stage1_out(ll):
        return STATUS_CLF_OUT
    return STATUS_POST_OUT
