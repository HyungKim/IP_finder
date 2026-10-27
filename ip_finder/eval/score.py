"""골드 시트 채점: 등급 정확도(정밀도·재현율·F1, 혼동 행렬)와 **검토 목록 정밀도**.
--stored 가 아니면 현재 모델·프롬프트·가중치·점수 기준으로 다시 판정한다."""
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
    """pairs = [(정답, 예측)]"""
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
    return {"total": total, "correct": correct, "accuracy": correct / total if total else 0.0,
            "per_grade": per, "confusion": {g: dict(conf[g]) for g in LABELS}}


def list_metrics(rows: list[tuple[str, str, float]], accept: float) -> dict:
    """rows = [(정답, 예측 등급, 점수)]. 예측이 A~D 이고 점수 ≥ accept 이면 목록에 든 것으로 본다.
    정밀도(비X) = 목록 중 정답이 X가 아닌 비율, 정밀도(등급) = 목록 중 등급까지 맞은 비율, 재현율 = 정답 비X 중 목록에 든 비율."""
    in_list = [(g, p) for g, p, s in rows if p in ("A", "B", "C", "D") and s >= accept]
    pos = sum(1 for g, _, _ in rows if g != "X")
    n = len(in_list)
    nonx = sum(1 for g, _ in in_list if g != "X")
    exact = sum(1 for g, p in in_list if g == p)
    return {"accept": accept, "list": n, "precision_nonx": nonx / n if n else 0.0, "precision_grade": exact / n if n else 0.0,
            "recall": nonx / pos if pos else 0.0, "positives": pos}


def evaluate(gold_path: Path, cfg: Config, rerun: bool = True, client=None, embedder=None, classifier=None) -> dict:
    rows = load_gold(gold_path)
    if not rows:
        raise ValueError("채점할 행이 없습니다. '정답' 열을 확인하세요.")
    info = RunInfo(source=str(gold_path), model=cfg.model, prompt_version="", started_at="")
    sweep = None
    if rerun:
        from ..pipeline import Services, label_pages
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
        cache = LabelCache(cfg.cache_file() if cfg.use_cache else None)
        try:
            svc = Services(cfg, cache, client=client, embedder=embedder, classifier=classifier)   # 채점에는 골드 반영 없음
            labeled = label_pages(pages, cfg, svc, info)
        finally:
            cache.close()
        if cfg.title_fix:
            apply_title_fix(labeled)
        if cfg.safety_net:
            apply_safety_net(labeled)
        trained = getattr(svc.classifier, "kind", "") == "trained"
        apply_scores(labeled, cfg, trained)
        raw_pairs = [(r["정답"], _norm(ll.raw_label)) for r, ll in zip(order, labeled)]
        final_pairs = [(r["정답"], _norm(ll.label)) for r, ll in zip(order, labeled)]
        triples = [(r["정답"], ll.label, ll.score) for r, ll in zip(order, labeled)]
        source = f"재실행: 모드 {info.mode}, LLM {cfg.model}" + (f", 임베딩 {info.embed_model}, {info.classifier}" if info.embed_model else "")
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
    lm = list_metrics(triples, cfg.accept_score)
    sweep = [list_metrics(triples, a) for a in SWEEP]
    return {"source": source, "rows": len(rows), "raw": score(raw_pairs), "final": score(final_pairs),
            "llm_lines": info.llm_lines, "clf_lines": info.clf_lines, "llm_calls": info.llm_calls,
            "list": lm, "sweep": sweep, "accept_score": cfg.accept_score}


def print_report(rep: dict) -> None:
    print(f"골드 {rep['rows']}문장 / {rep['source']}")
    if rep.get("llm_lines") or rep.get("clf_lines"):
        print(f"  분류기 채택 {rep.get('clf_lines', 0)}문장, LLM 판정 {rep.get('llm_lines', 0)}문장, LLM 호출 {rep.get('llm_calls', 0)}회")
    for name, s in (("모델 라벨", rep["raw"]), ("후처리 후", rep["final"])):
        print(f"\n[{name}] 정확도 {s['correct']}/{s['total']} = {s['accuracy']:.1%}")
        print("  등급  건수  정밀도  재현율   F1")
        for lab in LABELS:
            m = s["per_grade"][lab]
            print(f"  {lab:<4} {m['support']:>4}  {m['precision']:6.1%} {m['recall']:6.1%} {m['f1']:6.1%}")
        print("  혼동 행렬 (행=정답, 열=예측): " + " ".join(f"{l:>3}" for l in LABELS))
        for g in LABELS:
            print(f"    {g:<3} " + " ".join(f"{s['confusion'][g].get(p, 0):>3}" for p in LABELS))
    lm = rep.get("list")
    if lm:
        print(f"\n[검토 목록] 점수 기준 {lm['accept']:.2f}: 목록 {lm['list']}문장 (정답 비X {lm['positives']}문장)")
        print(f"  정밀도(비X) {lm['precision_nonx']:.1%}   정밀도(등급 일치) {lm['precision_grade']:.1%}   재현율 {lm['recall']:.1%}")
        print("  점수 기준별:  기준   목록  정밀도(비X)  정밀도(등급)  재현율")
        for m in rep.get("sweep", []):
            mark = " ◀ 현재" if abs(m["accept"] - lm["accept"]) < 1e-9 else ""
            print(f"               {m['accept']:.2f}  {m['list']:>5}   {m['precision_nonx']:7.1%}      {m['precision_grade']:7.1%}    {m['recall']:6.1%}{mark}")
        print("  정밀도 우선이면 정밀도(비X)가 95% 이상이 되는 가장 낮은 기준을 고르면 됩니다.")
