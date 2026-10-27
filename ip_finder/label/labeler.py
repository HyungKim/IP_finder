"""LLM 라벨링. 두 가지 호출 형태가 있다.
- label_page: 페이지 하나를 한 번에. 입력은 제목 + 페이지 유형 힌트 + 번호 줄.
- label_grouped: 분류기 1차를 통과한 후보 문장들을 페이지 유형별로 묶어 호출 (cascade 모드의 2차 판정).
출력은 언제나 줄 수와 같은 길이의 라벨 배열. 캐시 키는 모델 + 프롬프트 버전 + 입력 텍스트의 해시."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .. import PROMPT_VERSION
from ..cache import LabelCache
from ..config import Config
from ..models import GRADES, Document, LabeledLine, Line, Page, RunInfo
from ..prep.page_type import HINT_BY_KEY, page_type

_PROMPTS = Path(__file__).parent / "prompts"


def load_system_prompt(variant: str = "compact") -> str:
    name = "system_full.md" if variant == "full" else "system.md"
    return (_PROMPTS / name).read_text(encoding="utf-8").strip()


SYSTEM_PROMPT = load_system_prompt()


class LabelClient(Protocol):
    model: str

    def chat_labels(self, system: str, user: str, n: int) -> list[str]: ...


def build_user_prompt(title: str, lines: list[Line], page_no: int | None = None, hint: str | None = None) -> str:
    head = f"[슬라이드 {page_no}] 제목: {title}" if page_no is not None else f"제목: {title}"
    if hint:
        head += f"\n(페이지 유형: {hint})"
    body = [f"[{i}] {'  ' * ln.level}{ln.text}" for i, ln in enumerate(lines, 1)]
    return "\n".join([head, *body])


def build_group_prompt(hint: str | None, entries: list[tuple[str, str]]) -> str:
    """entries = [(페이지 제목, 문장)]. 서로 다른 슬라이드의 문장을 한 유형으로 묶어 보낼 때."""
    head = f"(페이지 유형: {hint or '일반 페이지'}) 아래 문장들은 서로 다른 슬라이드에서 왔으며, 각 문장 앞 괄호는 그 슬라이드의 제목이다."
    body = [f"[{i}] ({title[:20]}) {text}" for i, (title, text) in enumerate(entries, 1)]
    return "\n".join([head, *body])


def _chunks_by_chars(items: list, max_chars: int, text_of) -> list[list]:
    out: list[list] = []
    cur: list = []
    size = 0
    for it in items:
        n = len(text_of(it))
        if cur and size + n > max_chars:
            out.append(cur)
            cur, size = [], 0
        cur.append(it)
        size += n
    if cur:
        out.append(cur)
    return out


def _call(client: LabelClient, system: str, user: str, n: int, cache: LabelCache, info: RunInfo | None, where: str,
          cancel=None) -> list[str]:
    key = LabelCache.key(client.model, PROMPT_VERSION, system[:40] + user)
    labels = cache.get(key)
    if labels is None:
        if cancel is not None:
            cancel()                      # 중지 요청이면 여기서 Cancelled 예외
        try:
            labels = client.chat_labels(system, user, n)
            cache.set(key, labels)
        except Exception as e:
            if type(e).__name__ == "CancelledError":
                raise
            labels = ["?"] * n
            if info is not None:
                info.warnings.append(f"{where}: {e}")
        if info is not None:
            info.llm_calls += 1
    elif info is not None:
        info.cache_hits += 1
    return [lab if lab in GRADES else "?" for lab in labels]


def label_page(client: LabelClient, page: Page, cfg: Config, cache: LabelCache, info: RunInfo | None = None,
               system: str | None = None, cancel=None) -> dict[int, str]:
    """{줄 번호: 라벨}. 판정 실패는 '?'."""
    system = system or load_system_prompt(cfg.prompt_variant)
    result: dict[int, str] = {}
    active = page.active_lines()
    if not active:
        return result
    _, hint = page_type(page.title)
    for chunk in _chunks_by_chars(active, cfg.max_chars_per_call, lambda ln: ln.text):
        user = build_user_prompt(page.title, chunk, page.no, hint)
        labels = _call(client, system, user, len(chunk), cache, info, f"p{page.no}", cancel)
        for ln, lab in zip(chunk, labels):
            result[ln.idx] = lab
    return result


def label_grouped(client: LabelClient, entries: list[tuple[Page, Line]], cfg: Config, cache: LabelCache,
                  info: RunInfo | None = None, system: str | None = None, cancel=None,
                  progress=None) -> dict[tuple[int, int], str]:
    """애매한 문장들을 페이지 유형별로 묶어 호출. {(페이지, 줄): 라벨}"""
    system = system or load_system_prompt(cfg.prompt_variant)
    by_type: dict[str, list[tuple[Page, Line]]] = {}
    for page, ln in entries:
        by_type.setdefault(page_type(page.title)[0], []).append((page, ln))
    result: dict[tuple[int, int], str] = {}
    chunks = [(key, chunk) for key, items in by_type.items()
              for chunk in _chunks_by_chars(items, cfg.group_max_chars, lambda e: e[1].text)]
    for k, (key, chunk) in enumerate(chunks, 1):
        hint = HINT_BY_KEY.get(key)
        if True:
            if progress is not None:
                progress(k, len(chunks), len(chunk))
            user = build_group_prompt(hint, [(p.title, ln.text) for p, ln in chunk])
            labels = _call(client, system, user, len(chunk), cache, info, f"묶음({key})", cancel)
            for (p, ln), lab in zip(chunk, labels):
                result[(p.no, ln.idx)] = lab
    return result


def label_document(client: LabelClient, doc: Document, cfg: Config, cache: LabelCache, info: RunInfo,
                   progress=None) -> list[LabeledLine]:
    """llm 모드: 모든 대상 페이지를 페이지별로 라벨링."""
    system = load_system_prompt(cfg.prompt_variant)
    out: list[LabeledLine] = []
    targets = [p for p in doc.pages if p.excluded_reason is None and p.active_lines()]
    for k, page in enumerate(targets, 1):
        if progress:
            progress(k, len(targets), page)
        labels = label_page(client, page, cfg, cache, info, system)
        info.pages_labeled += 1
        for ln in page.active_lines():
            lab = labels.get(ln.idx, "?")
            notes = ["분할"] if ln.split_from else []
            if ln.source == "table":
                notes.append("표")
            out.append(LabeledLine(page_no=page.no, page_title=page.title, section=page.section, line_idx=ln.idx,
                                   text=ln.text, label=lab, raw_label=lab, notes=notes, source="llm"))
    return out
