"""1차 분류기의 공통 틀.

모든 분류기는 같은 두 메서드를 가진다.
  fit(batch, labels)   : 학습(학습형만). batch 는 골드 문장들, labels 는 정답 등급.
  predict(batch)       : 문장마다 Prediction(등급, 신뢰도 0~1, 등급별 점수, 1위-2위 차이).
Batch 는 문장·임베딩 벡터(필요한 분류기만)·페이지 유형을 함께 든다. 신뢰도는 '1위 등급이 맞을 확률의 추정'으로 통일해
후처리 점수(신뢰도 × 페이지 가중치)가 분류기 종류와 무관하게 같은 뜻을 갖게 한다."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..models import GRADES

LABELS = list(GRADES)


@dataclass
class Prediction:
    label: str
    confidence: float               # 0~1. 1위 등급이 맞을 확률의 추정 (분류기마다 계산법은 다르지만 뜻은 같다)
    scores: dict[str, float]        # 등급별 점수 (확률, 코사인, 투표 비율 등)
    top: float = 0.0                # 1위 점수
    margin: float = 0.0             # 1위 - 2위 (비고에 표시)


@dataclass
class Batch:
    """분류기 입력 묶음. vectors 는 임베딩이 필요 없는 분류기(cue, ngram)에서는 None."""
    texts: list[str]
    vectors: np.ndarray | None = None
    page_types: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.page_types:
            self.page_types = ["general"] * len(self.texts)
        if self.vectors is not None:
            self.vectors = np.asarray(self.vectors, dtype=np.float32)

    def __len__(self) -> int:
        return len(self.texts)

    def subset(self, idx) -> "Batch":
        idx = list(idx)
        return Batch([self.texts[i] for i in idx], None if self.vectors is None else self.vectors[idx],
                     [self.page_types[i] for i in idx])


def normalize_rows(M: np.ndarray) -> np.ndarray:
    """행마다 길이 1 로 (코사인 유사도 = 내적)."""
    M = np.asarray(M, dtype=np.float32)
    norms = np.linalg.norm(M, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return M / norms


def softmax(logits: np.ndarray) -> np.ndarray:
    z = logits - logits.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def predictions_from_scores(scores: np.ndarray, labels: list[str], confidence: np.ndarray | None = None) -> list[Prediction]:
    """점수 행렬(n × 등급 수)에서 Prediction 목록. confidence 를 주지 않으면 1위 점수를 신뢰도로 쓴다."""
    out = []
    for r, row in enumerate(scores):
        order = np.argsort(-row)
        top = float(row[order[0]])
        second = float(row[order[1]]) if len(order) > 1 else 0.0
        conf = float(confidence[r]) if confidence is not None else top
        out.append(Prediction(labels[int(order[0])], max(0.0, min(1.0, conf)),
                              {l: float(v) for l, v in zip(labels, row)}, top, top - second))
    return out


class Classifier:
    """분류기 기본 클래스. 하위 클래스는 name/label/needs_embedding/trainable 과 fit/predict/_arrays/_restore 를 채운다."""
    name = ""
    label = ""
    needs_embedding = False
    trainable = False

    def __init__(self, cfg=None):
        self.cfg = cfg
        self.labels: list[str] = list(LABELS)
        self.meta: dict = {}

    # ---- 학습·판정 ----
    def fit(self, batch: Batch, y: list[str]) -> None:
        raise NotImplementedError(f"{self.name} 은 학습하지 않는 분류기입니다")

    def predict(self, batch: Batch) -> list[Prediction]:
        raise NotImplementedError

    def prepare(self, embedder) -> None:
        """학습 없이 쓰는 분류기가 실행 전에 필요한 것(원형 문장 임베딩 등)을 준비한다. 기본은 아무것도 안 함."""

    # ---- 저장·복원 (학습형) ----
    def _arrays(self) -> dict[str, np.ndarray]:
        return {}

    def _restore(self, arrays: dict[str, np.ndarray]) -> None:
        pass

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, kind=np.array(self.name), labels=np.array(self.labels),
                 meta=np.array(json.dumps(self.meta, ensure_ascii=False)), **self._arrays())
        return path

    @classmethod
    def load_into(cls, path: Path, cfg=None) -> "Classifier":
        d = np.load(path, allow_pickle=False)
        clf = cls(cfg)
        clf.labels = [str(x) for x in d["labels"]]
        clf.meta = json.loads(str(d["meta"]))
        clf._restore({k: d[k] for k in d.files if k not in ("kind", "labels", "meta")})
        return clf

    def describe(self) -> str:
        """실행 정보에 적는 한 줄."""
        if not self.trainable:
            return f"{self.label} (학습 없음)"
        when = str(self.meta.get("trained_at", ""))[:16].replace("T", " ")
        return f"{self.label} (학습 {when}, {self.meta.get('n', '?')}문장, 골드 {len(self.meta.get('sources', []))}개)"


def label_indices(y: list[str], labels: list[str]) -> np.ndarray:
    idx = {g: i for i, g in enumerate(labels)}
    return np.array([idx[g] for g in y], dtype=np.int64)


def present_labels(y: list[str]) -> list[str]:
    """골드에 나온 등급만, GRADES 순서로."""
    s = set(y)
    return [g for g in LABELS if g in s]
