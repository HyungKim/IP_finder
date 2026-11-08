"""골드 문장의 임베딩을 그대로 기억해 쓰는 분류기 둘. 학습이 빠르고(저장만 한다) 골드가 늘면 바로 반영된다.
- KNNClassifier: 가장 가까운 k 개 골드 문장이 많이 가진 등급. 신뢰도 = 1위 등급의 (유사도 가중) 투표 비율.
- CentroidClassifier: 등급마다 골드 임베딩의 평균 벡터를 두고 가장 가까운 평균의 등급. 신뢰도 = 코사인에 소프트맥스(온도 20)를 씌운 확률."""
from __future__ import annotations

import numpy as np

from .base import Batch, Classifier, Prediction, label_indices, normalize_rows, predictions_from_scores, present_labels, softmax


class KNNClassifier(Classifier):
    name = "knn"
    label = "최근접 이웃 k-NN"
    needs_embedding = True
    trainable = True

    def __init__(self, cfg=None):
        super().__init__(cfg)
        self.k = int(getattr(cfg, "knn_k", 5) or 5)
        self.X: np.ndarray | None = None
        self.y_idx: np.ndarray | None = None

    def fit(self, batch: Batch, y: list[str]) -> None:
        self.labels = present_labels(y)
        self.X = normalize_rows(batch.vectors)
        self.y_idx = label_indices(y, self.labels)
        self.meta["k"] = self.k

    def predict(self, batch: Batch) -> list[Prediction]:
        if len(batch) == 0:
            return []
        if self.X is None:
            raise RuntimeError("knn: 학습되지 않은 분류기 (ip-finder train --classifier knn)")
        k = max(1, min(self.k, len(self.y_idx)))
        S = normalize_rows(batch.vectors) @ self.X.T                       # n × 골드 수 (코사인)
        scores = np.zeros((len(batch), len(self.labels)), dtype=np.float32)
        for r in range(len(batch)):
            nn = np.argpartition(-S[r], k - 1)[:k]
            w = np.maximum(S[r, nn], 1e-6)                                 # 유사도 가중 투표 (음수는 거의 없지만 바닥을 둔다)
            for j, wt in zip(self.y_idx[nn], w):
                scores[r, j] += wt
            scores[r] /= scores[r].sum()                                   # 투표 비율 → 확률처럼 읽힌다
        return predictions_from_scores(scores, self.labels)

    def _arrays(self):
        return {"X": self.X, "y_idx": self.y_idx}

    def _restore(self, a):
        self.X, self.y_idx = a["X"], a["y_idx"]
        self.k = int(self.meta.get("k", self.k))


class CentroidClassifier(Classifier):
    name = "centroid"
    label = "등급 평균 벡터"
    needs_embedding = True
    trainable = True
    temperature = 20.0           # 코사인 차이(0.05 단위)가 확률 차이로 보이도록 키우는 배수

    def __init__(self, cfg=None):
        super().__init__(cfg)
        self.C: np.ndarray | None = None

    def fit(self, batch: Batch, y: list[str]) -> None:
        self.labels = present_labels(y)
        X = normalize_rows(batch.vectors)
        idx = label_indices(y, self.labels)
        self.C = normalize_rows(np.stack([X[idx == i].mean(axis=0) for i in range(len(self.labels))]))

    def predict(self, batch: Batch) -> list[Prediction]:
        if len(batch) == 0:
            return []
        if self.C is None:
            raise RuntimeError("centroid: 학습되지 않은 분류기 (ip-finder train --classifier centroid)")
        sims = normalize_rows(batch.vectors) @ self.C.T
        probs = softmax(sims * self.temperature)
        return predictions_from_scores(sims, self.labels, probs.max(axis=1))

    def _arrays(self):
        return {"C": self.C}

    def _restore(self, a):
        self.C = a["C"]
