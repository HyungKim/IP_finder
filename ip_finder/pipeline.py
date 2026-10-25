"""읽기 → 전처리 → 라벨링 → 후처리 → 리포트. CLI와 평가 도구가 공유한다."""
from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import PROMPT_VERSION
from .cache import LabelCache
from .config import Config
from .label import label_document
from .llm import OllamaClient
from .models import Document, LabeledLine, Page, RunInfo
from .post import apply_safety_net, apply_title_fix, assign_sections
from .prep import apply_line_rules, apply_page_rules, number_lines
from .prep.page_rules import IMAGE_PAGE
from .readers import SUPPORTED, load_document
from .report import write_report

Progress = Callable[[int, int, Page], None]


@dataclass
class Result:
    doc: Document
    labeled: list[LabeledLine]
    info: RunInfo
    removed: Counter


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


def run_file(path: Path, cfg: Config, client=None, progress: Progress | None = None) -> Result:
    t0 = time.time()
    info = RunInfo(source=str(path), model=cfg.model, prompt_version=PROMPT_VERSION,
                   started_at=datetime.now().isoformat(timespec="seconds"))
    doc = load_document(path)
    removed = prepare(doc, cfg)
    info.pages_total = len(doc.pages)
    info.pages_image = sum(1 for p in doc.pages if p.excluded_reason == IMAGE_PAGE)
    info.pages_excluded = sum(1 for p in doc.pages if p.excluded_reason and p.excluded_reason != IMAGE_PAGE)
    cache = LabelCache(cfg.cache_file() if cfg.use_cache else None)
    try:
        client = client or make_client(cfg)
        info.model = getattr(client, "model", cfg.model)   # 실제로 쓴 모델을 기록
        labeled = label_document(client, doc, cfg, cache, info, progress)
    finally:
        cache.close()
    if cfg.title_fix:
        apply_title_fix(labeled)
    if cfg.safety_net:
        apply_safety_net(labeled)
    info.elapsed_sec = time.time() - t0
    return Result(doc, labeled, info, removed)


def extract(path: Path, cfg: Config, out_dir: Path | None = None, client=None, progress: Progress | None = None,
            with_ext: bool = False) -> tuple[Path, Result]:
    result = run_file(path, cfg, client, progress)
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
