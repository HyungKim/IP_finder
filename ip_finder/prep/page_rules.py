from __future__ import annotations

import re

from ..config import Config
from ..models import Document

IMAGE_PAGE = "이미지 페이지"


def apply_page_rules(doc: Document, cfg: Config) -> None:
    """쪽 단위 제외. 글이 전혀 없는 쪽(이미지 페이지·본문 없음)은 스위치와 무관하게 판정할 것이 없어 늘 제외한다.
    rule_page_exclude: 제목이 page_exclude_patterns 에 걸리는 쪽. rule_cover: 1쪽에 남은 줄이 cover_max_lines 이하이면 표지."""
    patterns = [re.compile(p, re.IGNORECASE) for p in cfg.page_exclude_patterns] if cfg.rule_page_exclude else []
    for page in doc.pages:
        page.excluded_reason = None
        if not page.has_body and (page.has_graphics or not page.title.strip()):
            page.excluded_reason = IMAGE_PAGE
            continue
        hit = next((m.group(0) for p in patterns if (m := p.search(page.title))), None)
        if hit:
            page.excluded_reason = f"제목 규칙: '{hit.strip()}'"
        elif cfg.rule_cover and page.no == 1 and len(page.active_lines()) <= cfg.cover_max_lines:
            page.excluded_reason = "표지"         # 줄 규칙이 거른 뒤(반복 문구·날짜·짧은 조각 제외) 남은 줄 수로 판단
        elif not page.has_body:
            page.excluded_reason = "본문 없음"
