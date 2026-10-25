"""줄 단위 제거 (보수적). 반복 문구, 수동 목록, 짧은 조각, 숫자만, 담당자, 짧은 일정·금액 줄."""
from __future__ import annotations

import re
from collections import Counter

from ..config import Config
from ..cues import has_tech_word
from ..models import Document

DATE_RE = re.compile(
    r"(\d{4}\s*[./년-]\s*\d{1,2}|\d{1,2}\s*월(\s*\d{1,2}\s*일)?|[1-4]\s*분기|\bQ[1-4]\b|\d{1,2}/\d{1,2}|상반기|하반기|\d{4}\s*년|\d{1,2}\s*주차)",
    re.IGNORECASE,
)
MONEY_RE = re.compile(r"(\d[\d,.]*\s*(억|만|천)?\s*원\b|\d[\d,.]*\s*(억|만원|천원|KRW|USD|달러|\$)|단가|비용|예산|투자비)")
OWNER_RE = re.compile(r"^\s*(담당|담당자|작성자|작성|보고자|발표자|부서|책임자|PM|PL|TF)\s*[:：]")
NUMERIC_ONLY = re.compile(r"^[\s\d.,%/()\-–~:]+$")
SHORT_RULE_LEN = 30


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def apply_line_rules(doc: Document, cfg: Config) -> Counter:
    """removed_by 를 채운다. 규칙별 제거 수를 돌려준다."""
    per_page_sets = [{_norm(ln.text) for ln in p.lines if ln.text.strip()} for p in doc.pages]
    counts: Counter = Counter()
    for s in per_page_sets:
        counts.update(s)
    stop = {_norm(s) for s in cfg.stoplist}
    removed: Counter = Counter()
    for page in doc.pages:
        for ln in page.lines:
            text = ln.text.strip()
            n = _norm(text)
            reason = None
            if not text:
                reason = "빈 줄"
            elif n in stop:
                reason = "수동 목록"
            elif counts[n] >= cfg.repeated_line_min_pages:
                reason = "반복 문구"
            elif len(text) <= 3:
                reason = "짧은 조각"
            elif NUMERIC_ONLY.match(text):
                reason = "숫자만"
            elif OWNER_RE.search(text):
                reason = "담당자"
            elif len(text) <= SHORT_RULE_LEN and (DATE_RE.search(text) or MONEY_RE.search(text)) and not has_tech_word(text):
                reason = "일정/금액"
            ln.removed_by = reason
            if reason:
                removed[reason] += 1
    return removed
