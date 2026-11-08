"""실행 결과를 비교 가능한 형태(RunRecord)로 만들고 두 결과를 비교한다.

RunRecord 는 실행 직후의 Result 에서도, 저장된 결과 Excel 에서도 만들 수 있다. 그래서 회사 PC 에 이미 있는 결과 파일 두 개를
그대로 비교할 수 있다 (ip-finder compare-runs A.xlsx B.xlsx). 문장 단위의 '상태'는 검토 목록 / 보류 / 분류기 제외 / 후처리 제외 /
전처리 제외 / 페이지 제외 여섯 가지다."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import load_workbook

from ..history.diff import settings_diff
from ..post import STATUS_CLF_OUT, STATUS_HOLD, STATUS_PAGE_OUT, STATUS_POST_OUT, STATUS_PREP_OUT, STATUS_REVIEW, STATUSES, status_of
from .matching import Matches, match_texts, norm_key

LINE_SHEETS = {"검토 목록": STATUS_REVIEW, "보류": STATUS_HOLD, "분류기 제외 (참고)": STATUS_CLF_OUT, "후처리 제외": STATUS_POST_OUT,
               "1차 제외 (참고)": STATUS_CLF_OUT, "2차 제외": STATUS_POST_OUT}      # 뒤 둘은 0.x 결과 파일
PREP_SHEET = STATUS_PREP_OUT
INFO_SHEET = "실행 정보"
SETTING_PREFIX = "설정 "
RESULT_SUFFIX = "_검토후보.xlsx"


@dataclass
class Unit:
    page: int
    line: int
    text: str
    status: str
    grade: str = ""
    score: float | None = None
    weight: float | None = None
    conf: float | None = None
    source: str = ""
    notes: str = ""
    reason: str = ""          # 보류 사유 / 전처리 규칙 / 쪽 제외 사유

    @property
    def key(self) -> str:
        return norm_key(self.text)

    @property
    def in_review(self) -> bool:
        return self.status == STATUS_REVIEW


@dataclass
class RunRecord:
    name: str                 # 보고서 파일 이름
    path: str                 # 결과 Excel 경로 (메모리에서 만들었으면 "")
    units: list[Unit]
    settings: dict = field(default_factory=dict)
    info: dict = field(default_factory=dict)
    pages: int = 0
    elapsed: float = 0.0

    def by_status(self) -> Counter:
        c = Counter(u.status for u in self.units)
        for s in STATUSES:
            c.setdefault(s, 0)
        return c

    def review(self) -> list[Unit]:
        return [u for u in self.units if u.in_review]

    def grade_counts(self) -> Counter:
        return Counter(u.grade for u in self.review())

    @property
    def label(self) -> str:
        return Path(self.path).name if self.path else self.name


def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def record_from_result(res, cfg=None, path: str | Path = "") -> RunRecord:
    """파이프라인 Result → RunRecord. 판정 문장 + 전처리·페이지 규칙에 걸린 줄."""
    units: list[Unit] = []
    for ll in res.labeled:
        units.append(Unit(ll.page_no, ll.line_idx, ll.text, status_of(ll), ll.label, ll.score, ll.page_weight, ll.clf_conf,
                          ll.source, ", ".join(ll.notes), ll.hold_reason))
    for p in res.doc.pages:
        for ln in p.lines:
            if not ln.text.strip():
                continue
            if ln.removed_by:                       # 줄 규칙이 먼저 (규칙에 걸려 쪽이 비어 제외된 경우 규칙 이름이 더 정확하다)
                units.append(Unit(p.no, 0, ln.text, STATUS_PREP_OUT, reason=ln.removed_by))
            elif p.excluded_reason is not None:
                units.append(Unit(p.no, 0, ln.text, STATUS_PAGE_OUT, reason=p.excluded_reason))
    settings = dict(cfg.fingerprint()) if cfg is not None else {}
    settings["classifier_desc"] = res.info.classifier
    info = {"입력 파일": res.info.source, "실행 ID": res.info.run_id, "1차 분류기": res.info.classifier, "임베딩 모델": res.info.embed_model}
    return RunRecord(Path(res.info.source).name, str(path), units, settings, info, res.info.pages_total, res.info.elapsed_sec)


def _sheet_rows(ws) -> list[dict]:
    it = ws.iter_rows(values_only=True)
    try:
        header = [str(h) if h is not None else "" for h in next(it)]
    except StopIteration:
        return []
    out = []
    for r in it:
        if r is None:
            continue
        d = {h: r[i] for i, h in enumerate(header) if h}
        out.append(d)
    return out


def load_record(xlsx: Path) -> RunRecord:
    """저장된 결과 Excel → RunRecord. 열은 이름으로 찾는다."""
    xlsx = Path(xlsx)
    wb = load_workbook(str(xlsx), read_only=True, data_only=True)
    try:
        units: list[Unit] = []
        for sheet, status in LINE_SHEETS.items():
            if sheet not in wb.sheetnames:
                continue
            for r in _sheet_rows(wb[sheet]):
                text = r.get("발췌")
                if text in (None, "") or r.get("페이지") in (None, ""):
                    continue
                units.append(Unit(int(r.get("페이지") or 0), int(r.get("줄") or 0), str(text), status, str(r.get("등급") or ""),
                                  _num(r.get("점수")), _num(r.get("가중치")), _num(r.get("확신")), str(r.get("판정") or ""),
                                  str(r.get("비고") or ""), str(r.get("보류 사유") or "")))
        if PREP_SHEET in wb.sheetnames:
            for r in _sheet_rows(wb[PREP_SHEET]):
                text = r.get("발췌")
                if text in (None, "") or r.get("페이지") in (None, ""):
                    continue
                units.append(Unit(int(r.get("페이지") or 0), 0, str(text), str(r.get("상태") or STATUS_PREP_OUT), reason=str(r.get("사유") or "")))
        info: dict = {}
        settings: dict = {}
        if INFO_SHEET in wb.sheetnames:
            for r in wb[INFO_SHEET].iter_rows(min_row=2, values_only=True):
                if not r or r[0] in (None, ""):
                    continue
                k = str(r[0])
                if k.startswith(SETTING_PREFIX):
                    settings[k[len(SETTING_PREFIX):]] = r[1]
                else:
                    info[k] = r[1]
        name = Path(str(info.get("입력 파일") or xlsx.stem.replace("_검토후보", ""))).name
        pages = int(_num(info.get("페이지 수")) or 0)
        elapsed = _num(info.get("소요 시간(초)")) or 0.0
        if "1차 분류기" in info:
            settings.setdefault("classifier_desc", str(info["1차 분류기"]))
        return RunRecord(name, str(xlsx), units, settings, info, pages, elapsed)
    finally:
        wb.close()


def find_result_files(path: Path) -> list[Path]:
    """결과 파일 하나, 또는 폴더 안의 *_검토후보.xlsx (하위 폴더 포함)."""
    path = Path(path)
    if path.is_file():
        return [path]
    return sorted(f for f in path.rglob(f"*{RESULT_SUFFIX}") if not f.name.startswith("~$"))


def load_records(path: Path) -> list[RunRecord]:
    return [load_record(f) for f in find_result_files(path)]


# ------------------------------------------------------------------ 두 실행 비교
KIND_ENTER, KIND_LEAVE, KIND_GRADE, KIND_SCORE, KIND_STATUS = "검토 목록 진입", "검토 목록 이탈", "등급 변경", "점수 변경", "상태 변경"
KIND_MERGED, KIND_SPLIT, KIND_SIMILAR, KIND_NEW, KIND_GONE = "문장 합쳐짐", "문장 나뉨", "문장 변경", "새 문장", "사라진 문장"
KIND_ORDER = [KIND_ENTER, KIND_LEAVE, KIND_GRADE, KIND_SCORE, KIND_STATUS, KIND_MERGED, KIND_SPLIT, KIND_SIMILAR, KIND_NEW, KIND_GONE]


@dataclass
class RunDiff:
    a: RunRecord
    b: RunRecord
    matches: Matches
    changes: list[dict]
    settings_diff: list[str]

    def counts(self) -> Counter:
        c = Counter(ch["kind"] for ch in self.changes)
        for k in KIND_ORDER:
            c.setdefault(k, 0)
        return c

    def summary_rows(self) -> list[tuple[str, int, int, int]]:
        """(상태, A 수, B 수, 증감)"""
        sa, sb = self.a.by_status(), self.b.by_status()
        rows = [(s, sa[s], sb[s], sb[s] - sa[s]) for s in STATUSES]
        rows.append(("전체 문장 단위", len(self.a.units), len(self.b.units), len(self.b.units) - len(self.a.units)))
        return rows


def _unit_desc(u: Unit) -> str:
    bits = [u.status]
    if u.grade:
        bits.append(u.grade)
    if u.score is not None:
        bits.append(f"{u.score:.2f}")
    if u.reason:
        bits.append(u.reason)
    return " / ".join(bits)


def compare_records(a: RunRecord, b: RunRecord, score_step: float = 0.1) -> RunDiff:
    """A(이전·기준) → B(이후·비교) 로 무엇이 달라졌는지 문장 단위로."""
    m = match_texts([u.text for u in a.units], [u.text for u in b.units], [u.page for u in a.units], [u.page for u in b.units])
    changes: list[dict] = []

    def row(kind: str, ua: Unit | None, ub: Unit | None, desc: str) -> dict:
        return {"kind": kind, "page": (ub or ua).page, "a_text": ua.text if ua else "", "a_status": ua.status if ua else "",
                "a_grade": ua.grade if ua else "", "a_score": ua.score if ua else None, "b_text": ub.text if ub else "",
                "b_status": ub.status if ub else "", "b_grade": ub.grade if ub else "", "b_score": ub.score if ub else None, "desc": desc}

    for i, j, kind in m.pairs:
        ua, ub = a.units[i], b.units[j]
        if kind == "동일":
            if ub.in_review and not ua.in_review:
                changes.append(row(KIND_ENTER, ua, ub, f"이전 {_unit_desc(ua)} → 현재 검토 목록 {ub.grade}"))
            elif ua.in_review and not ub.in_review:
                changes.append(row(KIND_LEAVE, ua, ub, f"이전 검토 목록 {ua.grade} → 현재 {_unit_desc(ub)}"))
            elif ua.status != ub.status:
                changes.append(row(KIND_STATUS, ua, ub, f"{_unit_desc(ua)} → {_unit_desc(ub)}"))
            elif ua.grade != ub.grade and (ua.grade or ub.grade):
                changes.append(row(KIND_GRADE, ua, ub, f"{ua.grade or '-'} → {ub.grade or '-'}"))
            elif ua.score is not None and ub.score is not None and abs(ua.score - ub.score) >= score_step:
                changes.append(row(KIND_SCORE, ua, ub, f"점수 {ua.score:.2f} → {ub.score:.2f}"))
        elif kind == "포함":
            merged = len(norm_key(ub.text)) > len(norm_key(ua.text))
            k = KIND_MERGED if merged else KIND_SPLIT
            changes.append(row(k, ua, ub, ("이전 줄이 현재 문장 안에 포함됨" if merged else "이전 문장의 일부가 현재 줄로 나뉨") + f": {_unit_desc(ua)} → {_unit_desc(ub)}"))
        else:
            changes.append(row(KIND_SIMILAR, ua, ub, f"비슷한 문장으로 바뀜: {_unit_desc(ua)} → {_unit_desc(ub)}"))
    for j in m.unmatched_b:
        ub = b.units[j]
        changes.append(row(KIND_NEW, None, ub, f"이전 실행에 없던 문장 → {_unit_desc(ub)}"))
    for i in m.unmatched_a:
        ua = a.units[i]
        changes.append(row(KIND_GONE, ua, None, f"이전 {_unit_desc(ua)} 였던 문장이 현재 실행에 없음"))
    order = {k: n for n, k in enumerate(KIND_ORDER)}
    changes.sort(key=lambda r: (order.get(r["kind"], 99), r["page"]))
    return RunDiff(a, b, m, changes, settings_diff(a.settings, b.settings))


def pair_records(a_list: list[RunRecord], b_list: list[RunRecord]) -> list[tuple[RunRecord, RunRecord]]:
    """두 폴더의 결과를 보고서 이름으로 짝짓는다. 이름이 완전히 같은 것 먼저, 남는 것은 확장자를 뺀 이름으로. 하나씩이면 이름이 달라도 짝."""
    if len(a_list) == 1 and len(b_list) == 1:
        return [(a_list[0], b_list[0])]
    pairs: list[tuple[RunRecord, RunRecord]] = []
    rest_b = list(b_list)
    rest_a = []
    for ra in a_list:
        rb = next((r for r in rest_b if r.name.lower() == ra.name.lower()), None)
        if rb is None:
            rest_a.append(ra)
        else:
            pairs.append((ra, rb))
            rest_b.remove(rb)
    stem = lambda r: Path(r.name).stem.lower()
    for ra in rest_a:
        rb = next((r for r in rest_b if stem(r) == stem(ra)), None)
        if rb is not None:
            pairs.append((ra, rb))
            rest_b.remove(rb)
    return pairs


# ------------------------------------------------------------------ 골드 지표
def gold_rows_for(rec: RunRecord, gold_rows: list[dict]) -> list[dict]:
    """이 보고서의 골드 행. '파일' 열이 보고서 이름과 같은 행, 없으면 전체(이름이 바뀐 경우)."""
    stem = Path(rec.name).stem.lower()
    mine = [r for r in gold_rows if Path(str(r.get("파일") or "")).stem.lower() == stem]
    return mine or gold_rows


def gold_metrics(rec: RunRecord, gold_rows: list[dict], targets: tuple[str, ...] = ("A", "B")) -> dict:
    """골드 문장을 실행 결과의 문장과 맞춰(matching) 채점한다.
    재현율 = 정답이 대상 등급(A·B)인 골드 문장 중 검토 목록에 있는 비율. 정밀도 = 골드와 맞춰진 검토 목록 문장 중 정답이 대상 등급인 비율.
    골드와 맞춰지지 않은 검토 목록 문장은 '미채점'으로 따로 센다. 등급 정확도 = 맞춰진 골드 문장 중 등급까지 같은 비율(제외된 줄은 X 로 본다)."""
    rows = gold_rows_for(rec, gold_rows)
    if not rows:
        return {}
    gtexts = [str(r.get("문장") or "") for r in rows]
    gpages = [r.get("페이지") if isinstance(r.get("페이지"), int) else None for r in rows]
    m = match_texts(gtexts, [u.text for u in rec.units], gpages, [u.page for u in rec.units])
    matched: dict[int, list[Unit]] = {}
    for i, j, _ in m.pairs:
        matched.setdefault(i, []).append(rec.units[j])
    hit = pos = cand_hit = cand_tot = exact = 0
    review_matched: set[int] = set()
    for i, r in enumerate(rows):
        g = str(r.get("정답") or "").upper()
        us = matched.get(i, [])
        if not us:
            continue
        in_review = any(u.in_review for u in us)
        pred = next((u.grade for u in us if u.in_review), None) or next((u.grade for u in us if u.grade), "X")
        if g in targets:
            pos += 1
            if in_review:
                hit += 1
        if in_review:
            cand_tot += 1
            if g in targets:
                cand_hit += 1
        if (pred or "X") == g or (g == "X" and pred in ("X", "X?", "")):
            exact += 1
        for u in us:
            if u.in_review:
                review_matched.add(id(u))
    n_review = len(rec.review())
    n_matched = len(matched)
    return {"gold_rows": len(rows), "matched": n_matched, "positives": pos, "hits": hit,
            "recall": hit / pos if pos else None, "precision": cand_hit / cand_tot if cand_tot else None,
            "review": n_review, "review_unscored": n_review - len(review_matched),
            "grade_accuracy": exact / n_matched if n_matched else None}


def aggregate_gold(metrics: list[dict]) -> dict:
    """여러 보고서의 골드 지표를 합쳐 하나로 (비율은 합계에서 다시 계산)."""
    ms = [m for m in metrics if m]
    if not ms:
        return {}
    pos = sum(m["positives"] for m in ms)
    hit = sum(m["hits"] for m in ms)
    rv = sum(m["review"] for m in ms)
    un = sum(m["review_unscored"] for m in ms)
    cand_tot = rv - un
    cand_hit = sum(round((m["precision"] or 0) * (m["review"] - m["review_unscored"])) for m in ms)
    matched = sum(m["matched"] for m in ms)
    exact = sum(round((m["grade_accuracy"] or 0) * m["matched"]) for m in ms)
    return {"gold_rows": sum(m["gold_rows"] for m in ms), "matched": matched, "positives": pos, "hits": hit,
            "recall": hit / pos if pos else None, "precision": cand_hit / cand_tot if cand_tot else None,
            "review": rv, "review_unscored": un, "grade_accuracy": exact / matched if matched else None}
