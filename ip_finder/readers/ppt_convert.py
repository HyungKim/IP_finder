"""구형 .ppt → .pptx 변환. 윈도우의 PowerPoint(COM, pywin32)가 필요하다. 변환본은 원본 옆에 만든다."""
from __future__ import annotations

import sys
from pathlib import Path

PP_SAVE_AS_OPENXML = 24   # ppSaveAsOpenXMLPresentation
PP_SAVE_AS_PDF = 32       # ppSaveAsPDF (2단계 썸네일용)


def convert_ppt_to_pptx(path: Path, out: Path | None = None) -> Path:
    out = out or path.with_suffix(".pptx")
    if out.exists():
        return out
    if sys.platform != "win32":
        raise RuntimeError(
            f"{path.name}: .ppt 변환은 윈도우의 PowerPoint(COM)에서만 가능합니다. "
            "PowerPoint에서 .pptx로 저장한 뒤 다시 실행하세요."
        )
    try:
        import win32com.client  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("pywin32가 필요합니다: pip install pywin32") from e
    app = win32com.client.Dispatch("PowerPoint.Application")
    pres = app.Presentations.Open(str(path.resolve()), True, False, False)  # ReadOnly, Untitled, WithWindow
    try:
        pres.SaveAs(str(out.resolve()), PP_SAVE_AS_OPENXML)
    finally:
        pres.Close()
    return out
