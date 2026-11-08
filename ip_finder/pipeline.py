"""한 파일의 처리 흐름 (0단계: 분류기만).

  읽기(레이아웃 스위치) → 전처리(줄·페이지 규칙 스위치) → 임베딩(필요한 분류기만) → 1차 분류기 → 후처리(보정·안전망 스위치)
  → 골드 반영 → 단계 확정 → 점수(신뢰도 × 가중치) → 이력 저장 → Excel

CLI, UI, 실험 명령(run-all, ladder, compare-*)이 모두 이 모듈의 run_file / extract 를 쓴다."""
from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import __version__
from .cache import LabelCache
from .cancel import CancelToken
from .classify import Batch, OllamaEmbedder, load_classifier, needs_embedding
from .config import Config
from .goldmap import GoldMap
from .history import History, change_rows, diff_runs, file_hash, make_run_id, settings_diff, text_hash
from .models import Document, LabeledLine, Page, RunInfo
from .ollama import OllamaError
from .post import apply_safety_net, apply_scores, apply_title_fix, assign_sections, in_review_list
from .prep import LOW, apply_line_rules, apply_page_rules, apply_page_weights, number_lines
from .prep.page_rules import IMAGE_PAGE
from .prep.page_type import page_type
from .readers import SUPPORTED, load_document
from .report import write_report
from .switches import switch_state

Progress = Callable[[int, int, Page], None]
Status = Callable[[str], None]


@dataclass
class Result:
    doc: Document
    labeled: list[LabeledLine]
    info: RunInfo
    removed: Counter
    changes: list[dict] = field(default_factory=list)   # 직전 실행 대비 변경 행 (Excel '변경 사항')


@dataclass
class Services:
    """임베더와 분류기를 필요할 때만 만든다. 테스트와 실험 명령은 만들어 둔 객체를 넣어 재사용한다."""
    cfg: Config
    cache: LabelCache
    embedder: object | None = None
    classifier: object | None = None
    gold: GoldMap | None = None      # 골드 정답 반영. None 이면 반영하지 않음 (채점, 골드 시트 생성, 실험)
    cancel: CancelToken | None = None   # UI 중지 버튼. 등록된 임베더의 요청을 즉시 끊는다

    def __post_init__(self):
        if self.cancel is not None:
            self.cancel.register(self.embedder)

    def check_cancel(self) -> None:
        if self.cancel is not None:
            self.cancel.check()

    def ensure_classifier(self) -> None:
        """설정의 분류기를 준비한다. 임베딩이 필요한데 모델이 없으면 OllamaError, 학습 파일이 없으면 FileNotFoundError."""
        if self.classifier is not None:
            return
        if needs_embedding(self.cfg.classifier):
            if self.embedder is None:
                self.embedder = make_embedder(self.cfg, self.cache)
                if self.cancel is not None:
                    self.cancel.register(self.embedder)
            if not self.embedder.available():
                raise OllamaError(f"임베딩 모델 {self.cfg.embed_model} 을 쓸 수 없습니다 (ollama pull {self.cfg.embed_model})")
        self.classifier = load_classifier(self.cfg, self.embedder)


def make_embedder(cfg: Config, cache: LabelCache | None = None) -> OllamaEmbedder:
    return OllamaEmbedder(cfg.host, cfg.embed_model, timeout_sec=cfg.timeout_sec, keep_alive=cfg.keep_alive, cache=cache)


def output_path(src: Path, out_dir: Path | None = None, with_ext: bool = False) -> Path:
    stem = f"{src.stem}_{src.suffix.lstrip('.').lower()}" if with_ext else src.stem
    return (out_dir or src.parent) / f"{stem}_검토후보.xlsx"


def prepare(doc: Document, cfg: Config) -> Counter:
    """전처리만 수행. 모든 규칙은 스위치를 본다. 글이 없는 쪽은 스위치와 무관하게 '이미지 페이지'/'본문 없음'."""
    removed = apply_line_rules(doc, cfg)      # 줄 규칙을 먼저: 표지 판정이 거른 뒤 남은 줄 수를 쓴다
    apply_page_rules(doc, cfg)
    apply_page_weights(doc, cfg)
    number_lines(doc, cfg)
    assign_sections(doc)
    for page in doc.pages:
        if page.excluded_reason is None and not page.active_lines():
            page.excluded_reason = IMAGE_PAGE if page.has_graphics else "본문 없음(전처리 후)"
    return removed


def _line_notes(ln) -> list[str]:
    notes = ["분할"] if ln.split_from else []
    if ln.source == "table":
        notes.append("표")
    elif ln.source == "diagram":
        notes.append("도형")
    return notes


def classify_lines(pages: list[Page], cfg: Config, svc: Services, info: RunInfo, status: Status | None = None) -> list[LabeledLine]:
    """판정 본체: 활성 줄 전부를 분류기에 넣는다. 대상 등급(기본 A·B)이 아니면 stage_out=1."""
    targets = [p for p in pages if p.excluded_reason is None and p.active_lines()]
    want = set(cfg.targets())
    info.target_grades = ",".join(cfg.targets())
    info.pages_labeled = len(targets)
    entries = [(p, ln) for p in targets for ln in p.active_lines()]
    labeled: list[LabeledLine] = []
    svc.ensure_classifier()
    clf = svc.classifier
    info.classifier_name = cfg.classifier
    info.classifier = clf.describe()
    if not entries:
        return labeled
    texts = [ln.text for _, ln in entries]
    page_types = [page_type(p.title)[0] for p, _ in entries]
    vectors = None
    if clf.needs_embedding:
        if status:
            status(f"임베딩 {len(texts)}문장 ({cfg.embed_model})")
        svc.check_cancel()
        t0 = time.time()
        vectors = svc.embedder.embed(texts)
        info.embed_sec = time.time() - t0
        info.embed_model = cfg.embed_model
        info.cache_hits = getattr(svc.embedder, "cache_hits", 0)
    if status:
        status(f"1차 분류기 {clf.label}: {len(texts)}문장 판정")
    svc.check_cancel()
    t0 = time.time()
    preds = clf.predict(Batch(texts, vectors, page_types))
    info.classify_sec = time.time() - t0
    for (p, ln), pr in zip(entries, preds):
        labeled.append(LabeledLine(page_no=p.no, page_title=p.title, section=p.section, line_idx=ln.idx, text=ln.text,
                                   label=pr.label, raw_label=pr.label, notes=_line_notes(ln), source="clf",
                                   clf_label=pr.label, clf_conf=round(pr.confidence, 3), clf_margin=round(pr.margin, 3),
                                   page_weight=p.weight, stage_out=0 if pr.label in want else 1))
    info.clf_lines = len(labeled)
    return labeled


def finalize_stages(labeled: list[LabeledLine], cfg: Config) -> None:
    """후처리(보정·안전망·골드) 뒤 최종 라벨이 대상 등급이 아니면 후처리 제외(2). 분류기 제외(1)는 그대로."""
    want = set(cfg.targets())
    for ll in labeled:
        if ll.stage_out == 0 and ll.label not in want and ll.label not in ("X?", "?"):
            ll.stage_out = 2
        elif ll.stage_out == 2 and ll.label in want:          # 골드가 대상 등급으로 확정한 경우 등
            ll.stage_out = 0


def apply_gold(labeled: list[LabeledLine], gold: GoldMap, info: RunInfo) -> int:
    """골드에 있는 문장은 분류기 판정 대신 골드 정답. 후처리 뒤에 적용해 사람 판정이 최종이 되게 한다."""
    applied = 0
    for ll in labeled:
        g = gold.get(ll.text)
        if g is None:
            continue
        applied += 1
        before = "X" if ll.label in ("X?", "?") else ll.label
        if before != g:
            info.gold_changed += 1
            ll.notes.append(f"골드 반영({ll.label}→{g})")
        else:
            ll.notes.append("골드 반영")
        ll.label = ll.raw_label = g
        ll.source = "gold"
        ll.hold_reason = ""
        if ll.stage_out == 1:
            ll.stage_out = 2                       # 분류기 제외였지만 골드가 다른 등급을 줌 → finalize 에서 대상 등급이면 통과
    info.gold_lines = applied
    return applied


def run_settings(cfg: Config, info: RunInfo) -> dict:
    """이력 스냅샷과 비교 명령이 쓰는 '결과에 영향을 준 설정' 묶음."""
    return {**cfg.fingerprint(), "classifier_desc": info.classifier or "-", "gold": info.gold_desc or "없음"}


def snapshot(info: RunInfo, cfg: Config, labeled: list[LabeledLine], doc: Document, src_hash: str) -> dict:
    lines = {f"{ll.page_no}:{ll.line_idx}": {"h": text_hash(ll.text), "label": ll.label, "score": ll.score, "in": in_review_list(ll)}
             for ll in labeled}
    grades = Counter(ll.label for ll in labeled if in_review_list(ll))
    return {
        "run_id": info.run_id, "started_at": info.started_at, "source": info.source, "source_name": Path(info.source).name,
        "source_hash": src_hash, "settings": run_settings(cfg, info), "elapsed_sec": round(info.elapsed_sec, 1),
        "stats": {"pages_total": info.pages_total, "pages_labeled": info.pages_labeled, "lines": len(labeled),
                  "list": sum(grades.values()), "A": grades.get("A", 0), "B": grades.get("B", 0), "C": grades.get("C", 0), "D": grades.get("D", 0),
                  "held": info.held_lines, "clf_out": sum(1 for ll in labeled if ll.stage_out == 1), "pages_low": info.pages_low},
        "lines": lines,
    }


def record_history(result: "Result", cfg: Config, history: History | None = None) -> None:
    """스냅샷 저장 + 같은 파일의 직전 실행과 비교. result.changes 와 info.changes/settings_diff/prev_run_id 를 채운다."""
    info = result.info
    history = history or History(cfg.history_dir())
    if not history.enabled:
        return
    src = Path(info.source)
    info.run_id = history.unique_run_id(make_run_id(info.started_at, src))
    snap = snapshot(info, cfg, result.labeled, result.doc, file_hash(src))
    prev = history.previous_run(snap["source_hash"], snap["source_name"], info.run_id)
    if prev is not None:
        info.prev_run_id = prev.get("run_id", "")
        info.settings_diff = settings_diff(prev.get("settings", {}), snap["settings"])
        d = diff_runs(prev, snap)
        info.changes = d["counts"]
        result.changes = change_rows(d, result.labeled)
        snap["prev_run_id"] = info.prev_run_id
        snap["settings_diff"] = info.settings_diff
        snap["changes"] = d["counts"]
    history.save_run(snap)


def load_gold_map(cfg: Config) -> GoldMap | None:
    if not cfg.use_gold:
        return None
    gm = GoldMap.load(cfg.gold_paths, cfg.base_dir)
    return gm if gm.files else None


def run_file(path: Path, cfg: Config, progress: Progress | None = None, status: Status | None = None,
             embedder=None, classifier=None, history: History | None = None, use_gold: bool = True,
             cancel: CancelToken | None = None) -> Result:
    t0 = time.time()
    info = RunInfo(source=str(path), started_at=datetime.now().isoformat(timespec="seconds"), version=__version__,
                   reader="layout" if cfg.layout_analysis else "raw", switches=switch_state(cfg),
                   accept_score=cfg.accept_score, page_weight_enabled=cfg.page_weight_enabled,
                   low_relevance_weight=cfg.low_relevance_weight)
    doc = load_document(path, layout=cfg.layout_analysis)
    info.warnings.extend(doc.notes)
    removed = prepare(doc, cfg)
    info.pages_total = len(doc.pages)
    info.pages_image = sum(1 for p in doc.pages if p.excluded_reason == IMAGE_PAGE)
    info.pages_excluded = sum(1 for p in doc.pages if p.excluded_reason and p.excluded_reason != IMAGE_PAGE)
    info.pages_low = sum(1 for p in doc.pages if p.relevance == LOW)
    if progress:
        for k, page in enumerate(doc.pages, 1):
            progress(k, len(doc.pages), page)
    cache = LabelCache(cfg.cache_file() if cfg.use_cache else None)
    gold = load_gold_map(cfg) if use_gold else None
    if gold is not None:
        info.gold_desc = gold.describe()
        if gold.conflicts:
            info.warnings.append(f"골드 {gold.conflicts}문장이 파일마다 정답이 달라 최근 파일을 따랐습니다")
    svc = Services(cfg, cache, embedder=embedder, classifier=classifier, gold=gold, cancel=cancel)
    try:
        labeled = classify_lines(doc.pages, cfg, svc, info, status)
    finally:
        cache.close()
    if cfg.title_fix:
        apply_title_fix(labeled)
    if cfg.safety_net:
        apply_safety_net(labeled)
    if gold is not None:
        apply_gold(labeled, gold, info)
    finalize_stages(labeled, cfg)
    info.held_lines = apply_scores(labeled, cfg)
    info.elapsed_sec = time.time() - t0
    result = Result(doc, labeled, info, removed)
    record_history(result, cfg, history)
    return result


def extract(path: Path, cfg: Config, out_dir: Path | None = None, progress: Progress | None = None,
            with_ext: bool = False, status: Status | None = None, embedder=None, classifier=None,
            history: History | None = None, cancel: CancelToken | None = None, use_gold: bool = True) -> tuple[Path, Result]:
    result = run_file(path, cfg, progress, status, embedder, classifier, history, use_gold=use_gold, cancel=cancel)
    out = write_report(output_path(path, out_dir, with_ext), result.doc, result.labeled, result.info, result.removed, result.changes, cfg)
    return out, result


def find_inputs(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            files.extend(sorted(f for f in p.rglob("*") if f.suffix.lower() in SUPPORTED and not f.name.startswith("~$")))
        elif p.suffix.lower() in SUPPORTED:
            files.append(p)
        else:
            raise ValueError(f"지원하지 않는 입력: {p}")
    return files
