"""Excel 리포트: 검토 목록 / 보류 / 제외 문장 / 페이지 / 변경 사항 / 제외 페이지 / 이미지 페이지 / 실행 정보.
검토 목록·보류·제외 문장 시트에는 '피드백' 열이 있어 O / X / A~D 를 적으면 ip-finder feedback 이 골드 시트로 가져간다."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from ..models import Document, LabeledLine, RunInfo
from ..post import in_hold_list, in_review_list
from ..post.templates import discussion_point
from ..prep.page_rules import IMAGE_PAGE
from ..prep.page_type import page_type

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
FEEDBACK_FILL = PatternFill("solid", fgColor="FFFDE7")
WRAP = Alignment(wrap_text=True, vertical="top")
SOURCE_NAME = {"clf": "분류기", "llm": "LLM", "verified": "분류기+LLM", "gold": "골드"}
FEEDBACK_HELP = "O=맞음, X=틀림(제외), A/B/C/D=올바른 등급"

LINE_HEADERS = ["번호", "섹션", "페이지", "줄", "등급", "발췌", "논의 포인트", "점수", "가중치", "판정", "비고", "피드백", "메모"]
LINE_WIDTHS = [6, 14, 8, 5, 6, 64, 36, 7, 7, 11, 28, 8, 24]
FEEDBACK_COL = LINE_HEADERS.index("피드백") + 1


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


def _finish(ws, n_cols: int, feedback_col: int | None = None) -> None:
    if ws.max_row > 1:
        ws.auto_filter.ref = f"A1:{get_column_letter(n_cols)}{ws.max_row}"
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = WRAP
    if feedback_col and ws.max_row > 1:
        col = get_column_letter(feedback_col)
        dv = DataValidation(type="list", formula1='"O,X,A,B,C,D"', allow_blank=True, showErrorMessage=False)
        dv.promptTitle, dv.prompt = "피드백", FEEDBACK_HELP
        ws.add_data_validation(dv)
        dv.add(f"{col}2:{col}{ws.max_row}")
        for r in range(2, ws.max_row + 1):
            ws.cell(row=r, column=feedback_col).fill = FEEDBACK_FILL
            ws.cell(row=r, column=feedback_col + 1).fill = FEEDBACK_FILL


def _line_row(n: int, ll: LabeledLine, extra: list | None = None) -> list:
    return [n, ll.section, ll.page_no, ll.line_idx, ll.label, ll.text, discussion_point(ll.label), ll.score, ll.page_weight,
            SOURCE_NAME.get(ll.source, ll.source), ", ".join(ll.notes), "", ""] + (extra or [])


def write_report(out: Path, doc: Document, labeled: list[LabeledLine], info: RunInfo,
                 removed: Counter | None = None, changes: list[dict] | None = None) -> Path:
    wb = Workbook()

    ws = _sheet(wb, "검토 목록", LINE_HEADERS, LINE_WIDTHS, first=True)
    n = 0
    for ll in labeled:
        if not in_review_list(ll):
            continue
        n += 1
        ws.append(_line_row(n, ll))
        ws.cell(row=ws.max_row, column=5).fill = FILLS[ll.label]
    _finish(ws, len(LINE_HEADERS), FEEDBACK_COL)

    ws = _sheet(wb, "보류", LINE_HEADERS + ["보류 사유"], LINE_WIDTHS + [40])
    n = 0
    for ll in labeled:
        if not in_hold_list(ll):
            continue
        n += 1
        reason = ll.hold_reason or ("모델은 제외, 기술 단서어 있음" if ll.label == "X?" else "판정 실패")
        ws.append(_line_row(n, ll, [reason]))
        ws.cell(row=ws.max_row, column=5).fill = FILLS.get(ll.label, FILLS["X?"])
    _finish(ws, len(LINE_HEADERS) + 1, FEEDBACK_COL)

    ws = _sheet(wb, "제외 문장", LINE_HEADERS, LINE_WIDTHS)
    n = 0
    for ll in labeled:
        if ll.label != "X":
            continue
        n += 1
        ws.append(_line_row(n, ll))
    _finish(ws, len(LINE_HEADERS), FEEDBACK_COL)

    ws = _sheet(wb, "페이지", ["페이지", "제목", "유형", "가중치", "가중치 근거", "상태", "문장", "목록", "보류", "제목 출처"], [8, 48, 10, 8, 22, 26, 7, 7, 7, 10])
    by_page: dict[int, list[LabeledLine]] = {}
    for ll in labeled:
        by_page.setdefault(ll.page_no, []).append(ll)
    for p in doc.pages:
        rows = by_page.get(p.no, [])
        state = p.excluded_reason or "판정"
        ws.append([p.no, p.title, page_type(p.title)[0], p.weight, p.weight_reason, state, len(rows),
                   sum(1 for ll in rows if in_review_list(ll)), sum(1 for ll in rows if in_hold_list(ll)), p.title_source])
    _finish(ws, 10)

    ws = _sheet(wb, "변경 사항", ["변경", "페이지", "줄", "발췌", "이전", "현재", "목록", "판정", "설명"], [10, 8, 5, 64, 8, 8, 6, 11, 44])
    if info.prev_run_id:
        ws.append(["기준", "", "", f"직전 실행 {info.prev_run_id} 과 비교 (현재 {info.run_id})", "", "", "", "", ""])
        for s in info.settings_diff or ["설정 변경 없음"]:
            ws.append(["설정", "", "", s, "", "", "", "", ""])
        for r in changes or []:
            ws.append([r["kind"], r["page"], r["line"], r["text"], r["old"], r["new"], r["in_list"], r["source"], r["desc"]])
        if not changes:
            ws.append(["", "", "", "변경된 문장 없음", "", "", "", "", ""])
    else:
        ws.append(["", "", "", "이 파일의 이전 실행 기록이 없어 비교하지 않았습니다. 다음 실행부터 여기에 달라진 행이 적힙니다.", "", "", "", "", ""])
    _finish(ws, 9)

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

    ws = _sheet(wb, "실행 정보", ["항목", "값"], [24, 90])
    grade_counts = Counter(ll.label for ll in labeled)
    list_counts = Counter(ll.label for ll in labeled if in_review_list(ll))
    rows = [
        ("입력 파일", info.source), ("실행 ID", info.run_id or "-"), ("직전 실행 ID", info.prev_run_id or "-"),
        ("판정 모드", info.mode), ("LLM 모델", info.model), ("프롬프트 버전", info.prompt_version),
        ("임베딩 모델", info.embed_model or "-"), ("분류기", info.classifier or "-"),
        ("확신 임계값", info.threshold if info.threshold is not None else "-"),
        ("목록 점수 기준", info.accept_score), ("점수 미달 보류", info.held_lines),
        ("LLM 재확인 문장", f"{info.verify_lines} (등급 바뀜 {info.verify_changed})" if info.verify_lines else "-"),
        ("골드 정답 반영", f"{info.gold_lines}문장 (모델 판정과 달랐던 것 {info.gold_changed}) / 읽은 골드: {info.gold_desc}" if info.gold_desc else "없음 (골드 파일이 없거나 use_gold=false)"),
        ("분류기 채택 문장", info.clf_lines), ("LLM 판정 문장", info.llm_lines),
        ("임베딩 시간(초)", round(info.embed_sec, 1)), ("LLM 시간(초)", round(info.llm_sec, 1)),
        ("시작", info.started_at), ("소요 시간(초)", round(info.elapsed_sec, 1)),
        ("페이지 수", info.pages_total), ("라벨링 페이지", info.pages_labeled),
        ("제외 페이지", info.pages_excluded), ("이미지 페이지", info.pages_image),
        ("LLM 호출", info.llm_calls), ("캐시 적중", info.cache_hits),
        ("검토 목록", ", ".join(f"{g}: {list_counts.get(g, 0)}" for g in ("A", "B", "C", "D")) + f" (합 {sum(list_counts.values())})"),
        ("등급 분포(전체)", ", ".join(f"{g}: {grade_counts.get(g, 0)}" for g in ("A", "B", "C", "D", "X", "X?", "?"))),
        ("직전 실행 대비", ", ".join(f"{k}: {v}" for k, v in (info.changes or {}).items() if k != "total" and v) or ("변경 없음" if info.prev_run_id else "-")),
        ("달라진 설정", "; ".join(info.settings_diff) or "-"),
        ("전처리로 제거된 줄", ", ".join(f"{k}: {v}" for k, v in (removed or {}).items()) or "없음"),
        ("경고", "; ".join(info.warnings) or "없음"),
        ("피드백 방법", f"검토 목록·보류·제외 문장 시트의 '피드백' 열에 {FEEDBACK_HELP}. 저장 후 UI '정확도 관리 → 피드백 가져오기' 또는 ip-finder feedback <이 파일>"),
    ]
    for r in rows:
        ws.append(list(r))
    _finish(ws, 2)

    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out))
    return out
