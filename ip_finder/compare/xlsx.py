"""비교 결과 Excel 세 가지: 실행 비교(compare-runs), 분류기 비교(compare-classifiers), 사다리(ladder).
사람이 보고서에 옮겨 적을 수 있게 요약 시트를 맨 앞에 두고, 문장 단위 근거는 뒤 시트에 둔다."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .. import __version__
from ..config import CLASSIFIER_NAMES
from ..goldmap import LABELS
from ..post import STATUSES
from .records import KIND_ORDER, RunDiff

HEAD_FILL = PatternFill("solid", fgColor="37474F")
HEAD_FONT = Font(bold=True, color="FFFFFF")
WRAP = Alignment(wrap_text=True, vertical="top")
UP = PatternFill("solid", fgColor="DCEDC8")
DOWN = PatternFill("solid", fgColor="FFCDD2")


def _sheet(wb: Workbook, title: str, headers: list[str], widths: list[int], first: bool = False):
    ws = wb.active if first else wb.create_sheet()
    ws.title = title[:31]
    ws.append(headers)
    for c in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill, cell.font = HEAD_FILL, HEAD_FONT
        ws.column_dimensions[get_column_letter(c)].width = widths[c - 1] if c - 1 < len(widths) else 12
    ws.freeze_panes = "A2"
    return ws


def _finish(ws, n_cols: int) -> None:
    if ws.max_row > 1:
        ws.auto_filter.ref = f"A1:{get_column_letter(n_cols)}{ws.max_row}"
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = WRAP


def _pct(v) -> str:
    return "-" if v is None else f"{v:.1%}"


def _delta(v: int) -> str:
    return f"{v:+d}" if v else "0"


def _color_delta(ws, row: int, col: int, v: int, good_when_down: bool = False) -> None:
    if not v:
        return
    better = (v < 0) if good_when_down else (v > 0)
    ws.cell(row=row, column=col).fill = UP if better else DOWN


# ------------------------------------------------------------------ 실행 비교
def write_runs_compare(diffs: list[RunDiff], out: Path, title_a: str = "A", title_b: str = "B", gold: list[tuple[dict, dict]] | None = None) -> Path:
    wb = Workbook()
    ws = _sheet(wb, "요약", ["파일", "상태", f"{title_a}", f"{title_b}", "증감"], [28, 16, 10, 10, 8], first=True)
    total: dict[str, list[int]] = {s: [0, 0] for s in STATUSES}
    for d in diffs:
        for s, a, b, dl in d.summary_rows():
            ws.append([d.a.name, s, a, b, _delta(dl)])
            if s in total:
                total[s][0] += a
                total[s][1] += b
    if len(diffs) > 1:
        for s, (a, b) in total.items():
            ws.append(["(전체 합)", s, a, b, _delta(b - a)])
    ws.append([])
    ws.append(["변경 종류", "건수(전체 파일)", "", "", ""])
    kinds: Counter = Counter()
    for d in diffs:
        kinds.update(d.counts())
    for k in KIND_ORDER:
        ws.append(["", k, kinds.get(k, 0), "", ""])
    ws.append([])
    ws.append(["검토 목록 등급 분포", "등급", title_a, title_b, "증감"])
    ga: Counter = Counter()
    gb: Counter = Counter()
    for d in diffs:
        ga.update(d.a.grade_counts())
        gb.update(d.b.grade_counts())
    for g in ("A", "B", "C", "D"):
        ws.append(["", g, ga.get(g, 0), gb.get(g, 0), _delta(gb.get(g, 0) - ga.get(g, 0))])
    ws.append([])
    ws.append(["처리 시간(초)", "", round(sum(d.a.elapsed for d in diffs), 1), round(sum(d.b.elapsed for d in diffs), 1), ""])
    ws.append(["비교 기준", f"{title_a}: 이전·기준 / {title_b}: 이후·비교. 문장 맞추기: 동일(공백 무시) → 포함(합쳐짐·나뉨) → 유사(0.6 이상)", "", "", ""])
    _finish(ws, 5)

    ws = _sheet(wb, "설정 차이", ["파일", "달라진 설정"], [28, 100])
    for d in diffs:
        for s in d.settings_diff or ["설정 차이 없음 (결과 파일에 설정 표가 없으면 비교하지 못함)"]:
            ws.append([d.a.name, s])
    _finish(ws, 2)

    ws = _sheet(wb, "변경 문장", ["파일", "변경", "페이지", f"{title_a} 발췌", f"{title_a} 상태", f"{title_a} 등급", f"{title_a} 점수",
                                f"{title_b} 발췌", f"{title_b} 상태", f"{title_b} 등급", f"{title_b} 점수", "설명"],
                [20, 12, 7, 46, 11, 6, 6, 46, 11, 6, 6, 44])
    for d in diffs:
        for ch in d.changes:
            ws.append([d.a.name, ch["kind"], ch["page"], ch["a_text"], ch["a_status"], ch["a_grade"], ch["a_score"],
                       ch["b_text"], ch["b_status"], ch["b_grade"], ch["b_score"], ch["desc"]])
    if ws.max_row == 1:
        ws.append(["", "", "", "달라진 문장이 없습니다."])
    _finish(ws, 12)

    ws = _sheet(wb, "페이지별", ["파일", "페이지", f"{title_a} 문장", f"{title_a} 목록", f"{title_b} 문장", f"{title_b} 목록", "목록 증감"], [24, 7, 9, 9, 9, 9, 9])
    for d in diffs:
        pages = sorted({u.page for u in d.a.units} | {u.page for u in d.b.units})
        for p in pages:
            ua = [u for u in d.a.units if u.page == p]
            ub = [u for u in d.b.units if u.page == p]
            ra, rb = sum(1 for u in ua if u.in_review), sum(1 for u in ub if u.in_review)
            ws.append([d.a.name, p, len(ua), ra, len(ub), rb, _delta(rb - ra)])
    _finish(ws, 7)

    if gold:
        ws = _sheet(wb, "골드 지표", ["파일", "지표", title_a, title_b], [24, 26, 12, 12])
        for d, (ma, mb) in zip(diffs, gold):
            for key, name in (("recall", "A·B 재현율"), ("precision", "A·B 정밀도(골드 기준)"), ("grade_accuracy", "등급 정확도"),
                              ("review", "검토 목록 수"), ("review_unscored", "그중 골드 밖(미채점)"), ("matched", "맞춰진 골드 문장"), ("gold_rows", "골드 문장 수")):
                va, vb = (ma or {}).get(key), (mb or {}).get(key)
                fmt = _pct if key in ("recall", "precision", "grade_accuracy") else (lambda v: "-" if v is None else v)
                ws.append([d.a.name, name, fmt(va), fmt(vb)])
        _finish(ws, 4)

    ws = _sheet(wb, "실행 정보", ["항목", "값"], [20, 100])
    ws.append(["프로그램 버전", __version__])
    ws.append([f"{title_a}", "; ".join(d.a.path or d.a.name for d in diffs)])
    ws.append([f"{title_b}", "; ".join(d.b.path or d.b.name for d in diffs)])
    ws.append(["파일 수", len(diffs)])
    _finish(ws, 2)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out))
    return out


# ------------------------------------------------------------------ 분류기 비교
def write_classifier_compare(result: dict, out: Path) -> Path:
    reps = result["reports"]
    y = result["y"]
    wb = Workbook()
    ws = _sheet(wb, "요약", ["분류기", "학습", "임베딩", "등급 정확도", "정확도 표준편차", "거시 F1", "A·B 재현율", "A·B 정밀도", "후보 수", "학습·판정 시간(초)", "비고"],
                [26, 6, 7, 11, 13, 9, 11, 11, 8, 15, 40], first=True)
    for r in reps:
        c = r.candidates or {}
        ws.append([r.label, "O" if r.trainable else "X", "O" if r.needs_embedding else "X", _pct(r.accuracy), _pct(r.acc_std) if r.acc_std is not None else "-",
                   _pct(r.macro_f1), _pct(c.get("recall")) if c else "-", _pct(c.get("precision")) if c else "-", c.get("candidates", "-") if c else "-",
                   round(r.fit_sec + r.predict_sec, 2), r.skipped])
    ws.append([])
    ws.append(["골드", f"{result['n']}문장, 등급별 {result['gold_counts']}, 파일 {len(result['files'])}개"])
    ws.append(["채점 방식", f"학습형: 층화 {result['k']}겹 교차 검증 × {result['repeats']}회 (seed {result['seed']}~), 학습 없는 분류기: 전체 골드 채점"])
    ws.append(["임베딩", result["embed_model"] or result.get("embed_error") or "-", f"{result['embed_sec']:.1f}초"])
    ws.append(["주의", "골드가 100문장 미만이면 정확도 몇 %p 차이는 겹 나누기에 따라 바뀌는 잡음일 수 있습니다. '정확도 표준편차' 보다 작은 차이는 같은 것으로 보세요."])
    _finish(ws, 11)

    ws = _sheet(wb, "등급별", ["분류기", "등급", "골드 수", "정밀도", "재현율", "F1"], [26, 6, 8, 9, 9, 9])
    for r in reps:
        if r.skipped:
            continue
        for g in LABELS:
            m = r.per_grade.get(g, {})
            ws.append([r.label, g, m.get("support", 0), _pct(m.get("precision")), _pct(m.get("recall")), _pct(m.get("f1"))])
    _finish(ws, 6)

    ws = _sheet(wb, "혼동 행렬", ["분류기", "정답 ＼ 예측", *LABELS, "?"], [26, 12, 6, 6, 6, 6, 6, 6])
    for r in reps:
        if r.skipped:
            continue
        for g in LABELS:
            row = r.confusion.get(g, {})
            ws.append([r.label, g, *[row.get(p, 0) for p in LABELS], row.get("?", 0)])
        ws.append([])
    _finish(ws, 8)

    heads = ["번호", "파일", "제목", "문장", "정답"]
    for r in reps:
        if not r.skipped:
            heads += [r.label, f"{r.label} 확신"]
    heads.append("맞힌 분류기 수")
    ws = _sheet(wb, "문장별", heads, [6, 16, 18, 56, 6] + [10, 7] * sum(1 for r in reps if not r.skipped) + [10])
    active = [r for r in reps if not r.skipped]
    for i, (t, g) in enumerate(zip(result["texts"], y), 1):
        row = [i, str(result["files"][0]) if len(result["files"]) == 1 else "", result["titles"][i - 1], t, g]
        hits = 0
        for r in active:
            p = r.preds[i - 1] if i - 1 < len(r.preds) else None
            row += [p.label if p else "?", round(p.confidence, 2) if p else ""]
            hits += 1 if (p and p.label == g) else 0
        row.append(hits)
        ws.append(row)
        for k, r in enumerate(active):
            p = r.preds[i - 1] if i - 1 < len(r.preds) else None
            if p is not None:
                ws.cell(row=ws.max_row, column=6 + 2 * k).fill = UP if p.label == g else DOWN
    _finish(ws, len(heads))

    ws = _sheet(wb, "불일치", ["번호", "문장", "정답", "분류기별 판정", "맞힌 분류기 수"], [6, 60, 6, 60, 10])
    for i, (t, g) in enumerate(zip(result["texts"], y), 1):
        labels = {r.label: (r.preds[i - 1].label if i - 1 < len(r.preds) and r.preds[i - 1] else "?") for r in active}
        if len(set(labels.values())) > 1:
            ws.append([i, t, g, ", ".join(f"{k}={v}" for k, v in labels.items()), sum(1 for v in labels.values() if v == g)])
    _finish(ws, 5)

    ws = _sheet(wb, "실행 정보", ["항목", "값"], [20, 100])
    for k, v in (("프로그램 버전", __version__), ("골드 파일", ", ".join(result["files"])), ("골드 문장 수", result["n"]),
                 ("대상 등급", result["targets"]), ("임베딩 모델", result["embed_model"] or "-"),
                 ("분류기", ", ".join(f"{r.name}({CLASSIFIER_NAMES.get(r.name, r.name)})" for r in reps))):
        ws.append([k, v])
    _finish(ws, 2)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out))
    return out


# ------------------------------------------------------------------ 사다리
def write_ladder(result, out: Path) -> Path:
    from .ladder import LadderResult
    assert isinstance(result, LadderResult)
    steps = result.steps
    mode_ko = "누적 (직전 칸과 비교)" if result.ladder.mode == "cumulative" else "단독 (기준선과 비교)"
    wb = Workbook()
    heads = ["칸", "켠 것", "문장 단위", *STATUSES, "A", "B", "증감(검토 목록)", "처리 시간(초)"]
    if result.gold_used:
        heads += ["A·B 재현율", "A·B 정밀도", "등급 정확도", "골드 밖 후보"]
    ws = _sheet(wb, "사다리 요약", heads, [18, 44, 9] + [9] * len(STATUSES) + [6, 6, 12, 10, 10, 10, 10, 10], first=True)
    prev = None
    for sr in steps:
        tot = sr.totals()
        gc = sr.grade_counts()
        what = ("아무것도 켜지 않음" if sr.index < 0 else
                (" + ".join(s.label for s in result.ladder.steps[:sr.index + 1]) if result.ladder.mode == "cumulative" else sr.label))
        review = tot.get("검토 목록", 0)
        base = steps[0] if result.ladder.mode == "single" else prev
        delta = "" if base is None else _delta(review - base.totals().get("검토 목록", 0))
        row = [sr.title, what, sum(tot.values()), *[tot.get(s, 0) for s in STATUSES], gc.get("A", 0), gc.get("B", 0), delta, round(sr.elapsed, 1)]
        if result.gold_used:
            g = sr.gold or {}
            row += [_pct(g.get("recall")), _pct(g.get("precision")), _pct(g.get("grade_accuracy")), g.get("review_unscored", "-")]
        ws.append(row)
        prev = sr
    ws.append([])
    ws.append(["방식", mode_ko])
    ws.append(["입력", f"{len(result.inputs)}개 파일: " + ", ".join(p.name for p in result.inputs)])
    ws.append(["결과 폴더", str(result.out_dir)])
    ws.append(["읽는 법", "칸마다 그 설정으로 모든 파일을 다시 실행했습니다. '증감'은 검토 목록 문장 수의 변화, 문장 단위 근거는 '칸별 변화' 시트입니다."])
    _finish(ws, len(heads))

    ws = _sheet(wb, "칸별 변화", ["칸", "비교 기준", "파일", "변경", "페이지", "이전 발췌", "이전 상태", "이전 등급", "현재 발췌", "현재 상태", "현재 등급", "설명"],
                [16, 12, 18, 12, 7, 44, 11, 6, 44, 11, 6, 40])
    for base, sr, dl in result.diffs:
        for d in dl:
            for ch in d.changes:
                ws.append([sr.title, base.title, d.a.name, ch["kind"], ch["page"], ch["a_text"], ch["a_status"], ch["a_grade"],
                           ch["b_text"], ch["b_status"], ch["b_grade"], ch["desc"]])
    if ws.max_row == 1:
        ws.append(["", "", "", "달라진 문장이 없습니다."])
    _finish(ws, 12)

    ws = _sheet(wb, "변경 종류별", ["칸", *KIND_ORDER], [18] + [11] * len(KIND_ORDER))
    for base, sr, dl in result.diffs:
        c: Counter = Counter()
        for d in dl:
            c.update(d.counts())
        ws.append([sr.title, *[c.get(k, 0) for k in KIND_ORDER]])
    _finish(ws, 1 + len(KIND_ORDER))

    ws = _sheet(wb, "파일별", ["칸", "파일", *STATUSES, "처리 시간(초)"] + (["A·B 재현율", "A·B 정밀도"] if result.gold_used else []),
                [18, 28] + [9] * len(STATUSES) + [10, 10, 10])
    for sr in steps:
        for n, r in enumerate(sr.records):
            c = r.by_status()
            row = [sr.title, r.name, *[c.get(s, 0) for s in STATUSES], round(r.elapsed, 1)]
            if result.gold_used:
                g = sr.per_file_gold[n] if n < len(sr.per_file_gold) else {}
                row += [_pct(g.get("recall")) if g else "-", _pct(g.get("precision")) if g else "-"]
            ws.append(row)
    _finish(ws, len(STATUSES) + 5)

    ws = _sheet(wb, "칸 설정", ["칸", "설정", "값"], [18, 28, 60])
    for sr in steps:
        for k, v in sr.cfg.fingerprint().items():
            ws.append([sr.title, k, v if isinstance(v, (int, float, str)) else ", ".join(map(str, v))])
    _finish(ws, 3)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out))
    return out
