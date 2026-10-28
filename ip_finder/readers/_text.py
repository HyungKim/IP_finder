"""리더 공용 텍스트 처리: 정리(clean), 목록 표식 판별, 표 행을 한 줄로 만들기."""
from __future__ import annotations

import re

from ..models import Line

_BULLET = re.compile(r"^[\s•·▪■◦●○▶►✓□☐◆◇※\-–—]+")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f​﻿]")

# 문단 머리의 목록 표식. 전용 글머리 기호는 뒤에 공백이 없어도 표식으로 본다(전각 글꼴 PDF 에서는 기호와 본문이 붙어 나온다).
# 본문에도 쓰이는 기호(-, *, + 등)는 뒤에 공백이 있을 때만 표식으로 본다.
STRONG_BULLETS = "•∙‣⁃◦○●◎◇◆□■▪▫▶▷►▻➢➤➔※✓✔"
WEAK_BULLETS = "·-–—*+→"
BULLET_RE = re.compile(rf"^\s*(?:([{re.escape(STRONG_BULLETS)}])\s*|([{re.escape(WEAK_BULLETS)}])\s+)")
PAGE_NUMBER_RE = re.compile(r"^\s*[-–—]\s*\d{1,4}\s*[-–—]\s*$")          # "- 3 -" 같은 쪽 번호는 목록 표식이 아니다
NUMBER_RE = re.compile(r"^\s*(\(?\d{1,3}[.)]|\(?[a-zA-Z][.)]|\(?[가-힣][.)]|[①-⑳]|[ⅰ-ⅹⅠ-Ⅹ][.)])\s+")


def clean(text: str) -> str:
    text = _CTRL.sub("", text).replace(" ", " ")
    text = _BULLET.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def list_marker(text: str) -> tuple[str, int]:
    """문단 머리의 목록 표식 종류('bullet' | 'number' | '')와 본문 시작 위치. 번호 표식은 의미가 있으므로 본문에 남긴다."""
    if PAGE_NUMBER_RE.match(text):
        return "", 0
    m = BULLET_RE.match(text)
    if m and m.end() < len(text):
        return "bullet", m.end()
    m = NUMBER_RE.match(text)
    if m:
        return "number", m.start(1)
    return "", 0


def table_lines(rows: list[list[str]]) -> list[Line]:
    """표의 행을 한 줄씩 Line(source='table') 으로. 첫 행이 열 제목이면 '제목: 셀 | 제목: 셀' 꼴로 붙인다."""
    rows = [[clean(c) for c in r] for r in rows]
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
