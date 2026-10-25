import re

_BULLET = re.compile(r"^[\s•·▪■◦●○▶►✓□☐◆◇※\-–—]+")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f​﻿]")


def clean(text: str) -> str:
    text = _CTRL.sub("", text).replace(" ", " ")
    text = _BULLET.sub("", text)
    return re.sub(r"\s+", " ", text).strip()
