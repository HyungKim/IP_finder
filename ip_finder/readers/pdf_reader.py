"""PDF 리더 (PyMuPDF). 페이지마다 제목과 본문 줄을 읽기 순서로 뽑는다.
제목 = 페이지 위쪽(높이 35% 안)에서 글씨가 가장 큰 줄 (중앙값의 1.15배 이상일 때). 없으면 첫 줄."""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pymupdf

from ..models import Document, Line, Page
from ._text import clean

_SENT_END = re.compile(r"[.!?。]\s*$")
_STARTS_NEW = re.compile(r"^(\(?\d{1,2}[.)]|[①-⑳]|[가-힣]\.|[•·▪■◦●○▶►✓□☐◆◇※\-–—])")


def _block_lines(block: dict) -> list[tuple[float, float, float, str]]:
    """블록 안에서 줄바꿈으로 나뉜 같은 문단을 다시 합친다. (y0, x0, size, text)"""
    out: list[list] = []
    for ln in block.get("lines", []):
        raw = "".join(s["text"] for s in ln["spans"])
        text = clean(raw)
        if not text:
            continue
        size = max(s["size"] for s in ln["spans"])
        x0, y0 = ln["bbox"][0], ln["bbox"][1]
        starts_new = bool(_STARTS_NEW.match(raw.strip())) or not out or _SENT_END.search(out[-1][3]) \
            or abs(size - out[-1][2]) > 1.0 or x0 < out[-1][1] - 4
        if starts_new:
            out.append([y0, x0, size, text])
        else:
            out[-1][3] = f"{out[-1][3]} {text}"
    return [tuple(o) for o in out]


def read_pdf(path: Path) -> Document:
    doc = pymupdf.open(path)
    pages: list[Page] = []
    try:
        for pno, page in enumerate(doc, 1):
            height = page.rect.height or 1.0
            data = page.get_text("dict", sort=True)
            raw: list[tuple[float, float, float, str]] = []
            for block in data.get("blocks", []):
                if block.get("type") != 0:
                    continue
                raw.extend(_block_lines(block))
            title, title_i, title_source = "", None, "없음"
            if raw:
                sizes = sorted(r[2] for r in raw)
                median = sizes[len(sizes) // 2]
                top = [(i, r) for i, r in enumerate(raw) if r[0] < height * 0.35]
                if top:
                    i, r = max(top, key=lambda t: (round(t[1][2], 1), -t[1][0]))
                    if r[2] >= median * 1.15 or len(raw) == 1:
                        title, title_i, title_source = r[3], i, "font"
                if title_i is None:
                    title, title_i, title_source = raw[0][3], 0, "first-line"
            body = [r for i, r in enumerate(raw) if i != title_i]
            xs = Counter(round(r[1]) for r in body)
            base_x = xs.most_common(1)[0][0] if xs else 0
            lines = [Line(idx=0, text=r[3], level=1 if r[1] > base_x + 12 else 0) for r in body]
            has_graphics = bool(page.get_images(full=False)) or len(page.get_drawings()) > 3
            pages.append(Page(no=pno, title=title, lines=lines, has_graphics=has_graphics, title_source=title_source))
    finally:
        doc.close()
    return Document(path=Path(path), kind="pdf", pages=pages, title=pages[0].title if pages else "")
