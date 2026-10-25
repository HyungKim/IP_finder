"""읽기 → 전처리 → 판정(llm / fast / hybrid) → 후처리 → 리포트. CLI와 평가·학습 도구가 공유한다."""
from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import PROMPT_VERSION
from .cache import LabelCache
from .classify import OllamaEmbedder, load_classifier
from .config import Config
from .label import label_grouped, label_page, load_system_prompt
from .llm import OllamaClient
from .models import Document, LabeledLine, Page, RunInfo
from .post import apply_safety_net, apply_title_fix, assign_sections
from .prep import apply_line_rules, apply_page_rules, number_lines
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


@dataclass
class Services:
    """LLM 클라이언트, 임베더, 분류기를 필요할 때만 만든다. 테스트는 가짜 객체를 넣는다."""
    cfg: Config
    cache: LabelCache
    client: object | None = None
    embedder: object | None = None
    classifier: object | None = None
    _clf_error: str = field(default="", repr=False)

    def llm(self):
        if self.client is None:
            self.client = make_client(self.cfg)
        return self.client

    def ensure_classifier(self) -> bool:
        if self.classifier is not None:
            return True
        if self.embedder is None:
            self.embedder = OllamaEmbedder(self.cfg.host, self.cfg.embed_model, timeout_sec=self.cfg.timeout_sec,
                                           keep_alive=self.cfg.keep_alive, cache=self.cache)
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


def label_pages(pages: list[Page], cfg: Config, svc: Services, info: RunInfo,
                progress: Progress | None = None, status: Status | None = None) -> list[LabeledLine]:
    """판정 본체. llm: 페이지별 LLM / fast: 분류기만 / hybrid: 분류기 확신분 채택 + 애매한 문장만 유형별 묶음 LLM."""
    targets = [p for p in pages if p.excluded_reason is None and p.active_lines()]
    mode = cfg.mode
    if mode not in ("llm", "fast", "hybrid"):
        raise ValueError(f"알 수 없는 모드: {mode}")
    if mode in ("fast", "hybrid") and not svc.ensure_classifier():
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
            labels = label_page(client, page, cfg, svc.cache, info, system)
            for ln in page.active_lines():
                lab = labels.get(ln.idx, "?")
                labeled.append(LabeledLine(page_no=page.no, page_title=page.title, section=page.section, line_idx=ln.idx,
                                           text=ln.text, label=lab, raw_label=lab, notes=_line_notes(ln), source="llm"))
        info.llm_lines = len(labeled)
        info.llm_sec = getattr(client, "llm_seconds", 0.0) - t0
        return labeled

    # ---- fast / hybrid: 임베딩 → 분류기 ----
    entries = [(p, ln) for p in targets for ln in p.active_lines()]
    if not entries:
        return labeled
    texts = [ln.text for _, ln in entries]
    page_types = [page_type(p.title)[0] for p, _ in entries]
    if status:
        status(f"임베딩 {len(texts)}문장 ({cfg.embed_model})")
    t0 = time.time()
    vectors = svc.embedder.embed(texts)
    info.embed_sec = time.time() - t0
    info.embed_model = cfg.embed_model
    clf = svc.classifier
    trained = getattr(clf, "kind", "") == "trained"
    info.classifier = f"학습({cfg.classifier_file().name})" if trained else "제로샷(원형 문장)"
    thr = cfg.threshold(trained)
    info.threshold = thr
    preds = clf.predict(vectors, texts, page_types)
    for (p, ln), pr in zip(entries, preds):
        labeled.append(LabeledLine(page_no=p.no, page_title=p.title, section=p.section, line_idx=ln.idx, text=ln.text,
                                   label=pr.label, raw_label=pr.label, notes=_line_notes(ln), source="clf",
                                   clf_label=pr.label, clf_conf=pr.confidence))
    if mode == "hybrid":
        ambiguous = [(p, ln) for (p, ln), pr in zip(entries, preds) if pr.confidence < thr]
        if status:
            status(f"분류기 확신 {len(entries) - len(ambiguous)}문장 채택, 애매한 {len(ambiguous)}문장은 LLM ({cfg.model})")
        if ambiguous:
            client = svc.llm()
            t0 = getattr(client, "llm_seconds", 0.0)
            res = label_grouped(client, ambiguous, cfg, svc.cache, info)
            info.llm_sec = getattr(client, "llm_seconds", 0.0) - t0
            for ll in labeled:
                lab = res.get((ll.page_no, ll.line_idx))
                if lab is None:
                    continue
                ll.notes.append(f"분류기 {ll.clf_label}({ll.clf_conf:.2f})")
                if lab == "?":
                    ll.notes.append("LLM 실패, 분류기 라벨 유지")
                    continue
                if lab != ll.clf_label:
                    ll.notes.append("불일치")
                ll.label = ll.raw_label = lab
                ll.source = "llm"
    info.llm_lines = sum(1 for ll in labeled if ll.source == "llm")
    info.clf_lines = sum(1 for ll in labeled if ll.source == "clf")
    return labeled


def run_file(path: Path, cfg: Config, client=None, progress: Progress | None = None, status: Status | None = None,
             embedder=None, classifier=None) -> Result:
    t0 = time.time()
    info = RunInfo(source=str(path), model=cfg.model, prompt_version=PROMPT_VERSION,
                   started_at=datetime.now().isoformat(timespec="seconds"))
    doc = load_document(path)
    removed = prepare(doc, cfg)
    info.pages_total = len(doc.pages)
    info.pages_image = sum(1 for p in doc.pages if p.excluded_reason == IMAGE_PAGE)
    info.pages_excluded = sum(1 for p in doc.pages if p.excluded_reason and p.excluded_reason != IMAGE_PAGE)
    cache = LabelCache(cfg.cache_file() if cfg.use_cache else None)
    svc = Services(cfg, cache, client=client, embedder=embedder, classifier=classifier)
    try:
        labeled = label_pages(doc.pages, cfg, svc, info, progress, status)
    finally:
        cache.close()
    info.model = getattr(svc.client, "model", cfg.model) if svc.client is not None else cfg.model
    if cfg.title_fix:
        apply_title_fix(labeled)
    if cfg.safety_net:
        apply_safety_net(labeled)
    info.elapsed_sec = time.time() - t0
    return Result(doc, labeled, info, removed)


def extract(path: Path, cfg: Config, out_dir: Path | None = None, client=None, progress: Progress | None = None,
            with_ext: bool = False, status: Status | None = None, embedder=None, classifier=None) -> tuple[Path, Result]:
    result = run_file(path, cfg, client, progress, status, embedder, classifier)
    out = write_report(output_path(path, out_dir, with_ext), result.doc, result.labeled, result.info, result.removed)
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
