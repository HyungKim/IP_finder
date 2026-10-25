"""페이지마다 LLM을 한 번(길면 몇 번) 불러 줄별 등급 라벨을 받는다. 캐시 키는 모델+프롬프트 버전+입력 텍스트의 해시."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .. import PROMPT_VERSION
from ..cache import LabelCache
from ..config import Config
from ..models import GRADES, Document, LabeledLine, Line, Page, RunInfo

SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "system.md").read_text(encoding="utf-8").strip()


class LabelClient(Protocol):
    model: str

    def chat_labels(self, system: str, user: str, n: int) -> list[str]: ...


def build_user_prompt(title: str, lines: list[Line], page_no: int | None = None) -> str:
    head = f"[슬라이드 {page_no}] 제목: {title}" if page_no is not None else f"제목: {title}"
    body = [f"[{i}] {'  ' * ln.level}{ln.text}" for i, ln in enumerate(lines, 1)]
    return "\n".join([head, *body])


def _chunks(lines: list[Line], max_chars: int) -> list[list[Line]]:
    out: list[list[Line]] = []
    cur: list[Line] = []
    size = 0
    for ln in lines:
        if cur and size + len(ln.text) > max_chars:
            out.append(cur)
            cur, size = [], 0
        cur.append(ln)
        size += len(ln.text)
    if cur:
        out.append(cur)
    return out


def label_page(client: LabelClient, page: Page, cfg: Config, cache: LabelCache, info: RunInfo | None = None) -> dict[int, str]:
    """{줄 번호: 라벨}. 판정 실패는 '?'."""
    result: dict[int, str] = {}
    active = page.active_lines()
    if not active:
        return result
    for chunk in _chunks(active, cfg.max_chars_per_call):
        user = build_user_prompt(page.title, chunk, page.no)
        key = LabelCache.key(client.model, PROMPT_VERSION, user)
        labels = cache.get(key)
        if labels is None:
            try:
                labels = client.chat_labels(SYSTEM_PROMPT, user, len(chunk))
                cache.set(key, labels)
            except Exception as e:  # 한 페이지 실패가 전체를 멈추지 않게
                labels = ["?"] * len(chunk)
                if info is not None:
                    info.warnings.append(f"p{page.no}: {e}")
            if info is not None:
                info.llm_calls += 1
        elif info is not None:
            info.cache_hits += 1
        for ln, lab in zip(chunk, labels):
            result[ln.idx] = lab if lab in GRADES else "?"
    return result


def label_document(client: LabelClient, doc: Document, cfg: Config, cache: LabelCache, info: RunInfo,
                   progress=None) -> list[LabeledLine]:
    out: list[LabeledLine] = []
    targets = [p for p in doc.pages if p.excluded_reason is None and p.active_lines()]
    for k, page in enumerate(targets, 1):
        if progress:
            progress(k, len(targets), page)
        labels = label_page(client, page, cfg, cache, info)
        info.pages_labeled += 1
        for ln in page.active_lines():
            lab = labels.get(ln.idx, "?")
            notes = ["분할"] if ln.split_from else []
            if ln.source == "table":
                notes.append("표")
            out.append(LabeledLine(page_no=page.no, page_title=page.title, section=page.section, line_idx=ln.idx,
                                   text=ln.text, label=lab, raw_label=lab, notes=notes))
    return out
