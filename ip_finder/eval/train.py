"""골드 세트로 학습형 분류기(knn, centroid, softmax, ovr, ngram)를 학습해 classifier_dir/<이름>.npz 로 저장한다.
교차 검증 정확도를 함께 내고 이력에 남긴다. 임베딩이 필요한 분류기는 골드 문장을 먼저 임베딩한다(캐시 사용)."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path

from ..classify import REGISTRY, Batch, build
from ..classify.cv import cv_accuracy
from ..config import Config
from ..history import History
from ..prep.page_type import page_type
from ..goldmap import load_gold

MIN_ROWS = 20


def gold_batch(rows: list[dict], embedder=None, need_embedding: bool = True) -> tuple[Batch, list[str]]:
    """골드 행 → (Batch, 정답). 제목으로 페이지 유형을 복원한다."""
    texts = [str(r["문장"]) for r in rows]
    y = [r["정답"] for r in rows]
    page_types = [page_type(str(r.get("제목") or ""))[0] for r in rows]
    vectors = embedder.embed(texts) if need_embedding else None
    return Batch(texts, vectors, page_types), y


def train_classifier(gold_paths: list[Path], cfg: Config, out: Path | None = None, embedder=None,
                     history: History | None = None, name: str | None = None) -> dict:
    name = name or cfg.classifier
    cls = REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"모르는 분류기: {name}")
    if not cls.trainable:
        raise ValueError(f"{name} 은 학습하지 않는 분류기입니다 (proto, cue 는 그냥 쓰면 됩니다)")
    rows: list[dict] = []
    for g in gold_paths:
        rows.extend(load_gold(g))
    if len(rows) < MIN_ROWS:
        raise ValueError(f"학습에는 정답이 적힌 문장이 최소 {MIN_ROWS}개 필요합니다 (현재 {len(rows)}).")
    if cls.needs_embedding and embedder is None:
        raise ValueError(f"{name} 분류기 학습에는 임베더가 필요합니다")
    batch, y = gold_batch(rows, embedder, cls.needs_embedding)
    cv = cv_accuracy(build(name, cfg), batch, y, k=5)
    trained_at = datetime.now().isoformat(timespec="seconds")
    clf = build(name, cfg)
    clf.fit(batch, y)
    clf.meta = {"embed_model": cfg.embed_model if cls.needs_embedding else None, "n": len(y), "trained_at": trained_at,
                "sources": [p.name for p in gold_paths], "counts": dict(Counter(y))}
    preds = clf.predict(batch)
    train_acc = sum(p.label == g for p, g in zip(preds, y)) / len(y)
    out = out or cfg.classifier_file(name)
    clf.save(out)
    stats = {"classifier": name, "n": len(y), "counts": dict(Counter(y)), "cv_accuracy": cv, "train_accuracy": train_acc,
             "out": str(out), "embed_model": clf.meta["embed_model"], "trained_at": trained_at, "sources": [str(p) for p in gold_paths]}
    (history or History(cfg.history_dir())).log_train(stats)
    return stats
