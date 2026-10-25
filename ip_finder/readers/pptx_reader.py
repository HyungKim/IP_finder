"""PPTX 리더 (python-pptx). 제목 플레이스홀더, 본문 문단(계층 유지), 표를 읽는다. 발표자 노트는 읽지 않는다."""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from ..models import Document, Line, Page
from ._text import clean

_GRAPHIC_TYPES = {
    MSO_SHAPE_TYPE.PICTURE, MSO_SHAPE_TYPE.AUTO_SHAPE, MSO_SHAPE_TYPE.FREEFORM, MSO_SHAPE_TYPE.LINE,
    MSO_SHAPE_TYPE.CHART, MSO_SHAPE_TYPE.LINKED_PICTURE, MSO_SHAPE_TYPE.MEDIA, MSO_SHAPE_TYPE.DIAGRAM,
}


def _iter_shapes(shapes):
    for sh in shapes:
        if sh.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from _iter_shapes(sh.shapes)
        else:
            yield sh


def _table_lines(table) -> list[Line]:
    rows = [[clean(c.text) for c in row.cells] for row in table.rows]
    rows = [r for r in rows if any(r)]
    if not rows:
        return []
    out: list[Line] = []
    if len(rows[0]) >= 2 and len(rows) >= 2:
        headers = rows[0]
        for r in rows[1:]:
            parts = [f"{h}: {c}" if h else c for h, c in zip(headers, r) if c]
            if parts:
                out.append(Line(idx=0, text=" | ".join(parts), source="table"))
    else:
        for r in rows:
            text = " | ".join(c for c in r if c)
            if text:
                out.append(Line(idx=0, text=text, source="table"))
    return out


def read_pptx(path: Path) -> Document:
    prs = Presentation(str(path))
    pages: list[Page] = []
    for sno, slide in enumerate(prs.slides, 1):
        title, title_shape = "", None
        ts = slide.shapes.title
        if ts is not None and ts.has_text_frame:
            title = clean(ts.text_frame.text.replace("\n", " "))
            title_shape = ts
        shapes = list(_iter_shapes(slide.shapes))
        shapes.sort(key=lambda s: ((s.top or 0), (s.left or 0)))
        lines: list[Line] = []
        has_graphics = False
        for sh in shapes:
            if title_shape is not None and sh.shape_id == title_shape.shape_id:
                continue
            if getattr(sh, "has_table", False) and sh.has_table:
                lines.extend(_table_lines(sh.table))
                continue
            if getattr(sh, "has_chart", False) and sh.has_chart:
                has_graphics = True
                continue
            if getattr(sh, "has_text_frame", False) and sh.has_text_frame and sh.text_frame.text.strip():
                for para in sh.text_frame.paragraphs:
                    text = clean("".join(r.text for r in para.runs) or para.text)
                    if text:
                        lines.append(Line(idx=0, text=text, level=para.level or 0))
                continue
            if sh.shape_type in _GRAPHIC_TYPES:
                has_graphics = True
        if not title and lines:
            title, lines = lines[0].text, lines[1:]
        pages.append(Page(no=sno, title=title, lines=lines, has_graphics=has_graphics))
    return Document(path=Path(path), kind="pptx", pages=pages, title=pages[0].title if pages else "")
