"""원형 문장 코사인 분류기(제로샷). 등급마다 미리 적어 둔 예시 문장(prototypes.json)을 임베딩해 두고,
새 문장은 가장 비슷한 예시의 등급으로 판정한다. 학습 데이터가 전혀 없을 때의 출발점.
신뢰도 = min(0.9, 0.65 + (1위 코사인 − 2위 코사인)). 차이가 0 이면 0.65, 0.25 이상이면 0.9 로 상한."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .base import Batch, Classifier, LABELS, Prediction, normalize_rows, predictions_from_scores

PROTOTYPES_PATH = Path(__file__).parent / "prototypes.json"


def load_prototypes(path: Path | None = None) -> dict[str, list[str]]:
    data = json.loads((path or PROTOTYPES_PATH).read_text(encoding="utf-8"))
    return {g: [s for s in data.get(g, [])] for g in LABELS}


class PrototypeClassifier(Classifier):
    name = "proto"
    label = "원형 문장 코사인 (제로샷)"
    needs_embedding = True
    trainable = False

    def __init__(self, cfg=None, prototypes: dict[str, list[str]] | None = None):
        super().__init__(cfg)
        self.prototypes = prototypes or load_prototypes()
        self.labels = [g for g in LABELS if self.prototypes.get(g)]
        self.P: np.ndarray | None = None
        self.proto_labels = np.array([i for i, g in enumerate(self.labels) for _ in self.prototypes[g]])

    def prepare(self, embedder) -> None:
        texts = [s for g in self.labels for s in self.prototypes[g]]
        self.P = normalize_rows(embedder.embed(texts))

    def predict(self, batch: Batch) -> list[Prediction]:
        if len(batch) == 0:
            return []
        if self.P is None:
            raise RuntimeError("원형 문장이 임베딩되지 않았습니다 (prepare(embedder) 먼저)")
        S = normalize_rows(batch.vectors) @ self.P.T                       # n × 원형 수
        scores = np.stack([S[:, self.proto_labels == i].max(axis=1) for i in range(len(self.labels))], axis=1)
        order = np.sort(scores.astype(np.float64), axis=1)
        margin = order[:, -1] - (order[:, -2] if scores.shape[1] > 1 else 0.0)
        conf = np.minimum(0.9, 0.65 + np.maximum(0.0, margin))          # float64: 0.65 가 그대로 0.65 로 남게
        return predictions_from_scores(scores, self.labels, conf)
