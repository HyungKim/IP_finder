"""선형 분류기 두 종류. 둘 다 경사하강법으로 학습하고 numpy 만 쓴다.
- SoftmaxClassifier: 소프트맥스 회귀(다항 로지스틱). 등급 전체에 걸친 확률 분포 하나를 낸다. 입력 = 임베딩 + 단서 특성, 표준화.
- OneVsRestClassifier: 일대다 로지스틱. 등급마다 '이 등급이냐 아니냐' 시그모이드를 따로 두어 어느 등급에도 확신이 없으면 전부 낮게 나온다.
- NgramClassifier: 임베딩 없이 글자 n-gram 특성으로 소프트맥스 회귀. 임베딩이 꼭 필요한지 보는 비교 기준."""
from __future__ import annotations

import numpy as np

from .base import Batch, Classifier, Prediction, label_indices, predictions_from_scores, present_labels, softmax
from .features import ngram_matrix, with_cues


def _standardize_fit(X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mu = X.mean(axis=0)
    sigma = X.std(axis=0) + 1e-6
    return mu.astype(np.float32), sigma.astype(np.float32)


def train_softmax(Z: np.ndarray, y_idx: np.ndarray, k: int, *, l2: float, epochs: int, lr: float) -> tuple[np.ndarray, np.ndarray]:
    """교차 엔트로피 + L2 를 경사하강법으로. Z 는 이미 표준화(또는 정규화)된 입력."""
    n, d = Z.shape
    Y = np.zeros((n, k), dtype=np.float32)
    Y[np.arange(n), y_idx] = 1.0
    W = np.zeros((k, d), dtype=np.float32)
    b = np.zeros(k, dtype=np.float32)
    for _ in range(epochs):
        P = softmax(Z @ W.T + b)
        G = P - Y
        W -= lr * (G.T @ Z / n + l2 * W)
        b -= lr * G.mean(axis=0)
    return W, b


def train_logistic_ovr(Z: np.ndarray, y_idx: np.ndarray, k: int, *, l2: float, epochs: int, lr: float) -> tuple[np.ndarray, np.ndarray]:
    """등급마다 독립된 이진 로지스틱 회귀. 출력은 등급별 시그모이드(합이 1 이 아님)."""
    n, d = Z.shape
    Y = np.zeros((n, k), dtype=np.float32)
    Y[np.arange(n), y_idx] = 1.0
    W = np.zeros((k, d), dtype=np.float32)
    b = np.zeros(k, dtype=np.float32)
    for _ in range(epochs):
        P = 1.0 / (1.0 + np.exp(-(Z @ W.T + b)))
        G = P - Y
        W -= lr * (G.T @ Z / n + l2 * W)
        b -= lr * G.mean(axis=0)
    return W, b


class _LinearBase(Classifier):
    trainable = True
    l2 = 1e-3
    epochs = 600
    lr = 0.2
    standardize = True

    def __init__(self, cfg=None):
        super().__init__(cfg)
        self.W = self.b = self.mu = self.sigma = None

    def features(self, batch: Batch) -> np.ndarray:
        raise NotImplementedError

    def _trainer(self):
        raise NotImplementedError

    def _z(self, X: np.ndarray) -> np.ndarray:
        return (X - self.mu) / self.sigma if self.standardize else X

    def fit(self, batch: Batch, y: list[str]) -> None:
        X = self.features(batch)
        self.labels = present_labels(y)
        if self.standardize:
            self.mu, self.sigma = _standardize_fit(X)
        else:
            self.mu, self.sigma = np.zeros(X.shape[1], np.float32), np.ones(X.shape[1], np.float32)
        self.W, self.b = self._trainer()(self._z(X), label_indices(y, self.labels), len(self.labels),
                                         l2=self.l2, epochs=self.epochs, lr=self.lr)

    def _scores(self, batch: Batch) -> np.ndarray:
        raise NotImplementedError

    def predict(self, batch: Batch) -> list[Prediction]:
        if len(batch) == 0:
            return []
        if self.W is None:
            raise RuntimeError(f"{self.name}: 학습되지 않은 분류기 (ip-finder train --classifier {self.name})")
        return predictions_from_scores(self._scores(batch), self.labels)

    def _arrays(self):
        return {"W": self.W, "b": self.b, "mu": self.mu, "sigma": self.sigma}

    def _restore(self, a):
        self.W, self.b, self.mu, self.sigma = a["W"], a["b"], a["mu"], a["sigma"]


class SoftmaxClassifier(_LinearBase):
    name = "softmax"
    label = "소프트맥스 회귀"
    needs_embedding = True

    def features(self, batch: Batch) -> np.ndarray:
        return with_cues(batch.vectors, batch.texts, batch.page_types)

    def _trainer(self):
        return train_softmax

    def _scores(self, batch: Batch) -> np.ndarray:
        return softmax(self._z(self.features(batch)) @ self.W.T + self.b)      # 확률 → 신뢰도 = 1위 확률


class OneVsRestClassifier(_LinearBase):
    name = "ovr"
    label = "일대다 로지스틱"
    needs_embedding = True

    def features(self, batch: Batch) -> np.ndarray:
        return with_cues(batch.vectors, batch.texts, batch.page_types)

    def _trainer(self):
        return train_logistic_ovr

    def _scores(self, batch: Batch) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-(self._z(self.features(batch)) @ self.W.T + self.b)))   # 등급별 시그모이드. 모두 낮으면 '모름'에 가깝다


class NgramClassifier(_LinearBase):
    name = "ngram"
    label = "글자 n-gram + 소프트맥스 (기준선)"
    needs_embedding = False
    baseline = True
    standardize = False          # 희소한 n-gram 수치를 표준화하면 드문 n-gram 이 과대해진다. 길이 1 정규화만 쓴다
    lr = 0.5
    epochs = 400
    l2 = 1e-4

    def features(self, batch: Batch) -> np.ndarray:
        return ngram_matrix(batch.texts)

    def _trainer(self):
        return train_softmax

    def _scores(self, batch: Batch) -> np.ndarray:
        return softmax(self.features(batch) @ self.W.T + self.b)
