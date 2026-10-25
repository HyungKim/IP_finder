"""Excel 리포트: 검토 목록 / 보류 / 제외 페이지 / 이미지 페이지 / 실행 정보."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from ..models import Document, LabeledLine, RunInfo
from ..post.templates import discussion_point
from ..prep.page_rules import IMAGE_PAGE

FILLS = {
    "A": PatternFill("solid", fgColor="FFE0B2"),
    "B": PatternFill("solid", fgColor="FFF9C4"),
    "C": PatternFill("solid", fgColor="DCEDC8"),
    "D": PatternFill("solid", fgColor="BBDEFB"),
    "X?": PatternFill("solid", fgColor="EEEEEE"),
    "?": PatternFill("solid", fgColor="FFCDD2"),
}
HEAD_FILL = PatternFill("solid", fgColor="37474F")
HEAD_FONT = Font(bold=True, color="FFFFFF")
WRAP = Alignment(wrap_text=True, vertical="top")


def _sheet(wb: Workbook, title: str, headers: list[str], widths: list[int], first: bool = False):
    ws = wb.active if first else wb.create_sheet()
    ws.title = title
    ws.append(headers)
    for c in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill, cell.font = HEAD_FILL, HEAD_FONT
        ws.column_dimensions[get_column_letter(c)].width = widths[c - 1]
    ws.freeze_panes = "A2"
    return ws


def _finish(ws, n_cols: int) -> None:
    if ws.max_row > 1:
        ws.auto_filter.ref = f"A1:{get_column_letter(n_cols)}{ws.max_row}"
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = WRAP


def write_report(out: Path, doc: Document, labeled: list[LabeledLine], info: RunInfo,
                 removed: Counter | None = None) -> Path:
    wb = Workbook()
    headers = ["번호", "섹션", "페이지", "등급", "발췌", "논의 포인트", "비고"]
    widths = [6, 16, 8, 6, 70, 40, 22]

    ws = _sheet(wb, "검토 목록", headers, widths, first=True)
    n = 0
    for ll in labeled:
        if ll.label not in ("A", "B", "C", "D"):
            continue
        n += 1
        ws.append([n, ll.section, ll.page_no, ll.label, ll.text, discussion_point(ll.label), ", ".join(ll.notes)])
        ws.cell(row=ws.max_row, column=4).fill = FILLS[ll.label]
    _finish(ws, len(headers))

    ws = _sheet(wb, "보류", headers, widths)
    n = 0
    for ll in labeled:
        if ll.label not in ("X?", "?"):
            continue
        n += 1
        ws.append([n, ll.section, ll.page_no, ll.label, ll.text, discussion_point(ll.label), ", ".join(ll.notes)])
        ws.cell(row=ws.max_row, column=4).fill = FILLS[ll.label]
    _finish(ws, len(headers))

    ws = _sheet(wb, "제외 페이지", ["페이지", "제목", "사유"], [8, 50, 30])
    for p in doc.pages:
        if p.excluded_reason and p.excluded_reason != IMAGE_PAGE:
            ws.append([p.no, p.title, p.excluded_reason])
    _finish(ws, 3)

    ws = _sheet(wb, "이미지 페이지", ["페이지", "제목", "비고"], [8, 50, 40])
    for p in doc.pages:
        if p.excluded_reason == IMAGE_PAGE:
            ws.append([p.no, p.title, "텍스트 없음. 도면·그림이면 직접 확인"])
    _finish(ws, 3)

    ws = _sheet(wb, "실행 정보", ["항목", "값"], [24, 70])
    grade_counts = Counter(ll.label for ll in labeled)
    rows = [
        ("입력 파일", info.source), ("모델", info.model), ("프롬프트 버전", info.prompt_version),
        ("시작", info.started_at), ("소요 시간(초)", round(info.elapsed_sec, 1)),
        ("페이지 수", info.pages_total), ("라벨링 페이지", info.pages_labeled),
        ("제외 페이지", info.pages_excluded), ("이미지 페이지", info.pages_image),
        ("LLM 호출", info.llm_calls), ("캐시 적중", info.cache_hits),
        ("등급 분포", ", ".join(f"{g}: {grade_counts.get(g, 0)}" for g in ("A", "B", "C", "D", "X", "X?", "?"))),
        ("전처리로 제거된 줄", ", ".join(f"{k}: {v}" for k, v in (removed or {}).items()) or "없음"),
        ("경고", "; ".join(info.warnings) or "없음"),
    ]
    for r in rows:
        ws.append(list(r))
    _finish(ws, 2)

    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out))
    return out
