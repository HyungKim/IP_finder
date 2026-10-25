"""활성 줄에 번호를 붙이고, 긴 줄은 문장 단위로 나눈다."""
from __future__ import annotations

import re

from ..config import Config
from ..models import Document, Line

_SPLIT = re.compile(r"(?<=[.!?。])\s+")
_MIN_FRAG = 8


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SPLIT.split(text) if p.strip()]
    if len(parts) <= 1:
        return [text]
    merged: list[str] = []
    for p in parts:
        if merged and (len(p) < _MIN_FRAG or len(merged[-1]) < _MIN_FRAG):
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
            parts = [ln.text] if len(ln.text) <= cfg.split_len else split_sentences(ln.text)
            for part in parts:
                idx += 1
                new.append(Line(idx=idx, text=part, level=ln.level, source=ln.source,
                                split_from=orig if len(parts) > 1 else None))
        page.lines = new
