"""골드 세트로 분류기 학습. 임베딩 + 단서어 특성 → 소프트맥스 회귀. 교차검증 정확도를 함께 내고 이력에 남긴다."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path

from ..classify import TrainedClassifier, build_features, cross_validate
from ..config import Config
from ..cues import FEATURE_NAMES
from ..history import History
from ..prep.page_type import page_type
from .score import load_gold


def train_classifier(gold_paths: list[Path], cfg: Config, out: Path, embedder, history: History | None = None) -> dict:
    rows: list[dict] = []
    for g in gold_paths:
        rows.extend(load_gold(g))
    if len(rows) < 20:
        raise ValueError(f"학습에는 정답이 적힌 문장이 최소 20개 필요합니다 (현재 {len(rows)}).")
    texts = [str(r["문장"]) for r in rows]
    y = [r["정답"] for r in rows]
    page_types = [page_type(str(r.get("제목") or ""))[0] for r in rows]
    vectors = embedder.embed(texts)
    X = build_features(vectors, texts, page_types)
    cv = cross_validate(X, y, k=5)
    trained_at = datetime.now().isoformat(timespec="seconds")
    clf = TrainedClassifier.train(X, y, meta={"embed_model": cfg.embed_model, "n": len(y), "features": FEATURE_NAMES,
                                              "trained_at": trained_at, "sources": [p.name for p in gold_paths]})
    preds = clf.predict(vectors, texts, page_types)
    train_acc = sum(p.label == g for p, g in zip(preds, y)) / len(y)
    clf.save(out)
    stats = {"n": len(y), "counts": dict(Counter(y)), "cv_accuracy": cv, "train_accuracy": train_acc, "out": str(out),
             "embed_model": cfg.embed_model, "trained_at": trained_at, "sources": [str(p) for p in gold_paths]}
    (history or History(cfg.history_dir())).log_train(stats)
    return stats
