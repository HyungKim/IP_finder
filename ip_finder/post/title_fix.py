"""제목이 과제·원인 유형인 페이지에서, 변경 동사가 없는 A는 C로 내린다. 보정된 행은 표시한다."""
from __future__ import annotations

from ..cues import CHANGE_VERBS
from ..models import LabeledLine
from ..prep.page_type import page_type


def apply_title_fix(labeled: list[LabeledLine]) -> int:
    fixed = 0
    for ll in labeled:
        if ll.label == "A" and page_type(ll.page_title)[0] == "problem" and not CHANGE_VERBS.search(ll.text):
            ll.label = "C"
            ll.notes.append("보정(A→C)")
            fixed += 1
    return fixed
