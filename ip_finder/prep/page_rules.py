from __future__ import annotations

import re

from ..config import Config
from ..models import Document

IMAGE_PAGE = "이미지 페이지"


def apply_page_rules(doc: Document, cfg: Config) -> None:
    patterns = [re.compile(p, re.IGNORECASE) for p in cfg.page_exclude_patterns]
    for page in doc.pages:
        page.excluded_reason = None
        if not page.has_body and (page.has_graphics or not page.title.strip()):
            page.excluded_reason = IMAGE_PAGE
            continue
        hit = next((m.group(0) for p in patterns if (m := p.search(page.title))), None)
        if hit:
            page.excluded_reason = f"제목 규칙: '{hit.strip()}'"
        elif page.no == 1 and len(page.lines) <= cfg.cover_max_lines:
            page.excluded_reason = "표지"
        elif not page.has_body:
            page.excluded_reason = "본문 없음"
