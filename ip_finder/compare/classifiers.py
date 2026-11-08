"""1차 분류기 후보를 같은 골드로 비교한다 (compare-classifiers).

학습형(knn, centroid, softmax, ovr, ngram)은 층화 k 겹 교차 검증으로 '자기가 학습에 쓰이지 않은 겹'에서 판정한 결과를 채점하고,
겹 나누기를 seed 를 바꿔 repeats 번 반복해 정확도의 흔들림(표준편차)도 적는다. 학습 없는 것(proto, cue)은 전체 골드를 그대로 채점한다.
임베딩은 한 번만 계산해 모든 분류기가 나눠 쓴다(캐시)."""
from __future__ import annotations

import statistics
import time
from collections import Counter
from dataclasses import dataclass, field

from ..classify import REGISTRY, Batch, available_names, build
from ..classify.cv import out_of_fold_predict
from ..config import Config
from ..eval.score import candidate_metrics, score
from ..prep.page_type import page_type

MIN_TRAIN_ROWS = 10


@dataclass
class ClassifierReport:
    name: str
    label: str
    trainable: bool
    needs_embedding: bool
    n: int = 0
    preds: list = field(default_factory=list)          # 골드 행마다 Prediction (학습형은 교차 검증 밖 판정), 없으면 None
    accuracy: float | None = None
    macro_f1: float | None = None
    per_grade: dict = field(default_factory=dict)
    confusion: dict = field(default_factory=dict)
    candidates: dict = field(default_factory=dict)     # 대상 등급(A·B) 후보의 재현율·정밀도
    repeat_acc: list[float] = field(default_factory=list)
    fit_sec: float = 0.0
    predict_sec: float = 0.0
    skipped: str = ""

    @property
    def acc_std(self) -> float | None:
        return statistics.pstdev(self.repeat_acc) if len(self.repeat_acc) > 1 else None

    def labels(self) -> list[str]:
        return [p.label if p is not None else "?" for p in self.preds]


def compare_classifiers(rows: list[dict], cfg: Config, embedder=None, names: list[str] | None = None, k: int = 5,
                        repeats: int = 2, seed: int = 0, status=None) -> dict:
    names = names or available_names(cfg)          # 기본: 설정 baseline_classifiers 에 따라 기준선(cue, ngram) 포함/제외
    for n in names:
        if n not in REGISTRY:
            raise ValueError(f"모르는 분류기: {n} (가능: {', '.join(REGISTRY)})")
    texts = [str(r["문장"]) for r in rows]
    y = [str(r["정답"]).upper() for r in rows]
    page_types = [page_type(str(r.get("제목") or ""))[0] for r in rows]
    targets = tuple(cfg.targets())
    vectors = None
    embed_error = ""
    embed_sec = 0.0
    if any(REGISTRY[n].needs_embedding for n in names):
        if embedder is None or not embedder.available():
            embed_error = f"임베딩 모델 {cfg.embed_model} 을 쓸 수 없어 건너뜀 (ollama pull {cfg.embed_model})"
        else:
            if status:
                status(f"임베딩 {len(texts)}문장 ({cfg.embed_model})")
            t0 = time.time()
            vectors = embedder.embed(texts)
            embed_sec = time.time() - t0
    batch = Batch(texts, vectors, page_types)
    reports: list[ClassifierReport] = []
    for name in names:
        cls = REGISTRY[name]
        rep = ClassifierReport(name, cls.label, cls.trainable, cls.needs_embedding, n=len(y))
        reports.append(rep)
        if cls.needs_embedding and vectors is None:
            rep.skipped = embed_error
            continue
        if status:
            status(f"분류기 {cls.label} 채점")
        if cls.trainable:
            if len(y) < MIN_TRAIN_ROWS or len(set(y)) < 2:
                rep.skipped = f"학습형은 정답 문장 {MIN_TRAIN_ROWS}개 이상, 등급 2종 이상 필요 (현재 {len(y)}개)"
                continue
            t0 = time.time()
            first = None
            for r in range(max(1, repeats)):
                preds = out_of_fold_predict(build(name, cfg), batch, y, k, seed + r)
                rep.repeat_acc.append(sum(1 for p, g in zip(preds, y) if p is not None and p.label == g) / len(y))
                if first is None:
                    first = preds
            rep.fit_sec = time.time() - t0
            rep.preds = first or []
        else:
            clf = build(name, cfg)
            if cls.needs_embedding:
                clf.prepare(embedder)
            t0 = time.time()
            rep.preds = clf.predict(batch)
            rep.predict_sec = time.time() - t0
        pairs = [(g, p.label if p is not None else "?") for p, g in zip(rep.preds, y)]
        s = score(pairs)
        rep.accuracy, rep.macro_f1, rep.per_grade, rep.confusion = s["accuracy"], s["macro_f1"], s["per_grade"], s["confusion"]
        rep.candidates = candidate_metrics(pairs, targets)
    return {"reports": reports, "texts": texts, "y": y, "n": len(y), "k": k, "repeats": repeats, "seed": seed,
            "embed_model": cfg.embed_model if vectors is not None else "", "embed_sec": embed_sec, "embed_error": embed_error,
            "targets": "".join(targets), "gold_counts": dict(Counter(y)), "titles": [str(r.get("제목") or "") for r in rows],
            "files": sorted({str(r.get("파일") or "") for r in rows})}
