"""1차 분류기 묶음. 이름(설정 classifier)으로 고르고, 모두 같은 fit/predict 인터페이스(base.Classifier)를 가진다.

| 이름     | 학습 | 임베딩 | 설명 |
| proto    | X    | O     | 원형 문장 코사인(제로샷). 학습 데이터 없이 동작 |
| knn      | O    | O     | 가장 가까운 골드 문장 k 개의 다수결 |
| centroid | O    | O     | 등급별 골드 임베딩 평균과의 코사인 |
| softmax  | O    | O     | 소프트맥스 회귀 (임베딩 + 단서 특성) |
| ovr      | O    | O     | 일대다 로지스틱 (등급마다 독립 시그모이드) |
| cue      | X    | X     | 단서어 정규식 규칙 (기준선) |
| ngram    | O    | X     | 글자 n-gram + 소프트맥스 (임베딩 없음, 기준선) |
기준선 둘(cue, ngram)은 '기계학습·임베딩 없이도 되는가'를 숫자로 보이기 위한 비교 기준이다. 설정 baseline_classifiers = false 면
비교 대상과 UI 선택지에서 빠지고(available_names), classifier 로 직접 고르면 여전히 쓸 수 있다.
"""
from __future__ import annotations

from pathlib import Path

from .base import Batch, Classifier, Prediction, present_labels
from .cue_rules import CueRuleClassifier
from .embed import OllamaEmbedder
from .linear import NgramClassifier, OneVsRestClassifier, SoftmaxClassifier
from .neighbors import CentroidClassifier, KNNClassifier
from .proto import PrototypeClassifier, load_prototypes

REGISTRY: dict[str, type[Classifier]] = {c.name: c for c in (
    PrototypeClassifier, KNNClassifier, CentroidClassifier, SoftmaxClassifier, OneVsRestClassifier,
    CueRuleClassifier, NgramClassifier)}
ORDER = list(REGISTRY)


def build(name: str, cfg=None) -> Classifier:
    if name not in REGISTRY:
        raise ValueError(f"모르는 분류기: {name} (가능: {', '.join(REGISTRY)})")
    return REGISTRY[name](cfg)


def needs_embedding(name: str) -> bool:
    return REGISTRY[name].needs_embedding


def available_names(cfg=None) -> list[str]:
    """비교 대상·UI 선택지에 올릴 분류기 이름. 설정 baseline_classifiers 가 False 면 기준선용(cue, ngram)을 뺀다.
    설정에서 직접 classifier = "cue" 로 고르는 것은 이 목록과 무관하게 늘 된다."""
    include = True if cfg is None else bool(getattr(cfg, "baseline_classifiers", True))
    return [n for n in ORDER if include or not REGISTRY[n].baseline]


def load_classifier(cfg, embedder=None) -> Classifier:
    """설정의 분류기를 쓸 수 있게 만든다. 학습형은 classifier_dir/<이름>.npz 를 읽고 임베딩 모델이 설정과 같은지 확인한다.
    학습 없는 분류기(proto·cue)는 바로 만들고, proto 는 원형 문장을 임베딩한다."""
    name = cfg.classifier
    cls = REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"모르는 분류기: {name} (가능: {', '.join(REGISTRY)})")
    if not cls.trainable:
        clf = cls(cfg)
        if cls.needs_embedding:
            if embedder is None:
                raise ValueError(f"{name} 분류기에는 임베더가 필요합니다")
            clf.prepare(embedder)
        return clf
    path = cfg.classifier_file(name)
    if not path.exists():
        raise FileNotFoundError(f"학습 분류기 파일이 없습니다: {path}\n  → 골드로 먼저 학습: ip-finder train --classifier {name}")
    clf = load_file(path, cfg)
    if clf.name != name:
        raise ValueError(f"{path.name} 은 {clf.name} 분류기 파일입니다 (설정은 {name})")
    trained_embed = clf.meta.get("embed_model")
    if cls.needs_embedding and trained_embed not in (None, cfg.embed_model):
        raise ValueError(f"{path.name} 은 {trained_embed} 임베딩으로 학습됐는데 설정은 {cfg.embed_model} 입니다.")
    return clf


def load_file(path: Path, cfg=None) -> Classifier:
    """npz 파일에 적힌 kind 로 알맞은 클래스를 골라 복원한다."""
    import numpy as np
    kind = str(np.load(path, allow_pickle=False)["kind"])
    cls = REGISTRY.get(kind)
    if cls is None:
        raise ValueError(f"{path} 의 분류기 종류를 모릅니다: {kind}")
    return cls.load_into(path, cfg)


__all__ = ["Batch", "Classifier", "Prediction", "OllamaEmbedder", "REGISTRY", "ORDER", "build", "needs_embedding", "available_names",
           "load_classifier", "load_file", "load_prototypes", "present_labels"]
