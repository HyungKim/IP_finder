"""문장 등급 분류기 두 종류.
- ZeroShotClassifier: 학습 데이터 없이 등급별 원형 문장(prototypes.json)과의 코사인 유사도로 판정. 확신 = 1위-2위 유사도 차이.
- TrainedClassifier: 골드 세트로 학습한 소프트맥스 회귀. 입력은 임베딩 + 단서어 특성 13개. 확신 = 1위-2위 확률 차이.
두 클래스는 같은 predict(vectors, texts, page_types) 인터페이스를 가진다."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..config import Config
from ..cues import FEATURE_NAMES, cue_features

GRADES = ["A", "B", "C", "D", "X"]
PROTOTYPES_PATH = Path(__file__).parent / "prototypes.json"


@dataclass
class Prediction:
    label: str
    confidence: float               # 1위 - 2위
    scores: dict[str, float]
    top: float = 0.0                # 1위 점수 (학습 분류기는 확률, 제로샷은 코사인 유사도)


def _normalize(M: np.ndarray) -> np.ndarray:
    M = np.asarray(M, dtype=np.float32)
    norms = np.linalg.norm(M, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return M / norms


def load_prototypes(path: Path | None = None) -> dict[str, list[str]]:
    data = json.loads((path or PROTOTYPES_PATH).read_text(encoding="utf-8"))
    return {g: [s for s in data.get(g, [])] for g in GRADES}


def build_features(vectors: list[list[float]], texts: list[str], page_types: list[str]) -> np.ndarray:
    V = np.asarray(vectors, dtype=np.float32)
    F = np.asarray([cue_features(t, pt) for t, pt in zip(texts, page_types)], dtype=np.float32)
    return np.hstack([V, F])


def _predictions(scores: np.ndarray, labels: list[str]) -> list[Prediction]:
    out = []
    for row in scores:
        order = np.argsort(-row)
        top, second = float(row[order[0]]), float(row[order[1]]) if len(order) > 1 else 0.0
        out.append(Prediction(labels[int(order[0])], top - second, {l: float(v) for l, v in zip(labels, row)}, top))
    return out


class ZeroShotClassifier:
    kind = "zero-shot"

    def __init__(self, embedder, prototypes: dict[str, list[str]]):
        self.labels = [g for g in GRADES if prototypes.get(g)]
        texts = [s for g in self.labels for s in prototypes[g]]
        self.proto_labels = np.array([i for i, g in enumerate(self.labels) for _ in prototypes[g]])
        self.P = _normalize(embedder.embed(texts))

    def predict(self, vectors, texts=None, page_types=None) -> list[Prediction]:
        if len(vectors) == 0:
            return []
        S = _normalize(vectors) @ self.P.T                      # n × 원형 수
        scores = np.stack([S[:, self.proto_labels == i].max(axis=1) for i in range(len(self.labels))], axis=1)
        return _predictions(scores, self.labels)


class TrainedClassifier:
    kind = "trained"

    def __init__(self, W: np.ndarray, b: np.ndarray, mu: np.ndarray, sigma: np.ndarray, labels: list[str], meta: dict):
        self.W, self.b, self.mu, self.sigma, self.labels, self.meta = W, b, mu, sigma, labels, meta

    def _proba(self, X: np.ndarray) -> np.ndarray:
        Z = (X - self.mu) / self.sigma
        logits = Z @ self.W.T + self.b
        logits -= logits.max(axis=1, keepdims=True)
        P = np.exp(logits)
        return P / P.sum(axis=1, keepdims=True)

    def predict(self, vectors, texts, page_types) -> list[Prediction]:
        if len(vectors) == 0:
            return []
        return _predictions(self._proba(build_features(vectors, texts, page_types)), self.labels)

    @classmethod
    def train(cls, X: np.ndarray, y: list[str], labels: list[str] | None = None, *, l2: float = 1e-3,
              epochs: int = 600, lr: float = 0.2, meta: dict | None = None) -> "TrainedClassifier":
        labels = labels or [g for g in GRADES if g in set(y)]
        idx = {g: i for i, g in enumerate(labels)}
        Y = np.zeros((len(y), len(labels)), dtype=np.float32)
        for r, g in enumerate(y):
            Y[r, idx[g]] = 1.0
        mu = X.mean(axis=0)
        sigma = X.std(axis=0) + 1e-6
        Z = (X - mu) / sigma
        W = np.zeros((len(labels), X.shape[1]), dtype=np.float32)
        b = np.zeros(len(labels), dtype=np.float32)
        n = len(y)
        for _ in range(epochs):
            logits = Z @ W.T + b
            logits -= logits.max(axis=1, keepdims=True)
            P = np.exp(logits)
            P /= P.sum(axis=1, keepdims=True)
            G = P - Y
            W -= lr * (G.T @ Z / n + l2 * W)
            b -= lr * G.mean(axis=0)
        return cls(W, b, mu, sigma, labels, meta or {})

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, W=self.W, b=self.b, mu=self.mu, sigma=self.sigma, labels=np.array(self.labels),
                 meta=np.array(json.dumps(self.meta, ensure_ascii=False)))

    @classmethod
    def load(cls, path: Path) -> "TrainedClassifier":
        d = np.load(path, allow_pickle=False)
        return cls(d["W"], d["b"], d["mu"], d["sigma"], [str(x) for x in d["labels"]], json.loads(str(d["meta"])))


def cross_validate(X: np.ndarray, y: list[str], k: int = 5, seed: int = 0) -> float:
    """k겹 교차검증 정확도. 표본이 적으면 k를 줄인다."""
    n = len(y)
    k = max(2, min(k, n))
    rng = np.random.default_rng(seed)
    order = rng.permutation(n)
    folds = np.array_split(order, k)
    labels = [g for g in GRADES if g in set(y)]
    hit = 0
    for f in folds:
        test = set(int(i) for i in f)
        tr = [i for i in range(n) if i not in test]
        if len(set(y[i] for i in tr)) < 2:
            continue
        clf = TrainedClassifier.train(X[tr], [y[i] for i in tr], labels)
        P = clf._proba(X[list(test)])
        hit += sum(labels[int(np.argmax(P[j]))] == y[i] for j, i in enumerate(test))
    return hit / n


def load_classifier(cfg: Config, embedder):
    """학습된 분류기 파일이 있으면 그것을, 없으면 원형 문장 제로샷을 돌려준다."""
    path = cfg.classifier_file()
    if path.exists():
        clf = TrainedClassifier.load(path)
        if clf.meta.get("embed_model") not in (None, cfg.embed_model):
            raise ValueError(f"분류기는 {clf.meta.get('embed_model')} 임베딩으로 학습됐는데 설정은 {cfg.embed_model}입니다.")
        return clf
    return ZeroShotClassifier(embedder, load_prototypes())
