"""골드 시트 채점: 등급 정확도(정밀도·재현율·F1, 혼동 행렬)와 **검토 목록 정밀도·재현율**.
rerun=True 면 골드 문장을 현재 설정의 분류기·후처리·가중치·점수 기준으로 다시 판정해 채점한다 (골드 정답 반영은 끈다)."""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from ..cache import LabelCache
from ..config import Config
from ..goldmap import GOLD_HEADERS, LABELS, load_gold, norm_label as _norm
from ..models import Line, Page, RunInfo
from ..post import apply_safety_net, apply_scores, apply_title_fix, in_review_list
from ..prep.page_weight import page_weight

SWEEP = (0.3, 0.4, 0.5, 0.6, 0.7, 0.8)


def score(pairs: list[tuple[str, str]]) -> dict:
    """pairs = [(정답, 예측)]. 정확도, 등급별 정밀도·재현율·F1, 거시 F1, 혼동 행렬."""
    total = len(pairs)
    correct = sum(1 for g, p in pairs if g == p)
    conf: dict[str, Counter] = defaultdict(Counter)
    for g, p in pairs:
        conf[g][p] += 1
    per = {}
    for lab in LABELS:
        tp = conf[lab][lab]
        fn = sum(conf[lab].values()) - tp
        fp = sum(conf[g][lab] for g in LABELS if g != lab)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        per[lab] = {"support": tp + fn, "precision": prec, "recall": rec, "f1": f1}
    present = [lab for lab in LABELS if per[lab]["support"]]
    macro_f1 = sum(per[lab]["f1"] for lab in present) / len(present) if present else 0.0
    return {"total": total, "correct": correct, "accuracy": correct / total if total else 0.0, "macro_f1": macro_f1,
            "per_grade": per, "confusion": {g: dict(conf[g]) for g in LABELS}}


def candidate_metrics(pairs: list[tuple[str, str]], targets: tuple[str, ...] = ("A", "B")) -> dict:
    """pairs = [(정답, 예측)]. 예측이 대상 등급이면 '후보'. 재현율 = 정답이 대상인 문장 중 후보가 된 비율, 정밀도 = 후보 중 정답이 대상인 비율."""
    pos = sum(1 for g, _ in pairs if g in targets)
    cand = [(g, p) for g, p in pairs if p in targets]
    hit = sum(1 for g, _ in cand if g in targets)
    return {"positives": pos, "candidates": len(cand), "hits": hit,
            "recall": hit / pos if pos else 0.0, "precision": hit / len(cand) if cand else 0.0, "targets": "".join(targets)}


def list_metrics(rows: list[tuple[str, str, float]], accept: float, targets: tuple[str, ...] = ("A", "B")) -> dict:
    """rows = [(정답, 예측 등급, 점수)]. 예측이 대상 등급이고 점수 ≥ accept 이면 목록에 든 것으로 본다."""
    in_list = [(g, p) for g, p, s in rows if p in targets and s >= accept]
    pos = sum(1 for g, _, _ in rows if g in targets)
    n = len(in_list)
    hit = sum(1 for g, _ in in_list if g in targets)
    exact = sum(1 for g, p in in_list if g == p)
    return {"accept": accept, "list": n, "precision_nonx": hit / n if n else 0.0, "precision_grade": exact / n if n else 0.0,
            "recall": hit / pos if pos else 0.0, "positives": pos, "targets": "".join(targets)}


def pages_from_gold(rows: list[dict], cfg: Config) -> tuple[list[Page], list[dict]]:
    """골드 행을 (파일, 페이지) 묶음으로 가짜 Page 로 만든다. 제목으로 가중치를 복원한다."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r.get("파일"), r.get("페이지"))].append(r)
    pages, order = [], []
    for n, ((_, pno), grp) in enumerate(groups.items(), 1):
        grp.sort(key=lambda r: int(r.get("줄") or 0))
        lines = [Line(idx=i, text=str(r["문장"])) for i, r in enumerate(grp, 1)]
        title = str(grp[0].get("제목") or "")
        pw = page_weight(title, cfg)
        pages.append(Page(no=n, title=title, lines=lines, weight=pw.weight, weight_reason=pw.reason, relevance=pw.relevance))
        order.extend(grp)
    return pages, order


def evaluate(gold_path: Path, cfg: Config, rerun: bool = True, embedder=None, classifier=None) -> dict:
    rows = load_gold(gold_path)
    if not rows:
        raise ValueError("채점할 행이 없습니다. '정답' 열을 확인하세요.")
    info = RunInfo(source=str(gold_path), started_at="")
    if rerun:
        from ..pipeline import Services, classify_lines, finalize_stages
        pages, order = pages_from_gold(rows, cfg)
        cache = LabelCache(cfg.cache_file() if cfg.use_cache else None)
        try:
            svc = Services(cfg, cache, embedder=embedder, classifier=classifier)   # 채점에는 골드 반영 없음
            labeled = classify_lines(pages, cfg, svc, info)
        finally:
            cache.close()
        if cfg.title_fix:
            apply_title_fix(labeled)
        if cfg.safety_net:
            apply_safety_net(labeled)
        finalize_stages(labeled, cfg)
        apply_scores(labeled, cfg)
        raw_pairs = [(r["정답"], _norm(ll.raw_label)) for r, ll in zip(order, labeled)]
        final_pairs = [(r["정답"], _norm(ll.label)) for r, ll in zip(order, labeled)]
        triples = [(r["정답"], ll.label if in_review_list(ll) or ll.stage_out == 0 else "X", ll.score) for r, ll in zip(order, labeled)]
        source = f"재실행: 분류기 {info.classifier}" + (f", 임베딩 {info.embed_model}" if info.embed_model else "")
        source += f", 페이지 가중치 {'켬' if cfg.page_weight_enabled else '끔'}"
    else:
        raw_pairs = [(r["정답"], _norm(r.get("모델 라벨"))) for r in rows]
        final_pairs = [(r["정답"], _norm(r.get("후처리 라벨"))) for r in rows]
        triples = []
        for r in rows:
            try:
                s = float(r.get("점수")) if r.get("점수") not in (None, "") else 1.0
            except (TypeError, ValueError):
                s = 1.0
            triples.append((r["정답"], str(r.get("후처리 라벨") or "").strip().upper(), s))
        source = "시트에 저장된 라벨"
    tg = tuple(cfg.targets())
    lm = list_metrics(triples, cfg.accept_score, tg)
    sweep = [list_metrics(triples, a, tg) for a in SWEEP]
    return {"source": source, "rows": len(rows), "raw": score(raw_pairs), "final": score(final_pairs),
            "candidates": candidate_metrics(raw_pairs, tg), "clf_lines": info.clf_lines,
            "list": lm, "sweep": sweep, "accept_score": cfg.accept_score}


def print_report(rep: dict) -> None:
    print(f"골드 {rep['rows']}문장 / {rep['source']}")
    for name, s in (("분류기 라벨", rep["raw"]), ("후처리 후", rep["final"])):
        print(f"\n[{name}] 정확도 {s['correct']}/{s['total']} = {s['accuracy']:.1%}  거시 F1 {s['macro_f1']:.1%}")
        print("  등급  건수  정밀도  재현율   F1")
        for lab in LABELS:
            m = s["per_grade"][lab]
            print(f"  {lab:<4} {m['support']:>4}  {m['precision']:6.1%} {m['recall']:6.1%} {m['f1']:6.1%}")
        print("  혼동 행렬 (행=정답, 열=예측): " + " ".join(f"{l:>3}" for l in LABELS))
        for g in LABELS:
            print(f"    {g:<3} " + " ".join(f"{s['confusion'][g].get(p, 0):>3}" for p in LABELS))
    cm = rep.get("candidates")
    if cm:
        print(f"\n[후보(분류기가 {cm['targets']} 로 본 문장)] 재현율 {cm['recall']:.1%} ({cm['hits']}/{cm['positives']})  정밀도 {cm['precision']:.1%} ({cm['hits']}/{cm['candidates']})")
    lm = rep.get("list")
    if lm:
        print(f"\n[검토 목록] 추출 등급 {lm.get('targets', 'AB')}, 점수 기준 {lm['accept']:.2f}: 목록 {lm['list']}문장 (정답이 대상 등급인 문장 {lm['positives']})")
        print(f"  정밀도(대상 등급) {lm['precision_nonx']:.1%}   정밀도(등급 일치) {lm['precision_grade']:.1%}   재현율 {lm['recall']:.1%}")
        print("  점수 기준별:  기준   목록  정밀도(대상)  정밀도(등급)  재현율")
        for m in rep.get("sweep", []):
            mark = " ◀ 현재" if abs(m["accept"] - lm["accept"]) < 1e-9 else ""
            print(f"               {m['accept']:.2f}  {m['list']:>5}   {m['precision_nonx']:7.1%}      {m['precision_grade']:7.1%}    {m['recall']:6.1%}{mark}")
