"""입력 파일을 공통 Document 모델로 읽는다. 원본은 절대 수정하지 않는다."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ..models import Document
from ._text import split_items

SUPPORTED = {".pdf", ".pptx", ".ppt"}


def load_document(path: str | Path) -> Document:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        from .pdf_reader import read_pdf
        doc = read_pdf(p)
    elif suffix == ".pptx":
        from .pptx_reader import read_pptx
        doc = read_pptx(p)
    elif suffix == ".ppt":
        from .ppt_convert import convert_ppt_to_pptx
        from .pptx_reader import read_pptx
        converted = convert_ppt_to_pptx(p)
        doc = read_pptx(converted)
        doc.path = p
    else:
        raise ValueError(f"지원하지 않는 형식: {p.name} (지원: {', '.join(sorted(SUPPORTED))})")
    return split_listed_items(doc)


def split_listed_items(doc: Document) -> Document:
    """한 줄에 ▪·|(전각 ｜ 포함)로 나열된 항목은 각각 한 줄로 나눈다 (글머리 기호를 이어 쓴 항목, 셀을 세로줄로 구분한 글).
    계층·출처(본문/표/도형)는 그대로 물려받는다. 제목은 나누지 않는다."""
    for page in doc.pages:
        new = []
        for ln in page.lines:
            parts = split_items(ln.text)
            new.extend([ln] if len(parts) == 1 else [replace(ln, idx=0, text=part) for part in parts])
        page.lines = new
    return doc


def layout_report(path: str | Path, pages: set[int] | None = None) -> list[str]:
    """읽기 진단: 페이지마다 고른 제목과 블록(종류·글씨 크기·굵기·위치)을 줄 목록으로. LLM 없음."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        from .pdf_reader import layout_report as _pdf
        return _pdf(p, pages)
    if suffix == ".pptx":
        from .pptx_reader import layout_report as _pptx
        return _pptx(p, pages)
    raise ValueError(f"진단은 .pdf 와 .pptx 만 지원합니다: {p.name}")
