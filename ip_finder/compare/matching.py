"""두 실행(또는 골드와 실행)의 문장을 서로 맞춘다.

레이아웃 분석이나 긴 줄 분할을 켜면 문장 단위 자체가 합쳐지거나 나뉘어 글자 그대로의 일치로는 전후를 맞출 수 없다. 세 단계로 맞춘다.
  1. 동일: 공백을 모두 지우고 소문자로 만든 글이 같다
  2. 포함: 같은 쪽에서 한쪽 글이 다른 쪽 글 안에 들어 있다 (여러 줄 → 한 문단 = 합쳐짐, 한 줄 → 여러 문장 = 나뉨). 짧은 글(6자 미만)은 안 쓴다
  3. 유사: 같은 쪽에서 글자 일치 비율(difflib)이 0.6 이상인 가장 비슷한 짝
이 기준은 비교·골드 채점 양쪽에서 같다."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

_WS = re.compile(r"\s+")
MIN_CONTAIN = 6
MIN_RATIO = 0.6


def norm_key(text) -> str:
    """비교용 열쇠: 공백 전부 제거, 소문자."""
    return _WS.sub("", str(text or "")).lower()


@dataclass
class Matches:
    pairs: list[tuple[int, int, str]] = field(default_factory=list)   # (a 인덱스, b 인덱스, 동일|포함|유사)
    unmatched_a: list[int] = field(default_factory=list)
    unmatched_b: list[int] = field(default_factory=list)

    def kind_of(self) -> dict[tuple[int, int], str]:
        return {(i, j): k for i, j, k in self.pairs}


def match_texts(a: list[str], b: list[str], pages_a: list | None = None, pages_b: list | None = None) -> Matches:
    """a 의 각 글과 b 의 각 글을 맞춘다. pages 를 주면 2·3단계는 같은 쪽 안에서만 찾는다 (None 쪽은 모든 쪽과 비교)."""
    ka = [norm_key(t) for t in a]
    kb = [norm_key(t) for t in b]
    pa = pages_a if pages_a is not None else [None] * len(a)
    pb = pages_b if pages_b is not None else [None] * len(b)
    m = Matches()
    used_a: set[int] = set()
    used_b: set[int] = set()

    # 1. 동일 — 같은 글이 여러 번 나오면 순서대로 짝짓는다
    pool: dict[str, list[int]] = {}
    for j, k in enumerate(kb):
        if k:
            pool.setdefault(k, []).append(j)
    for i, k in enumerate(ka):
        lst = pool.get(k)
        if k and lst:
            j = lst.pop(0)
            m.pairs.append((i, j, "동일"))
            used_a.add(i)
            used_b.add(j)

    def same_page(i: int, j: int) -> bool:
        return pa[i] is None or pb[j] is None or pa[i] == pb[j]

    # 2. 포함 — a 가 b 안에(합쳐짐): b 는 여러 a 와 짝지을 수 있다. b 가 a 안에(나뉨): a 는 여러 b 와 짝지을 수 있다
    by_page_b: dict = {}
    for j in range(len(b)):
        by_page_b.setdefault(pb[j], []).append(j)
    cand_b_for = lambda i: (by_page_b.get(pa[i], []) if pa[i] is not None else range(len(b)))
    for i in range(len(a)):
        if i in used_a or len(ka[i]) < MIN_CONTAIN:
            continue
        best = None
        for j in cand_b_for(i):
            if len(kb[j]) > len(ka[i]) and ka[i] in kb[j] and same_page(i, j):
                if best is None or len(kb[j]) < len(kb[best]):      # 가장 짧게 감싸는 쪽
                    best = j
        if best is not None:
            m.pairs.append((i, best, "포함"))
            used_a.add(i)
            used_b.add(best)
    by_page_a: dict = {}
    for i in range(len(a)):
        by_page_a.setdefault(pa[i], []).append(i)
    cand_a_for = lambda j: (by_page_a.get(pb[j], []) if pb[j] is not None else range(len(a)))
    for j in range(len(b)):
        if j in used_b or len(kb[j]) < MIN_CONTAIN:
            continue
        best = None
        for i in cand_a_for(j):
            if len(ka[i]) > len(kb[j]) and kb[j] in ka[i] and same_page(i, j):
                if best is None or len(ka[i]) < len(ka[best]):
                    best = i
        if best is not None:
            m.pairs.append((best, j, "포함"))
            used_b.add(j)
            used_a.add(best)

    # 3. 유사 — 남은 것끼리 같은 쪽에서 가장 비슷한 짝 (둘 다 소비)
    rest_a = [i for i in range(len(a)) if i not in used_a and ka[i]]
    rest_b = [j for j in range(len(b)) if j not in used_b and kb[j]]
    scored: list[tuple[float, int, int]] = []
    for i in rest_a:
        for j in rest_b:
            if not same_page(i, j):
                continue
            sm = SequenceMatcher(None, ka[i], kb[j])
            if sm.real_quick_ratio() < MIN_RATIO or sm.quick_ratio() < MIN_RATIO:
                continue
            r = sm.ratio()
            if r >= MIN_RATIO:
                scored.append((r, i, j))
    for _, i, j in sorted(scored, reverse=True):
        if i in used_a or j in used_b:
            continue
        m.pairs.append((i, j, "유사"))
        used_a.add(i)
        used_b.add(j)

    m.unmatched_a = [i for i in range(len(a)) if i not in used_a]
    m.unmatched_b = [j for j in range(len(b)) if j not in used_b]
    return m
