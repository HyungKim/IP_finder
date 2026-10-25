"""재현율 안전장치: 모델이 X라 해도 기술 단서어가 있으면 'X?'로 보류 시트에 남긴다."""
from __future__ import annotations

from ..cues import HARD_EXCLUDE, tech_cues
from ..models import LabeledLine


def apply_safety_net(labeled: list[LabeledLine]) -> int:
    rescued = 0
    for ll in labeled:
        if ll.label != "X":
            continue
        cues = tech_cues(ll.text)
        if cues and not HARD_EXCLUDE.search(ll.text):
            ll.label = "X?"
            ll.notes.append("단서어: " + ", ".join(cues[:4]))
            rescued += 1
    return rescued
