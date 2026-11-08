"""교차 검증 도우미. 학습형 분류기를 골드로 채점할 때 '학습에 쓴 문장으로 채점하는' 착시를 피하려고 k 겹으로 나눈다.
층화(stratified): 등급 비율이 겹마다 비슷하게 섞는다. 골드가 적으면 k 를 줄인다."""
from __future__ import annotations

import numpy as np

from .base import Batch, Classifier, Prediction


def stratified_folds(y: list[str], k: int = 5, seed: int = 0) -> list[list[int]]:
    """등급별로 섞어 k 개 겹으로 나눈 인덱스 목록. 표본 수보다 k 가 크면 k 를 줄인다."""
    n = len(y)
    k = max(2, min(k, n))
    rng = np.random.default_rng(seed)
    folds: list[list[int]] = [[] for _ in range(k)]
    for g in sorted(set(y)):
        idx = [i for i in range(n) if y[i] == g]
        rng.shuffle(idx)
        for j, i in enumerate(idx):
            folds[j % k].append(i)
    return [sorted(f) for f in folds if f]


def out_of_fold_predict(clf: Classifier, batch: Batch, y: list[str], k: int = 5, seed: int = 0) -> list[Prediction | None]:
    """각 문장을 자기가 들어가지 않은 겹으로 학습한 분류기로 판정한다. 학습이 불가능한 겹(등급이 하나뿐)은 None."""
    n = len(y)
    out: list[Prediction | None] = [None] * n
    for test in stratified_folds(y, k, seed):
        test_set = set(test)
        train = [i for i in range(n) if i not in test_set]
        if len(set(y[i] for i in train)) < 2:
            continue
        clf.fit(batch.subset(train), [y[i] for i in train])
        for i, pr in zip(test, clf.predict(batch.subset(test))):
            out[i] = pr
    return out


def cv_accuracy(clf: Classifier, batch: Batch, y: list[str], k: int = 5, seed: int = 0) -> float:
    preds = out_of_fold_predict(clf, batch, y, k, seed)
    return sum(1 for p, g in zip(preds, y) if p is not None and p.label == g) / len(y) if y else 0.0
