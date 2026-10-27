"""두 실행 스냅샷의 비교와 설정 차이의 설명."""
from __future__ import annotations

from ..models import LabeledLine

CHANGE_KINDS = {
    "entered": "목록 진입",
    "left": "목록 이탈",
    "grade": "등급 변경",
    "score": "점수 변경",
    "text": "문장 변경",
    "new": "새 문장",
    "gone": "사라진 문장",
}

_SETTING_NAMES = {
    "model": "LLM 모델", "prompt_variant": "프롬프트 판", "mode": "판정 모드", "embed_model": "임베딩 모델",
    "group_max_chars": "묶음 글자 수", "group_by": "묶음 기준", "target_grades": "추출 등급", "page_weight_enabled": "페이지 가중치 적용",
    "low_relevance_patterns": "관련성 낮음 키워드", "high_relevance_patterns": "관련성 높음 키워드", "low_relevance_weight": "관련성 낮음 가중치",
    "accept_score": "목록 점수 기준", "short_line_chars": "짧은 줄 기준(글자수)", "split_len": "분할 길이", "repeated_line_min_pages": "반복 문구 기준",
    "stoplist": "수동 제거 목록", "page_exclude_patterns": "페이지 제외 패턴", "cover_max_lines": "표지 기준",
    "title_fix": "제목 보정", "safety_net": "안전장치", "prompt_version": "프롬프트 버전", "classifier": "분류기",
    "version": "프로그램 버전", "gold": "골드(반영 문장)", "use_gold": "골드 반영",
}


def _fmt(v) -> str:
    if v is None:
        return "기본값"
    if isinstance(v, bool):
        return "켬" if v else "끔"
    if isinstance(v, (list, dict)):
        return f"{len(v)}개 항목"
    return str(v)


def settings_diff(prev: dict, cur: dict) -> list[str]:
    out = []
    for k in list(cur.keys()) + [k for k in prev.keys() if k not in cur]:
        a, b = prev.get(k), cur.get(k)
        if a == b:
            continue
        name = _SETTING_NAMES.get(k, k)
        if isinstance(a, (list, dict)) or isinstance(b, (list, dict)):
            out.append(f"{name} 변경 ({_fmt(a)} → {_fmt(b)})")
        else:
            out.append(f"{name}: {_fmt(a)} → {_fmt(b)}")
    return out


def diff_runs(prev: dict, cur: dict, score_step: float = 0.1) -> dict:
    """lines = {key: {"h": 해시, "label": 등급, "score": 점수, "in": 목록 여부}}"""
    P, C = prev.get("lines", {}), cur.get("lines", {})
    items: list[dict] = []
    for key, c in C.items():
        p = P.get(key)
        if p is None:
            items.append({"key": key, "kind": "new", "old": "", "new": c["label"], "in": c["in"]})
            continue
        if p.get("h") != c.get("h"):
            items.append({"key": key, "kind": "text", "old": p["label"], "new": c["label"], "in": c["in"]})
            continue
        if c["in"] and not p["in"]:
            items.append({"key": key, "kind": "entered", "old": p["label"], "new": c["label"], "in": True})
        elif p["in"] and not c["in"]:
            items.append({"key": key, "kind": "left", "old": p["label"], "new": c["label"], "in": False})
        elif p["label"] != c["label"]:
            items.append({"key": key, "kind": "grade", "old": p["label"], "new": c["label"], "in": c["in"]})
        elif abs(float(p.get("score", 0)) - float(c.get("score", 0))) >= score_step:
            items.append({"key": key, "kind": "score", "old": f"{p.get('score', 0):.2f}", "new": f"{c.get('score', 0):.2f}", "in": c["in"]})
    for key, p in P.items():
        if key not in C:
            items.append({"key": key, "kind": "gone", "old": p["label"], "new": "", "in": False})
    counts = {k: sum(1 for it in items if it["kind"] == k) for k in CHANGE_KINDS}
    counts["total"] = len(items)
    return {"items": items, "counts": counts}


def change_rows(diff: dict, labeled: list[LabeledLine]) -> list[dict]:
    """Excel '변경 사항' 시트용. 현재 실행의 문장으로 발췌를 채운다 (사라진 문장은 발췌 없음)."""
    by_key = {f"{ll.page_no}:{ll.line_idx}": ll for ll in labeled}
    rows = []
    for it in diff.get("items", []):
        ll = by_key.get(it["key"])
        page, _, idx = it["key"].partition(":")
        kind = CHANGE_KINDS.get(it["kind"], it["kind"])
        old, new = it["old"], it["new"]
        if it["kind"] == "entered":
            desc = f"이전 실행에서는 목록에 없었음 (이전 {old or '-'})"
        elif it["kind"] == "left":
            desc = ("보류: " + ll.hold_reason) if ll and ll.hold_reason else f"이전 {old} → 현재 {new or '-'}"
        elif it["kind"] == "grade":
            desc = f"{old} → {new}"
        elif it["kind"] == "score":
            desc = f"점수 {old} → {new}"
        elif it["kind"] == "text":
            desc = "전처리 결과가 달라져 문장이 바뀜"
        elif it["kind"] == "new":
            desc = "이전 실행에 없던 문장"
        else:
            desc = "이전 실행에 있던 문장이 없어짐"
        rows.append({"kind": kind, "page": int(page) if page.isdigit() else page, "line": int(idx) if idx.isdigit() else idx,
                     "text": ll.text if ll else "", "old": old, "new": new, "in_list": "목록" if it.get("in") else "",
                     "desc": desc, "source": ({"clf": "분류기", "llm": "LLM", "verified": "분류기+LLM"}.get(ll.source, ll.source) if ll else "")})
    order = {"entered": 0, "left": 1, "grade": 2, "score": 3, "text": 4, "new": 5, "gone": 6}
    kinds_rev = {v: k for k, v in CHANGE_KINDS.items()}
    rows.sort(key=lambda r: (order.get(kinds_rev.get(r["kind"], ""), 9), r["page"] if isinstance(r["page"], int) else 0, r["line"] if isinstance(r["line"], int) else 0))
    return rows
