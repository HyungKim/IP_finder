"""줄 단위 제거. 반복 문구, 수동 목록, 숫자만, 한글 없음(영어·숫자·기호만), 담당자, 짧은 일정·금액 줄, 그리고 글자수가 short_line_chars 이하인 짧은 조각."""
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
HANGUL_RE = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]")
SHORT_RULE_LEN = 30


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def has_korean(text: str) -> bool:
    return HANGUL_RE.search(text) is not None


def char_count(text: str) -> int:
    """공백을 뺀 글자수. 한글·영문·숫자·기호 모두 한 글자."""
    return len(re.sub(r"\s+", "", text))


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
            elif NUMERIC_ONLY.match(text):
                reason = "숫자만"
            elif cfg.require_korean and not has_korean(text):
                reason = "한글 없음"       # 영어·숫자·기호만 있는 줄 (모델명, 영문 항목명, 수식)은 한국어 보고서에서 본문이 아니다
            elif OWNER_RE.search(text):
                reason = "담당자"
            elif len(text) <= SHORT_RULE_LEN and (DATE_RE.search(text) or MONEY_RE.search(text)) and not has_tech_word(text):
                reason = "일정/금액"
            elif char_count(text) <= cfg.short_line_chars:
                reason = "짧은 조각"       # 제목 조각·표 셀·항목명 같은 짧은 줄은 문맥 없이 판정할 수 없어 후보에서 뺀다
            ln.removed_by = reason
            if reason:
                removed[reason] += 1
    return removed
