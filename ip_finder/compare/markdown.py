"""보고서에 바로 붙일 Markdown 요약. Excel 과 같은 숫자를 표로 적는다 (문장은 넣지 않는다)."""
from __future__ import annotations

from collections import Counter

from ..post import STATUSES
from .records import KIND_ORDER, RunDiff


def _pct(v) -> str:
    return "-" if v is None else f"{v:.1%}"


def _table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def runs_markdown(diffs: list[RunDiff], title_a: str = "A", title_b: str = "B", gold: list[tuple[dict, dict]] | None = None) -> str:
    total: dict[str, list[int]] = {s: [0, 0] for s in STATUSES}
    for d in diffs:
        sa, sb = d.a.by_status(), d.b.by_status()
        for s in STATUSES:
            total[s][0] += sa[s]
            total[s][1] += sb[s]
    rows = [[s, a, b, (f"{b - a:+d}" if b != a else "0")] for s, (a, b) in total.items()]
    kinds: Counter = Counter()
    for d in diffs:
        kinds.update(d.counts())
    lines = [f"## 실행 비교: {title_a} → {title_b}", "",
             f"파일 {len(diffs)}개. 문장 맞추기: 동일(공백 무시) → 포함(합쳐짐·나뉨) → 유사(0.6 이상).", "",
             "### 상태별 문장 수", "", _table(["상태", title_a, title_b, "증감"], rows), "",
             "### 변경 종류", "", _table(["종류", "건수"], [[k, kinds.get(k, 0)] for k in KIND_ORDER]), ""]
    sd = sorted({s for d in diffs for s in d.settings_diff})
    lines += ["### 달라진 설정", ""] + ([f"- {s}" for s in sd] or ["- 없음"]) + [""]
    if gold:
        grows = []
        for d, (ma, mb) in zip(diffs, gold):
            grows.append([d.a.name, _pct((ma or {}).get("recall")), _pct((mb or {}).get("recall")),
                          _pct((ma or {}).get("precision")), _pct((mb or {}).get("precision"))])
        lines += ["### 골드 지표", "", _table(["파일", f"재현율 {title_a}", f"재현율 {title_b}", f"정밀도 {title_a}", f"정밀도 {title_b}"], grows), ""]
    return "\n".join(lines)


def classifiers_markdown(result: dict) -> str:
    rows = []
    for r in result["reports"]:
        c = r.candidates or {}
        rows.append([r.label, "O" if r.trainable else "X", "O" if r.needs_embedding else "X", _pct(r.accuracy),
                     _pct(r.acc_std) if r.acc_std is not None else "-", _pct(r.macro_f1), _pct(c.get("recall")) if c else "-",
                     _pct(c.get("precision")) if c else "-", f"{r.fit_sec + r.predict_sec:.1f}", r.skipped or ""])
    return "\n".join([
        "## 1차 분류기 비교", "",
        f"골드 {result['n']}문장 (등급별 {result['gold_counts']}), 학습형은 층화 {result['k']}겹 교차 검증 × {result['repeats']}회, 임베딩 {result['embed_model'] or '-'}.", "",
        _table(["분류기", "학습", "임베딩", "등급 정확도", "±표준편차", "거시 F1", "A·B 재현율", "A·B 정밀도", "시간(초)", "비고"], rows), "",
        "표준편차보다 작은 정확도 차이는 겹 나누기에 따른 잡음으로 본다.", ""])


def ladder_markdown(result) -> str:
    steps = result.steps
    mode_ko = "누적(직전 칸과 비교)" if result.ladder.mode == "cumulative" else "단독(기준선과 비교)"
    rows = []
    prev = None
    for sr in steps:
        tot = sr.totals()
        review = tot.get("검토 목록", 0)
        base = steps[0] if result.ladder.mode == "single" else prev
        delta = "" if base is None else (f"{review - base.totals().get('검토 목록', 0):+d}" if review != base.totals().get('검토 목록', 0) else "0")
        row = [sr.title, sum(tot.values()), review, tot.get("보류", 0), tot.get("분류기 제외", 0), tot.get("전처리 제외", 0) + tot.get("페이지 제외", 0), delta, f"{sr.elapsed:.0f}"]
        if result.gold_used:
            g = sr.gold or {}
            row += [_pct(g.get("recall")), _pct(g.get("precision"))]
        rows.append(row)
        prev = sr
    heads = ["칸", "문장 단위", "검토 목록", "보류", "분류기 제외", "전처리·페이지 제외", "증감", "초"] + (["A·B 재현율", "A·B 정밀도"] if result.gold_used else [])
    kind_rows = []
    for base, sr, dl in result.diffs:
        c: Counter = Counter()
        for d in dl:
            c.update(d.counts())
        kind_rows.append([sr.title] + [c.get(k, 0) for k in KIND_ORDER])
    return "\n".join([
        f"## 사다리 실행: {result.ladder.name} ({mode_ko})", "",
        f"입력 {len(result.inputs)}개 파일, 칸 {len(result.ladder.steps)}개. 칸마다 모든 파일을 다시 실행했다.", "",
        _table(heads, rows), "", "### 칸별 변경 종류", "", _table(["칸"] + KIND_ORDER, kind_rows), ""])
