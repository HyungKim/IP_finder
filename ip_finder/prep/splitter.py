"""활성 줄에 번호를 붙이고, 긴 줄은 문장 단위로 나눈다."""
from __future__ import annotations

import re

from ..config import Config
from ..models import Document, Line
from .line_rules import char_count, has_korean

_SPLIT = re.compile(r"(?<=[.!?。])\s+")
_MIN_FRAG = 15


def split_sentences(text: str, min_frag: int = _MIN_FRAG, require_korean: bool = False) -> list[str]:
    """문장 부호 뒤에서 나눈다. 글자수(공백 제외)가 min_frag 미만이거나(require_korean 이면) 한글이 없는 조각은 옆 조각에 붙인다."""
    parts = [p.strip() for p in _SPLIT.split(text) if p.strip()]
    if len(parts) <= 1:
        return [text]
    merged: list[str] = []
    for p in parts:
        weak = False
        if merged:
            weak = char_count(p) < min_frag or char_count(merged[-1]) < min_frag
            if require_korean and (not has_korean(p) or not has_korean(merged[-1])):
                weak = True
        if weak:
            merged[-1] = f"{merged[-1]} {p}"
        else:
            merged.append(p)
    return merged


def number_lines(doc: Document, cfg: Config) -> None:
    for page in doc.pages:
        new: list[Line] = []
        idx = 0
        orig = 0
        for ln in page.lines:
            if not ln.active:
                ln.idx = 0
                new.append(ln)
                continue
            orig += 1
            parts = [ln.text] if len(ln.text) <= cfg.split_len else split_sentences(ln.text, cfg.short_line_chars + 1, cfg.require_korean)
            for part in parts:
                idx += 1
                new.append(Line(idx=idx, text=part, level=ln.level, source=ln.source,
                                split_from=orig if len(parts) > 1 else None))
        page.lines = new
