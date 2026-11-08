"""단서어 규칙 분류기(기준선). 임베딩도 학습도 없이 정규식만으로 등급을 매긴다.
'기계학습이 정말 필요한가'를 숫자로 보이기 위한 비교 기준이지 실제로 쓰려는 분류기가 아니다.
순서: 비기술 단어 → X, 계획 단어 → D, 변경 동사 → A, 단위·효과 단어 → B, 문제 단어 → C, 나머지 X.
규칙이 걸리면 신뢰도 0.7, 아무 규칙도 안 걸려 X 가 된 경우 0.55."""
from __future__ import annotations

from ..cues import CHANGE_VERBS, EFFECT_RE, NONTECH_RE, PLAN_RE, PROBLEM_RE, UNIT_RE
from .base import Batch, Classifier, LABELS, Prediction


class CueRuleClassifier(Classifier):
    name = "cue"
    label = "단서어 규칙 (기준선)"
    needs_embedding = False
    trainable = False
    baseline = True

    @staticmethod
    def rule(text: str) -> tuple[str, str]:
        """(등급, 걸린 규칙 이름)"""
        if NONTECH_RE.search(text):
            return "X", "비기술 단어"
        if PLAN_RE.search(text):
            return "D", "계획 단어"
        if CHANGE_VERBS.search(text):
            return "A", "변경 동사"
        if UNIT_RE.search(text) or EFFECT_RE.search(text):
            return "B", "단위·효과 단어"
        if PROBLEM_RE.search(text):
            return "C", "문제 단어"
        return "X", ""

    def predict(self, batch: Batch) -> list[Prediction]:
        out = []
        for t in batch.texts:
            label, why = self.rule(t)
            conf = 0.7 if why else 0.55
            scores = {g: (conf if g == label else (1 - conf) / (len(LABELS) - 1)) for g in LABELS}
            out.append(Prediction(label, conf, scores, conf, conf - (1 - conf) / (len(LABELS) - 1)))
        return out
