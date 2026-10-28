"""리더 공용 텍스트 처리: 정리(clean), 목록 표식 판별, 표 셀을 줄로 만들기, 한 줄에 나열된 항목(▪·|) 나누기."""
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
    if not PAGE_NUMBER_RE.match(text):          # "- 3 -" 같은 쪽 번호는 꼴을 남긴다 (진단 출력에서 알아보기 쉽게; 전처리의 '숫자만' 규칙이 거른다)
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
    """표의 셀을 하나씩 Line(source='table') 으로 (행 순서, 왼쪽부터). 첫 행이 열 제목이면 '열 제목: 셀' 꼴로 붙인다.
    v0.6.1 까지는 한 행을 '제목: 셀 | 제목: 셀' 한 줄로 만들었다. 사용자 요구로 '|' 로 나뉜 항목은 각각 한 문장이다."""
    rows = [[clean(c) for c in r] for r in rows]
    rows = [r for r in rows if any(r)]
    if not rows:
        return []
    cells: list[str] = []
    if len(rows[0]) >= 2 and len(rows) >= 2:
        headers = rows[0]
        for r in rows[1:]:
            cells.extend(f"{h}: {c}" if h else c for h, c in zip(headers, r) if c)
    else:
        for r in rows:
            cells.extend(c for c in r if c)
    return [Line(idx=0, text=c, source="table") for c in cells]


# 한 줄 안에서 항목을 나누는 구분 기호: 앞에 공백이 있는 글머리 기호(▪ • ■ ● …), 양쪽에 공백이 있는 세로줄(|), 전각 세로줄(｜).
# "연구∙개발"(공백 없음)과 수식의 |x|(한쪽에 글자가 붙음)는 나누지 않는다. '·'(가운뎃점)은 낱말 이음에 쓰여 구분 기호가 아니다.
ITEM_SEP_RE = re.compile(rf"(?:(?<=\s)[{re.escape(STRONG_BULLETS)}]|\s\|(?=\s)|｜)")


def split_items(text: str) -> list[str]:
    """'▪ 항목 ▪ 항목', '항목 | 항목' 처럼 한 줄에 나열된 항목을 각각 한 줄로 나눈다. 나눌 것이 없으면 원문 그대로 한 줄."""
    parts = [clean(p) for p in ITEM_SEP_RE.split(text)]
    parts = [p for p in parts if p]
    return parts if len(parts) > 1 else [text]
