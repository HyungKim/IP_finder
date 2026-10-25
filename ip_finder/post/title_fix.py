"""제목이 원인·문제·배경·현황인 페이지에서, 변경 동사가 없는 A는 C로 내린다. 보정된 행은 표시한다."""
from __future__ import annotations

import re

from ..cues import CHANGE_VERBS
from ..models import LabeledLine

PROBLEM_TITLE = re.compile(r"(원인|문제|배경|현황|이슈|과제|불량|한계)")


def apply_title_fix(labeled: list[LabeledLine]) -> int:
    fixed = 0
    for ll in labeled:
        if ll.label == "A" and PROBLEM_TITLE.search(ll.page_title) and not CHANGE_VERBS.search(ll.text):
            ll.label = "C"
            ll.notes.append("보정(A→C)")
            fixed += 1
    return fixed
