"""입력 파일을 공통 Document 모델로 읽는다. 원본은 절대 수정하지 않는다."""
from __future__ import annotations

from pathlib import Path

from ..models import Document

SUPPORTED = {".pdf", ".pptx", ".ppt"}


def load_document(path: str | Path) -> Document:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        from .pdf_reader import read_pdf
        return read_pdf(p)
    if suffix == ".pptx":
        from .pptx_reader import read_pptx
        return read_pptx(p)
    if suffix == ".ppt":
        from .ppt_convert import convert_ppt_to_pptx
        from .pptx_reader import read_pptx
        converted = convert_ppt_to_pptx(p)
        doc = read_pptx(converted)
        doc.path = p
        return doc
    raise ValueError(f"지원하지 않는 형식: {p.name} (지원: {', '.join(sorted(SUPPORTED))})")
