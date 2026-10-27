"""읽기 → 전처리(관련성·가중치 포함) → 판정(cascade / fast / llm) → 후처리 → 골드 반영 → 단계 확정 → 점수 → 이력 → 리포트.
cascade = 분류기가 1차로 대상 등급(기본 A·B) 문장만 추출하고, 그 후보 전부를 LLM 이 2차로 판정해 최종 등급(A/B)을 매긴다.
LLM 이 C·D·X 로 보면 '2차 제외'. CLI, UI, 평가·학습 도구가 공유한다."""
from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import PROMPT_VERSION, __version__
from .cache import LabelCache
from .cancel import CancelToken, Cancelled
from .classify import OllamaEmbedder, load_classifier
from .config import MODES, Config
from .goldmap import GoldMap
from .history import History, change_rows, diff_runs, file_hash, make_run_id, settings_diff, text_hash
from .label import label_grouped, label_page, load_system_prompt
from .llm import OllamaClient
from .models import Document, LabeledLine, Page, RunInfo
from .post import apply_safety_net, apply_scores, apply_title_fix, assign_sections, in_review_list
from .prep import LOW, apply_line_rules, apply_page_rules, apply_page_weights, number_lines
from .prep.page_rules import IMAGE_PAGE
from .prep.page_type import page_type
from .readers import SUPPORTED, load_document
from .report import write_report

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
    """LLM 클라이언트, 임베더, 분류기를 필요할 때만 만든다. 테스트는 가짜 객체를 넣는다."""
    cfg: Config
    cache: LabelCache
    client: object | None = None
    embedder: object | None = None
    classifier: object | None = None
    gold: GoldMap | None = None      # 골드 정답 반영. None 이면 반영하지 않음 (채점, 골드 시트 생성)
    cancel: CancelToken | None = None   # UI 중지 버튼. 등록된 클라이언트의 요청을 즉시 끊는다
    _clf_error: str = field(default="", repr=False)

    def __post_init__(self):
        if self.cancel is not None:
            self.cancel.register(self.client)
            self.cancel.register(self.embedder)

    def in_gold(self, text: str) -> bool:
        return self.gold is not None and self.gold.get(text) is not None

    def check_cancel(self) -> None:
        if self.cancel is not None:
            self.cancel.check()

    def llm(self):
        if self.client is None:
            self.client = make_client(self.cfg)
            if self.cancel is not None:
                self.cancel.register(self.client)
        return self.client

    def ensure_classifier(self) -> bool:
        if self.classifier is not None:
            return True
        if self.embedder is None:
            self.embedder = OllamaEmbedder(self.cfg.host, self.cfg.embed_model, timeout_sec=self.cfg.timeout_sec,
                                           keep_alive=self.cfg.keep_alive, cache=self.cache)
            if self.cancel is not None:
                self.cancel.register(self.embedder)
        if not self.embedder.available():
            self._clf_error = f"임베딩 모델 {self.cfg.embed_model} 을 쓸 수 없음 (ollama pull {self.cfg.embed_model})"
            return False
        try:
            self.classifier = load_classifier(self.cfg, self.embedder)
        except Exception as e:
            self._clf_error = f"분류기 로드 실패: {e}"
            return False
        return True


def output_path(src: Path, out_dir: Path | None = None, with_ext: bool = False) -> Path:
    stem = f"{src.stem}_{src.suffix.lstrip('.').lower()}" if with_ext else src.stem
    return (out_dir or src.parent) / f"{stem}_검토후보.xlsx"


def prepare(doc: Document, cfg: Config) -> Counter:
    """전처리만 수행 (LLM 없음). 테스트와 골드 시트가 재사용."""
    apply_page_rules(doc, cfg)
    apply_page_weights(doc, cfg)
    removed = apply_line_rules(doc, cfg)
    number_lines(doc, cfg)
    assign_sections(doc)
    for page in doc.pages:
        if page.excluded_reason is None and not page.active_lines():
            page.excluded_reason = IMAGE_PAGE if page.has_graphics else "본문 없음(전처리 후)"
    return removed


def make_client(cfg: Config) -> OllamaClient:
    return OllamaClient(cfg.host, cfg.model, timeout_sec=cfg.timeout_sec, keep_alive=cfg.keep_alive, num_ctx=cfg.num_ctx)


def make_embedder(cfg: Config, cache: LabelCache | None = None) -> OllamaEmbedder:
    return OllamaEmbedder(cfg.host, cfg.embed_model, timeout_sec=cfg.timeout_sec, keep_alive=cfg.keep_alive, cache=cache)


def _line_notes(ln) -> list[str]:
    notes = ["분할"] if ln.split_from else []
    if ln.source == "table":
        notes.append("표")
    return notes


def classifier_desc(cfg: Config, clf) -> str:
    """실행 정보와 이력에 적는 분류기 설명. 학습 분류기는 학습 시각과 문장 수까지."""
    if getattr(clf, "kind", "") != "trained":
        return "제로샷(원형 문장)"
    meta = getattr(clf, "meta", {}) or {}
    when = str(meta.get("trained_at", ""))[:16].replace("T", " ")
    return f"학습({cfg.classifier_file().name}, {when}, {meta.get('n', '?')}문장, 골드 {len(meta.get('sources', []))}개)"


def label_pages(pages: list[Page], cfg: Config, svc: Services, info: RunInfo,
                progress: Progress | None = None, status: Status | None = None) -> list[LabeledLine]:
    """판정 본체.
    cascade: 분류기가 모든 문장을 1차 판정해 대상 등급(cfg.targets, 기본 A·B)만 후보로 남기고(stage_out=1 로 제외),
             후보 전부를 LLM 이 2차 판정. LLM 결과가 대상 등급이 아니면 stage_out=2 로 제외.
    fast: 분류기만. llm: 모든 페이지를 LLM 이 판정 (대상 등급 밖은 stage_out=2)."""
    targets = [p for p in pages if p.excluded_reason is None and p.active_lines()]
    want = set(cfg.targets())
    info.target_grades = ",".join(cfg.targets())
    mode = "cascade" if cfg.mode == "hybrid" else cfg.mode
    if mode not in MODES:
        raise ValueError(f"알 수 없는 모드: {mode} (cascade | fast | llm)")
    if mode in ("fast", "cascade") and not svc.ensure_classifier():
        info.warnings.append(f"{svc._clf_error} → llm 모드로 대체")
        mode = "llm"
    info.mode = mode
    info.pages_labeled = len(targets)
    labeled: list[LabeledLine] = []

    if mode == "llm":
        client = svc.llm()
        system = load_system_prompt(cfg.prompt_variant)
        t0 = getattr(client, "llm_seconds", 0.0)
        for k, page in enumerate(targets, 1):
            if progress:
                progress(k, len(targets), page)
            svc.check_cancel()
            if all(svc.in_gold(ln.text) for ln in page.active_lines()):
                labels = {ln.idx: svc.gold.get(ln.text) for ln in page.active_lines()}   # 전부 골드 → LLM 호출 없음
            else:
                labels = label_page(client, page, cfg, svc.cache, info, system, cancel=svc.check_cancel)
            for ln in page.active_lines():
                lab = labels.get(ln.idx, "?")
                labeled.append(LabeledLine(page_no=page.no, page_title=page.title, section=page.section, line_idx=ln.idx,
                                           text=ln.text, label=lab, raw_label=lab, notes=_line_notes(ln), source="llm",
                                           llm_label=lab, page_weight=page.weight,
                                           stage_out=0 if (lab in want or lab == "?") else 2))
        info.llm_lines = len(labeled)
        info.llm_sec = getattr(client, "llm_seconds", 0.0) - t0
        return labeled

    # ---- fast / cascade: 임베딩 → 분류기 1차 ----
    entries = [(p, ln) for p in targets for ln in p.active_lines()]
    if not entries:
        return labeled
    texts = [ln.text for _, ln in entries]
    page_types = [page_type(p.title)[0] for p, _ in entries]
    if status:
        status(f"임베딩 {len(texts)}문장 ({cfg.embed_model})")
    svc.check_cancel()
    t0 = time.time()
    vectors = svc.embedder.embed(texts)
    info.embed_sec = time.time() - t0
    info.embed_model = cfg.embed_model
    clf = svc.classifier
    info.classifier = classifier_desc(cfg, clf)
    preds = clf.predict(vectors, texts, page_types)
    for (p, ln), pr in zip(entries, preds):
        labeled.append(LabeledLine(page_no=p.no, page_title=p.title, section=p.section, line_idx=ln.idx, text=ln.text,
                                   label=pr.label, raw_label=pr.label, notes=_line_notes(ln), source="clf",
                                   clf_label=pr.label, clf_conf=pr.confidence, clf_top=pr.top, page_weight=p.weight,
                                   stage_out=0 if pr.label in want else 1))
    if mode == "cascade":
        # 1차: 분류기가 대상 등급(A·B)으로 본 문장만 후보. 2차: 후보 전부를 LLM 이 판정 (골드 문장은 정답을 쓰므로 제외)
        candidates = [(p, ln) for (p, ln), pr in zip(entries, preds) if pr.label in want and not svc.in_gold(ln.text)]
        n_gold = sum(1 for (_, ln_), pr_ in zip(entries, preds) if pr_.label in want and svc.in_gold(ln_.text))
        n_x = len(entries) - len(candidates) - n_gold
        if status:
            status(f"분류기 1차: {'/'.join(sorted(want))} 후보 {len(candidates)}문장 (제외 {n_x}" + (f", 골드 {n_gold}" if n_gold else "")
                   + f") → LLM 2차 판정 ({cfg.model})")
        if candidates:
            client = svc.llm()
            t0 = getattr(client, "llm_seconds", 0.0)

            def prog(k, n, size):
                if status:
                    status(f"  LLM 2차 {k}/{n} 묶음 ({size}문장)")

            res = label_grouped(client, candidates, cfg, svc.cache, info, cancel=svc.check_cancel, progress=prog)
            info.llm_sec = getattr(client, "llm_seconds", 0.0) - t0
            for ll in labeled:
                lab = res.get((ll.page_no, ll.line_idx))
                if lab is None:
                    continue
                ll.notes.append(f"분류기 {ll.clf_label}({ll.clf_conf:.2f})")
                if lab == "?":
                    ll.notes.append("LLM 실패, 분류기 라벨 유지")
                    continue
                ll.llm_label = lab
                if lab not in want:
                    info.llm_rejected += 1
                    ll.stage_out = 2
                    ll.notes.append(f"LLM 2차 제외({lab})")
                elif lab != ll.clf_label:
                    ll.notes.append("불일치")
                ll.label = ll.raw_label = lab
                ll.source = "llm"
    info.llm_lines = sum(1 for ll in labeled if ll.source == "llm")
    info.clf_lines = sum(1 for ll in labeled if ll.source == "clf")
    return labeled


def finalize_stages(labeled: list[LabeledLine], cfg: Config) -> None:
    """후처리(보정·안전장치·골드) 뒤 최종 라벨이 대상 등급이 아니면 2차 제외로 둔다. 1차 제외(stage_out=1)는 그대로."""
    want = set(cfg.targets())
    for ll in labeled:
        if ll.stage_out == 0 and ll.label not in want and ll.label not in ("X?", "?"):
            ll.stage_out = 2
        elif ll.stage_out == 2 and ll.label in want:          # 골드가 대상 등급으로 확정한 경우 등
            ll.stage_out = 0


def apply_gold(labeled: list[LabeledLine], gold: GoldMap, info: RunInfo) -> int:
    """골드에 있는 문장은 모델 판정 대신 골드 정답. 후처리(보정·안전장치) 뒤에 적용해 사람 판정이 최종이 되게 한다."""
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
            ll.stage_out = 2                       # 1차 제외였지만 골드가 다른 등급을 줌 → finalize 에서 대상 등급이면 통과
    info.gold_lines = applied
    return applied


def snapshot(info: RunInfo, cfg: Config, labeled: list[LabeledLine], doc: Document, src_hash: str) -> dict:
    settings = {**cfg.fingerprint(), "prompt_version": PROMPT_VERSION, "classifier": info.classifier or "-", "version": __version__,
                "gold": info.gold_desc or "없음"}
    lines = {f"{ll.page_no}:{ll.line_idx}": {"h": text_hash(ll.text), "label": ll.label, "score": ll.score, "in": in_review_list(ll)}
             for ll in labeled}
    grades = Counter(ll.label for ll in labeled if in_review_list(ll))
    return {
        "run_id": info.run_id, "started_at": info.started_at, "source": info.source, "source_name": Path(info.source).name,
        "source_hash": src_hash, "settings": settings, "elapsed_sec": round(info.elapsed_sec, 1),
        "stats": {"pages_total": info.pages_total, "pages_labeled": info.pages_labeled, "lines": len(labeled),
                  "list": sum(grades.values()), "A": grades.get("A", 0), "B": grades.get("B", 0), "C": grades.get("C", 0), "D": grades.get("D", 0),
                  "held": info.held_lines, "llm_calls": info.llm_calls, "llm_rejected": info.llm_rejected,
                  "clf_out": info.clf_lines, "pages_low": info.pages_low},
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


def run_file(path: Path, cfg: Config, client=None, progress: Progress | None = None, status: Status | None = None,
             embedder=None, classifier=None, history: History | None = None, use_gold: bool = True,
             cancel: CancelToken | None = None) -> Result:
    t0 = time.time()
    info = RunInfo(source=str(path), model=cfg.model, prompt_version=PROMPT_VERSION,
                   started_at=datetime.now().isoformat(timespec="seconds"), accept_score=cfg.accept_score,
                   page_weight_enabled=cfg.page_weight_enabled, low_relevance_weight=cfg.low_relevance_weight)
    doc = load_document(path)
    removed = prepare(doc, cfg)
    info.pages_total = len(doc.pages)
    info.pages_image = sum(1 for p in doc.pages if p.excluded_reason == IMAGE_PAGE)
    info.pages_excluded = sum(1 for p in doc.pages if p.excluded_reason and p.excluded_reason != IMAGE_PAGE)
    info.pages_low = sum(1 for p in doc.pages if p.relevance == LOW)
    cache = LabelCache(cfg.cache_file() if cfg.use_cache else None)
    gold = load_gold_map(cfg) if use_gold else None
    if gold is not None:
        info.gold_desc = gold.describe()
        if gold.conflicts:
            info.warnings.append(f"골드 {gold.conflicts}문장이 파일마다 정답이 달라 최근 파일을 따랐습니다")
    svc = Services(cfg, cache, client=client, embedder=embedder, classifier=classifier, gold=gold, cancel=cancel)
    try:
        labeled = label_pages(doc.pages, cfg, svc, info, progress, status)
    finally:
        cache.close()
    info.model = getattr(svc.client, "model", cfg.model) if svc.client is not None else cfg.model
    if cfg.title_fix:
        apply_title_fix(labeled)
    if cfg.safety_net:
        apply_safety_net(labeled)
    if gold is not None:
        apply_gold(labeled, gold, info)
    finalize_stages(labeled, cfg)
    trained = getattr(svc.classifier, "kind", "") == "trained"
    info.held_lines = apply_scores(labeled, cfg, trained)
    info.elapsed_sec = time.time() - t0
    result = Result(doc, labeled, info, removed)
    record_history(result, cfg, history)
    return result


def extract(path: Path, cfg: Config, out_dir: Path | None = None, client=None, progress: Progress | None = None,
            with_ext: bool = False, status: Status | None = None, embedder=None, classifier=None,
            history: History | None = None, cancel: CancelToken | None = None) -> tuple[Path, Result]:
    result = run_file(path, cfg, client, progress, status, embedder, classifier, history, cancel=cancel)
    out = write_report(output_path(path, out_dir, with_ext), result.doc, result.labeled, result.info, result.removed, result.changes)
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
