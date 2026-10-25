"""제목 접두어가 같은 연속 페이지를 섹션으로 묶는다. 병합은 하지 않는다."""
from __future__ import annotations

import re

from ..models import Document

_LEAD_NUM = re.compile(r"^\s*(\d{1,2}|[IVXivx]{1,4}|[가-힣]|[A-Za-z])\s*[.)]\s*")
_TRAIL = re.compile(r"[\s\d\-–()#.]+$")


def section_name(title: str) -> str:
    t = re.split(r"\s[-–—|]\s|[:：|]", title, maxsplit=1)[0]
    t = _LEAD_NUM.sub("", t)
    t = _TRAIL.sub("", t).strip()
    return t or title.strip()


def assign_sections(doc: Document) -> None:
    for page in doc.pages:
        page.section = section_name(page.title) if page.title.strip() else ""
