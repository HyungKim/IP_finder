"""골드 세트 라벨링 시트. 모델 초안 라벨을 '정답' 열에 미리 채워 두고, 사용자는 틀린 것만 고친다.
이 파일은 실제 보고서 문장을 담으므로 회사 PC의 프로젝트 바깥 폴더에만 둔다."""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from .. import PROMPT_VERSION
from ..config import Config
from ..pipeline import run_file

GOLD_HEADERS = ["번호", "파일", "페이지", "제목", "줄", "문장", "모델 라벨", "후처리 라벨", "정답", "메모"]
RUBRIC_PATH = Path(__file__).parent.parent / "label" / "prompts" / "rubric.md"


def make_gold_sheet(path: Path, cfg: Config, out: Path | None = None, client=None) -> Path:
    res = run_file(path, cfg, client)
    out = out or path.with_name(f"{path.stem}_gold.xlsx")
    wb = Workbook()
    ws = wb.active
    ws.title = "라벨링"
    ws.append(GOLD_HEADERS)
    for c in range(1, len(GOLD_HEADERS) + 1):
        ws.cell(row=1, column=c).font = Font(bold=True)
        ws.cell(row=1, column=c).fill = PatternFill("solid", fgColor="CFD8DC")
    for n, ll in enumerate(res.labeled, 1):
        answer = "X" if ll.raw_label in ("X", "X?") else ("" if ll.raw_label == "?" else ll.raw_label)
        ws.append([n, path.name, ll.page_no, ll.page_title, ll.line_idx, ll.text, ll.raw_label, ll.label, answer, ""])
    for col, w in zip("ABCDEFGHIJ", (6, 18, 8, 24, 5, 70, 10, 10, 8, 30)):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"

    ws2 = wb.create_sheet("안내")
    for line in [
        "정답 열에 A / B / C / D / X 중 하나를 적습니다. 모델 라벨이 미리 채워져 있으니 틀린 것만 고치세요.",
        "X는 기술 내용이 없는 문장입니다. 판정이 어려우면 X가 아닌 쪽으로 적습니다 (재현율 우선).",
        "채점: ip-finder eval <이 파일>   (현재 모델로 다시 라벨링해 채점)   /   --stored (저장된 라벨을 채점)",
        "", *RUBRIC_PATH.read_text(encoding="utf-8").splitlines(),
    ]:
        ws2.append([line])
    ws2.column_dimensions["A"].width = 120

    ws3 = wb.create_sheet("메타")
    for k, v in (("파일", str(path)), ("모델", cfg.model), ("프롬프트 버전", PROMPT_VERSION), ("생성", res.info.started_at)):
        ws3.append([k, v])
    wb.save(str(out))
    return out
