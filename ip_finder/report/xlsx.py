"""Excel 리포트 (0단계).
시트: 검토 목록 / 보류 / 분류기 제외 (참고) / 후처리 제외 / 전처리 제외 / 페이지 / 변경 사항 / 제외 페이지 / 이미지 페이지 / 실행 정보.
- 문장 시트의 열은 모두 같다(LINE_HEADERS). '확신'은 분류기가 낸 신뢰도(0~1), '판정'은 분류기/골드.
- '전처리 제외'에는 규칙에 걸린 줄과 제외된 쪽의 줄이 사유와 함께 들어가 스위치가 무엇을 뺐는지 사람이 바로 본다.
- '실행 정보'에는 스위치 표와 '설정 <이름>' 행이 있어 비교 명령(compare-runs)이 결과 파일만으로 설정 차이를 읽는다.
검토 목록·보류·제외 시트에는 '피드백' 열이 있어 O / X / A~D 를 적으면 ip-finder feedback 이 골드 시트로 가져간다."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from .. import STAGE, __version__
from ..config import CLASSIFIER_NAMES, Config
from ..models import Document, LabeledLine, RunInfo
from ..post import (STATUS_CLF_OUT, STATUS_HOLD, STATUS_PAGE_OUT, STATUS_POST_OUT, STATUS_PREP_OUT, STATUS_REVIEW,
                    in_hold_list, in_review_list, is_stage1_out, is_stage2_out)
from ..post.templates import discussion_point
from ..prep.page_rules import IMAGE_PAGE
from ..switches import describe as describe_switches, table_rows

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
SOURCE_NAME = {"clf": "분류기", "gold": "골드"}
FEEDBACK_HELP = "O=맞음, X=틀림(제외), A/B/C/D=올바른 등급"

SHEET_REVIEW, SHEET_HOLD, SHEET_CLF_OUT, SHEET_POST_OUT, SHEET_PREP_OUT = STATUS_REVIEW, STATUS_HOLD, "분류기 제외 (참고)", STATUS_POST_OUT, STATUS_PREP_OUT
SHEET_PAGES, SHEET_CHANGES, SHEET_INFO = "페이지", "변경 사항", "실행 정보"
LINE_HEADERS = ["번호", "섹션", "페이지", "줄", "등급", "발췌", "논의 포인트", "점수", "가중치", "확신", "판정", "비고", "피드백", "메모"]
LINE_WIDTHS = [6, 14, 8, 5, 6, 60, 34, 7, 7, 7, 8, 28, 8, 24]
FEEDBACK_COL = LINE_HEADERS.index("피드백") + 1
PREP_HEADERS = ["페이지", "상태", "사유", "발췌", "출처"]
SETTING_PREFIX = "설정 "          # 실행 정보에서 설정 행의 접두어. compare-runs 가 이 접두어로 설정을 읽는다

is_clf_rejected = is_stage1_out
is_post_rejected = is_stage2_out
is_held = in_hold_list


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
            ll.clf_conf if ll.clf_conf is not None else "", SOURCE_NAME.get(ll.source, ll.source), ", ".join(ll.notes), "", ""] + (extra or [])


def _line_sheet(wb, title, rows: list[LabeledLine], first=False, extra_header: str | None = None, extra_of=None, note: str | None = None):
    headers = LINE_HEADERS + ([extra_header] if extra_header else [])
    widths = LINE_WIDTHS + ([40] if extra_header else [])
    ws = _sheet(wb, title, headers, widths, first=first)
    for n, ll in enumerate(rows, 1):
        ws.append(_line_row(n, ll, [extra_of(ll)] if extra_of else None))
        ws.cell(row=ws.max_row, column=5).fill = FILLS.get(ll.label, FILLS["X?"]) if ll.label in FILLS else PatternFill()
    if not rows and note:
        ws.append(["", "", "", "", "", note])
    _finish(ws, len(headers), FEEDBACK_COL)
    return ws


def prep_rows(doc: Document) -> list[list]:
    """'전처리 제외' 시트 행: 규칙에 걸린 줄(상태 전처리 제외, 사유 = 규칙 이름)과 제외된 쪽의 줄(상태 페이지 제외, 사유 = 쪽 제외 사유)."""
    src_name = {"body": "본문", "table": "표", "diagram": "도형"}
    out = []
    for p in doc.pages:
        for ln in p.lines:
            if not ln.text.strip():
                continue
            if ln.removed_by:                       # 줄 규칙이 먼저 (규칙 때문에 쪽이 비어 제외된 경우 규칙 이름이 더 정확하다)
                out.append([p.no, STATUS_PREP_OUT, ln.removed_by, ln.text, src_name.get(ln.source, ln.source)])
            elif p.excluded_reason is not None:
                out.append([p.no, STATUS_PAGE_OUT, p.excluded_reason, ln.text, src_name.get(ln.source, ln.source)])
    return out


def write_report(out: Path, doc: Document, labeled: list[LabeledLine], info: RunInfo,
                 removed: Counter | None = None, changes: list[dict] | None = None, cfg: Config | None = None) -> Path:
    wb = Workbook()
    _line_sheet(wb, SHEET_REVIEW, [ll for ll in labeled if in_review_list(ll)], first=True, note="검토 목록에 오른 문장이 없습니다.")

    def hold_reason(ll: LabeledLine) -> str:
        return ll.hold_reason or ("분류기는 제외, 기술 단서어 있음" if ll.label == "X?" else "판정 실패")

    _line_sheet(wb, SHEET_HOLD, [ll for ll in labeled if in_hold_list(ll)], extra_header="보류 사유", extra_of=hold_reason, note="보류된 문장이 없습니다.")
    _line_sheet(wb, SHEET_CLF_OUT, [ll for ll in labeled if is_stage1_out(ll)],
                note=f"분류기가 {info.target_grades} 밖으로 본 문장이 없습니다.")
    _line_sheet(wb, SHEET_POST_OUT, [ll for ll in labeled if is_stage2_out(ll)],
                note="분류기는 통과시켰지만 후처리(보정)나 골드가 대상 등급 밖으로 바꾼 문장이 없습니다.")

    ws = _sheet(wb, SHEET_PREP_OUT, PREP_HEADERS, [8, 11, 26, 64, 6])
    rows = prep_rows(doc)
    for r in rows:
        ws.append(r)
    if not rows:
        ws.append(["", "", "", "전처리·페이지 규칙에 걸린 줄이 없습니다 (스위치가 모두 꺼져 있으면 비어 있는 것이 정상)."])
    _finish(ws, len(PREP_HEADERS))

    ws = _sheet(wb, SHEET_PAGES, ["페이지", "제목", "관련성", "가중치", "근거", "상태", "문장", "목록", "보류", "분류기 제외", "후처리 제외", "전처리 제외", "제목 출처"],
                [8, 48, 8, 8, 22, 26, 7, 7, 7, 9, 9, 9, 10])
    by_page: dict[int, list[LabeledLine]] = {}
    for ll in labeled:
        by_page.setdefault(ll.page_no, []).append(ll)
    for p in doc.pages:
        rows_p = by_page.get(p.no, [])
        ws.append([p.no, p.title, p.relevance, p.weight, p.weight_reason, p.excluded_reason or "판정", len(rows_p),
                   sum(1 for ll in rows_p if in_review_list(ll)), sum(1 for ll in rows_p if in_hold_list(ll)),
                   sum(1 for ll in rows_p if is_stage1_out(ll)), sum(1 for ll in rows_p if is_stage2_out(ll)),
                   sum(1 for ln in p.lines if ln.removed_by and ln.text.strip()), p.title_source])
    _finish(ws, 13)

    ws = _sheet(wb, SHEET_CHANGES, ["변경", "페이지", "줄", "발췌", "이전", "현재", "목록", "판정", "설명"], [10, 8, 5, 64, 8, 8, 6, 11, 44])
    if info.prev_run_id:
        ws.append(["기준", "", "", f"직전 실행 {info.prev_run_id} 과 비교 (현재 {info.run_id})", "", "", "", "", ""])
        for s in info.settings_diff or ["설정 변경 없음"]:
            ws.append(["설정", "", "", s, "", "", "", "", ""])
        for r in changes or []:
            ws.append([r["kind"], r["page"], r["line"], r["text"], r["old"], r["new"], r["in_list"], r["source"], r["desc"]])
        if not changes:
            ws.append(["", "", "", "변경된 문장 없음", "", "", "", "", ""])
    else:
        ws.append(["", "", "", "이 파일의 이전 실행 기록이 없어 비교하지 않았습니다. 두 결과 파일을 직접 비교하려면 ip-finder compare-runs A.xlsx B.xlsx", "", "", "", "", ""])
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

    ws = _sheet(wb, SHEET_INFO, ["항목", "값"], [26, 100])
    grade_counts = Counter(ll.label for ll in labeled)
    list_counts = Counter(ll.label for ll in labeled if in_review_list(ll))
    n_clf_out = sum(1 for ll in labeled if is_stage1_out(ll))
    n_post_out = sum(1 for ll in labeled if is_stage2_out(ll))
    n_prep = len(rows)
    rows_info = [
        ("입력 파일", info.source), ("실행 ID", info.run_id or "-"), ("직전 실행 ID", info.prev_run_id or "-"),
        ("프로그램 버전", info.version or __version__), ("단계", STAGE),
        ("읽기 방식", "레이아웃 분석" if info.reader == "layout" else "원시 읽기 (레이아웃 분석 끔)"),
        ("스위치", describe_switches(cfg) if cfg is not None else ", ".join(f"{k}={'켬' if v else '끔'}" for k, v in info.switches.items())),
        ("1차 분류기", f"{CLASSIFIER_NAMES.get(info.classifier_name, info.classifier_name)} — {info.classifier}"),
        ("임베딩 모델", info.embed_model or "- (이 분류기는 임베딩을 쓰지 않음)"),
        ("추출 등급", info.target_grades),
        ("판정 흐름", f"읽기 → 전처리 → 1차 분류기({info.target_grades} 만 통과) → 후처리 → 점수 ≥ {info.accept_score} 이면 검토 목록, 미만은 보류"),
        ("단계별 문장 수", f"판정 {len(labeled)} → 분류기 제외 {n_clf_out} → 후처리 제외 {n_post_out} → 보류 {sum(1 for ll in labeled if in_hold_list(ll))} → 검토 목록 {sum(list_counts.values())}  (전처리·페이지 제외 줄 {n_prep})"),
        ("페이지 가중치", f"{'켬' if info.page_weight_enabled else '끔'} (관련성 낮음 {info.low_relevance_weight}, 낮음 페이지 {info.pages_low}개)"),
        ("목록 점수 기준", info.accept_score), ("점수 미달 보류", info.held_lines),
        ("골드 정답 반영", f"{info.gold_lines}문장 (분류기 판정과 달랐던 것 {info.gold_changed}) / 읽은 골드: {info.gold_desc}" if info.gold_desc else "없음 (골드 파일이 없거나 use_gold=false)"),
        ("임베딩 시간(초)", round(info.embed_sec, 1)), ("분류 시간(초)", round(info.classify_sec, 2)),
        ("시작", info.started_at), ("소요 시간(초)", round(info.elapsed_sec, 1)),
        ("페이지 수", info.pages_total), ("판정 페이지", info.pages_labeled),
        ("제외 페이지", info.pages_excluded), ("이미지 페이지", info.pages_image), ("임베딩 캐시 적중", info.cache_hits),
        ("검토 목록", ", ".join(f"{g}: {list_counts.get(g, 0)}" for g in info.target_grades.split(",")) + f" (합 {sum(list_counts.values())})"),
        ("등급 분포(판정 문장)", ", ".join(f"{g}: {grade_counts.get(g, 0)}" for g in ("A", "B", "C", "D", "X", "X?", "?"))),
        ("직전 실행 대비", ", ".join(f"{k}: {v}" for k, v in (info.changes or {}).items() if k != "total" and v) or ("변경 없음" if info.prev_run_id else "-")),
        ("달라진 설정", "; ".join(info.settings_diff) or "-"),
        ("전처리로 제거된 줄", ", ".join(f"{k}: {v}" for k, v in (removed or {}).items() if k != "빈 줄") or "없음"),
        ("경고", "; ".join(info.warnings) or "없음"),
        ("피드백 방법", f"검토 목록·보류·제외 시트의 '피드백' 열에 {FEEDBACK_HELP}. 저장 후 ip-finder feedback <이 파일>"),
    ]
    for r in rows_info:
        ws.append(list(r))
    ws.append(["", ""])
    ws.append(["스위치 표", "묶음 / 이름 / 상태 / 지금 일어나는 일"])
    if cfg is not None:
        for group, label, state, what in table_rows(cfg):
            ws.append([f"스위치 {label}", f"{state} — [{group}] {what}"])
        ws.append(["", ""])
        ws.append(["설정 표", "결과에 영향을 주는 설정 (compare-runs 가 읽는다)"])
        for k, v in cfg.fingerprint().items():
            ws.append([f"{SETTING_PREFIX}{k}", v if isinstance(v, (int, float, str)) else ", ".join(map(str, v))])
    _finish(ws, 2)

    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out))
    return out
