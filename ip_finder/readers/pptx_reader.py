"""PPTX 리더 (python-pptx). 제목 플레이스홀더, 본문 문단(계층 유지), 표를 읽는다. 발표자 노트는 읽지 않는다.
제목 플레이스홀더가 없거나 비어 있으면 슬라이드 위쪽(높이 35% 안)에서 글씨가 가장 큰 텍스트 상자를 제목으로 본다."""
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
TITLE_ZONE = 0.35      # 슬라이드 높이의 이 비율 안에 있어야 제목 후보
TITLE_MAX_CHARS = 80   # 이보다 길면 제목이 아니라 본문


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


def _max_font_pt(shape) -> float:
    """텍스트 상자의 가장 큰 명시적 글꼴 크기(pt). 상속만 있으면 0."""
    best = 0.0
    try:
        for para in shape.text_frame.paragraphs:
            for run in para.runs:
                if run.font.size is not None:
                    best = max(best, run.font.size.pt)
            if para.font.size is not None:
                best = max(best, para.font.size.pt)
    except Exception:
        pass
    return best


def _title_by_font(shapes, slide_height: int) -> object | None:
    """위쪽 영역의 텍스트 상자 중 글씨가 가장 큰 것. 크기 정보가 없으면 가장 위의 것."""
    cands = []
    for sh in shapes:
        if not (getattr(sh, "has_text_frame", False) and sh.has_text_frame):
            continue
        text = clean(sh.text_frame.text.replace("\n", " "))
        if not text or len(text) > TITLE_MAX_CHARS:
            continue
        top = sh.top or 0
        if slide_height and top > slide_height * TITLE_ZONE:
            continue
        cands.append((-_max_font_pt(sh), top, sh))
    if not cands:
        return None
    cands.sort(key=lambda t: (t[0], t[1]))
    return cands[0][2]


def read_pptx(path: Path) -> Document:
    prs = Presentation(str(path))
    slide_height = prs.slide_height or 0
    pages: list[Page] = []
    for sno, slide in enumerate(prs.slides, 1):
        title, title_shape, title_source = "", None, "없음"
        ts = slide.shapes.title
        if ts is not None and ts.has_text_frame:
            title = clean(ts.text_frame.text.replace("\n", " "))
            title_shape = ts
            title_source = "placeholder"
        shapes = list(_iter_shapes(slide.shapes))
        shapes.sort(key=lambda s: ((s.top or 0), (s.left or 0)))
        if not title:
            cand = _title_by_font(shapes, slide_height)
            if cand is not None:
                title, title_shape, title_source = clean(cand.text_frame.text.replace("\n", " ")), cand, "font"
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
            title, lines, title_source = lines[0].text, lines[1:], "first-line"
        pages.append(Page(no=sno, title=title, lines=lines, has_graphics=has_graphics, title_source=title_source))
    return Document(path=Path(path), kind="pptx", pages=pages, title=pages[0].title if pages else "")
