"""PDF 리더 (PyMuPDF). 문자 좌표에서 줄·다단 읽기 순서·문단·표를 복원한다.

patent_finder 의 레이아웃 분석(XY-cut)을 PyMuPDF 위에 옮긴 것이다. 흐름:
- 문자 → 줄(세로로 절반 이상 겹치는 문자) → 조각(큰 가로 간격에서 끊음: 다단·표 열 분리) → 재귀 XY-cut 으로 단과 블록 순서
  → 같은 영역의 줄을 문단으로 묶음(줄 간격·글씨 크기·목록 표식·오른쪽 여백·들여쓰기로 판단). 줄 끝 하이픈은 이어 붙인다.
- 페이지 위·아래 8% 띠의 글(문서명, 쪽 번호)은 단 나눔 분석에서 떼어 두고 위 띠는 맨 앞, 아래 띠는 맨 뒤에 읽는다. 지우지 않는다
  (반복 문구는 전처리 규칙이 거른다). 머리말·꼬리말을 지우던 정책은 v0.6.2 에서 폐기했다(제목이 지워지던 문제).
- 표는 선 개체가 있을 때 PyMuPDF find_tables 로 찾아 행마다 '열 제목: 셀 | …' 한 줄(source="table")로 만든다.
- 제목 = 페이지 위쪽 35% 안에서 ① 본문 글씨의 1.15배 이상인 줄 중 가장 큰 것("font") → ② 굵은 글씨 줄 중 가장 위("bold")
  → ③ 본문의 0.8배 이상 크기인 첫 줄("first-line", 8pt 문서명 같은 작은 글은 건너뜀).
- 회전 페이지(/Rotate)는 화면 기준 좌표로 돌려 읽고, 화면에서 세로로 선 문자는 읽지 않고 센다.
  글꼴 매핑이 깨진 페이지(치환 문자 20% 초과)와 글자 없는 페이지는 본문 없이 둔다(전처리에서 '이미지 페이지').
"""
from __future__ import annotations

import os
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

os.environ.setdefault("PYMUPDF_SUGGEST_LAYOUT_ANALYZER", "0")   # find_tables 가 pymupdf_layout 설치를 권하는 문구를 찍지 않게
import pymupdf

from ..models import Document, Line, Page
from ._text import clean, list_marker, table_lines

EDGE_ZONE = 0.08          # 페이지 위·아래 8% 띠: 본문 배치 분석에서 떼어 두고 앞·뒤에 읽는다 (지우지 않음)
TITLE_ZONE = 0.35         # 제목은 페이지 높이의 이 비율 안에 있어야 한다
HEADING_RATIO = 1.15      # 본문 글씨의 이 배수 이상이면 제목·소제목
TITLE_MIN_RATIO = 0.8     # 첫 줄을 제목으로 삼을 때(③) 본문 글씨의 이 배수 미만인 작은 글(문서명·쪽 번호)은 건너뛴다
_DATE_START = re.compile(r"^\d{4}\s*[./년]")
_NUMBER_DOT_END = re.compile(r"\d\.$")
MAX_VECTORS = 5000        # 선 개체가 이보다 많으면 표 인식을 건너뛴다 (도면 페이지)
MAX_LEVEL = 3
_FLAGS = pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_MEDIABOX_CLIP   # 합자는 풀고, 이미지 블록은 받지 않는다


@dataclass
class Char:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    size: float
    bold: bool = False


@dataclass
class Fragment:
    """같은 줄에서 가로로 이어진 문자 묶음, 또는 표 하나."""
    x0: float
    x1: float
    top: float
    bottom: float
    chars: list[Char] = field(default_factory=list)
    line_id: int = -1
    table: Any = None


@dataclass
class TextLine:
    text: str
    xs: list[float]
    top: float
    bottom: float
    size: float
    tabular: bool = False       # 큰 가로 간격으로 나뉜 칸이 둘 이상인 줄(공백으로 맞춘 표의 한 행). 앞뒤 줄과 문단으로 묶지 않는다
    bold: bool = False          # 글자 과반이 굵은 글씨

    @property
    def x0(self) -> float:
        return self.xs[0]

    @property
    def x1(self) -> float:
        return self.xs[-1]


@dataclass
class Block:
    """페이지 안의 읽기 단위. kind: heading | paragraph | list_item | table_row."""
    kind: str
    text: str
    top: float
    size: float
    level: int = 0
    rows: list[list[str]] | None = None     # table_row 묶음: 표 전체의 셀 텍스트
    bold: bool = False
    x0: float = 0.0
    x1: float = 0.0
    is_title: bool = False
    title_source: str = ""


# ------------------------------------------------------------------ 문자 → 줄 → 조각
def cluster_lines(chars: list[Char]) -> list[list[Char]]:
    """세로로 절반 이상 겹치는 문자를 같은 줄로 묶는다."""
    lines: list[dict[str, Any]] = []
    for char in sorted(chars, key=lambda c: (c.top, c.x0)):
        height = char.bottom - char.top
        if height <= 0:
            continue
        target = None
        for line in reversed(lines[-8:]):
            overlap = min(line["bottom"], char.bottom) - max(line["top"], char.top)
            base = min(height, line["bottom"] - line["top"])
            if base > 0 and overlap / base >= 0.5:
                target = line
                break
        if target is None:
            lines.append({"top": char.top, "bottom": char.bottom, "chars": [char]})
        else:
            target["chars"].append(char)
            if height > target["bottom"] - target["top"]:
                target["top"], target["bottom"] = char.top, char.bottom
    return [line["chars"] for line in lines]


def split_fragments(line_chars: list[Char], line_id: int) -> list[Fragment]:
    """한 줄의 문자를 큰 가로 간격에서 끊어 조각으로 만든다 (다단·표 열 분리용). 공백 문자는 간격으로만 보고 버린다."""
    ordered = sorted((c for c in line_chars if not c.text.isspace()), key=lambda c: c.x0)
    if not ordered:
        return []
    groups: list[list[Char]] = [[ordered[0]]]
    for previous, current in zip(ordered, ordered[1:]):
        if current.x0 - previous.x1 > 1.4 * max(previous.size, current.size):
            groups.append([current])
        else:
            groups[-1].append(current)
    fragments = []
    for group in groups:
        visible = [c for c in group if not c.text.isspace()]
        if not visible:
            continue
        fragments.append(Fragment(x0=min(c.x0 for c in visible), x1=max(c.x1 for c in visible),
                                  top=min(c.top for c in visible), bottom=max(c.bottom for c in visible),
                                  chars=group, line_id=line_id))
    return fragments


def build_line(chars: list[Char]) -> TextLine | None:
    """문자 목록에서 줄 텍스트와 문자 경계 x 좌표(xs)를 만든다. 단어 사이 공백은 간격으로 복원한다."""
    ordered = sorted(chars, key=lambda c: c.x0)
    text: list[str] = []
    xs: list[float] = []
    previous: Char | None = None
    last_x1 = 0.0
    for char in ordered:
        if char.text.isspace() or not char.text:
            if text and text[-1] != " ":
                text.append(" ")
                xs.append(char.x0)
            previous = None
            continue
        if previous is not None and char.x0 - previous.x1 > 0.18 * max(previous.size, char.size):
            if text and text[-1] != " ":
                text.append(" ")
                xs.append(previous.x1)
        count = len(char.text)
        step = (char.x1 - char.x0) / count
        for index, ch in enumerate(char.text):
            text.append(ch)
            xs.append(char.x0 + step * index)
        last_x1 = char.x1
        previous = char
    while text and text[-1] == " ":
        text.pop()
        xs.pop()
    if not text:
        return None
    xs.append(last_x1)
    visible = [c for c in ordered if not c.text.isspace()]
    return TextLine(text="".join(text), xs=xs, top=min(c.top for c in visible), bottom=max(c.bottom for c in visible),
                    size=statistics.median(c.size for c in visible), bold=sum(1 for c in visible if c.bold) * 2 > len(visible))


def _band_lines(line_chars: list[Char]) -> list[TextLine]:
    """위·아래 띠의 한 줄을 큰 가로 간격에서 나눠 각각 한 줄로 (왼쪽의 문서명과 오른쪽의 쪽 번호가 한 줄에 있어도 따로)."""
    out = []
    for frag in split_fragments(line_chars, -1):
        built = build_line(frag.chars)
        if built is not None:
            out.append(built)
    return out


# ------------------------------------------------------------------ XY-cut 읽기 순서
def lower_quartile(values: list[float]) -> float:
    """일반적인 줄 간격의 추정값. 문단 간격이 섞여 있어도 흔들리지 않게 하위 사분위를 쓴다."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[(len(ordered) - 1) // 4]


def _gaps(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[list[float]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(a[1], b[0]) for a, b in zip(merged, merged[1:])]


def xy_cut(fragments: list[Fragment], x_gap: float, y_gap: float, min_col_width: float,
           stats: dict[str, int], column: str = "c", standalone: set[int] | None = None) -> list[tuple[str, list[Fragment]]]:
    """재귀 XY-cut. 세로 여백(단 구분)을 먼저 찾고, 없으면 가장 큰 가로 여백에서 위아래로 나눈다.

    반환: (단 키, 조각 목록). 좌우로 나뉠 때만 단 키가 달라지고, 위아래로 나뉜 잎들은 같은 단 키를 갖는다.
    standalone: 제목 크기 글·표처럼 단에 속하지 않는 조각의 id. 두 단의 위·아래에 있으면 단보다 앞·뒤에 따로 읽는다.
    """
    if len(fragments) <= 1:
        return [(column, fragments)] if fragments else []
    standalone = standalone or set()
    x_candidates = sorted(_gaps([(f.x0, f.x1) for f in fragments]), key=lambda g: g[0] - g[1])
    for start, end in x_candidates:
        if end - start < x_gap:
            break
        left = [f for f in fragments if f.x1 <= start + 0.01]
        right = [f for f in fragments if f.x1 > start + 0.01]
        widths = [max(f.x1 for f in side) - min(f.x0 for f in side) for side in (left, right)]
        if min(widths) >= min_col_width:
            stats["x_cuts"] = stats.get("x_cuts", 0) + 1
            # 두 단이 함께 있는 세로 구간(band) 위·아래에만 있는 조각(단 위의 제목, 단 아래의 소제목·캡션)은
            # 단에 넣지 않고 앞뒤에 따로 둔다. 그래야 왼쪽 단 끝에 붙은 전체 폭 소제목이 오른쪽 단보다 먼저 읽히지 않는다.
            band_top = max(min(f.top for f in left), min(f.top for f in right))
            band_bottom = min(max(f.bottom for f in left), max(f.bottom for f in right))
            head = [f for f in fragments if id(f) in standalone and f.bottom + y_gap <= band_top]
            tail = [f for f in fragments if id(f) in standalone and f.top >= band_bottom + y_gap]
            if head or tail:
                band = [f for f in fragments if f not in head and f not in tail]
                return (xy_cut(head, x_gap, y_gap, min_col_width, stats, column, standalone)
                        + xy_cut([f for f in band if f in left], x_gap, y_gap, min_col_width, stats, column + "L", standalone)
                        + xy_cut([f for f in band if f in right], x_gap, y_gap, min_col_width, stats, column + "R", standalone)
                        + xy_cut(tail, x_gap, y_gap, min_col_width, stats, column, standalone))
            return (xy_cut(left, x_gap, y_gap, min_col_width, stats, column + "L", standalone)
                    + xy_cut(right, x_gap, y_gap, min_col_width, stats, column + "R", standalone))
    y_candidates = sorted(_gaps([(f.top, f.bottom) for f in fragments]), key=lambda g: g[0] - g[1])
    if y_candidates and y_candidates[0][1] - y_candidates[0][0] >= y_gap:
        start = y_candidates[0][0]
        upper = [f for f in fragments if f.bottom <= start + 0.01]
        lower = [f for f in fragments if f.bottom > start + 0.01]
        return (xy_cut(upper, x_gap, y_gap, min_col_width, stats, column, standalone)
                + xy_cut(lower, x_gap, y_gap, min_col_width, stats, column, standalone))
    return [(column, fragments)]


# ------------------------------------------------------------------ 줄 → 문단
def _first_word_width(line: TextLine) -> float:
    space = line.text.find(" ")
    end = space if space > 0 else len(line.text)
    return line.xs[end] - line.xs[0]


def group_paragraphs(lines: list[TextLine], right_edge: float) -> list[list[TextLine]]:
    """같은 영역 안의 줄을 문단으로 묶는다."""
    if not lines:
        return []
    gaps = [b.top - a.bottom for a, b in zip(lines, lines[1:])]
    median_gap = lower_quartile([g for g in gaps if g > 0])
    paragraphs: list[list[TextLine]] = [[lines[0]]]
    for previous, current in zip(lines, lines[1:]):
        size = max(previous.size, current.size)
        first = paragraphs[-1][0]
        starts_marker = bool(list_marker(current.text)[0])
        size_change = abs(previous.size - current.size) > 0.15 * size
        big_gap = (current.top - previous.bottom) > max(0.5 * size, 1.5 * median_gap + 0.5)
        # 다음 줄의 첫 단어가 앞줄에 들어갈 자리가 있었다면 의도적인 줄바꿈이다.
        room = right_edge - previous.x1
        hyphenated = (len(previous.text) >= 2 and previous.text[-1] == "-" and previous.text[-2].isalpha()
                      and current.text[:1].isascii() and current.text[:1].islower())
        hard_break = not hyphenated and room > _first_word_width(current) + 0.6 * size
        hanging = bool(list_marker(first.text)[0])
        indented = not hanging and current.x0 - previous.x0 > 0.8 * size
        # 앞줄이 문장 부호로 끝났거나(번호 "1." "2026." 제외) 다음 줄이 연도로 시작하면 다른 문장이다.
        prev_text = previous.text.rstrip()
        sentence_end = prev_text[-1:] in ".!?。" and not _NUMBER_DOT_END.search(prev_text)
        date_start = bool(_DATE_START.match(current.text))
        if (starts_marker or size_change or big_gap or hard_break or indented or sentence_end or date_start
                or current.tabular or previous.tabular):
            paragraphs.append([current])
        else:
            paragraphs[-1].append(current)
    return paragraphs


def join_lines(lines: list[TextLine]) -> tuple[str, int]:
    """문단의 줄을 공백 하나로 잇는다. 첫 줄의 글머리 기호는 떼고, 영문 줄 끝 하이픈은 다음 줄과 붙인다. 반환: (text, 하이픈 제거 수)."""
    pieces: list[str] = []
    dehyphenated = 0
    for index, line in enumerate(lines):
        text = line.text
        if index == 0:
            kind, body_start = list_marker(text)
            if kind == "bullet":
                text = text[body_start:]
        is_last = index == len(lines) - 1
        joiner = "" if is_last else " "
        if not is_last and len(text) >= 2 and text[-1] in "-­":
            following = lines[index + 1].text[:1]
            if text[-1] == "­" or (text[-2].isascii() and text[-2].isalpha() and following.isascii() and following.islower()):
                text = text[:-1]
                joiner = ""
                dehyphenated += 1
        pieces.append(text + joiner)
    return "".join(pieces).rstrip(), dehyphenated


# ------------------------------------------------------------------ 선 없는 표 (공백으로 칸을 맞춘 행 묶음)
_MARKER_ONLY = re.compile(r"\(?\d{1,3}[.)]|\(?[가-힣a-zA-Z][.)]|[①-⑳]")
_BULLET_CHARS = set("•∙‣⁃◦○●◎◇◆□■▪▫▶▷►▻➢➤➔※✓✔·-–—*+→")


def _marker_only(text: str) -> bool:
    t = text.strip()
    return t in _BULLET_CHARS or bool(_MARKER_ONLY.fullmatch(t))


def _is_big(fragment: Fragment, body_size: float) -> bool:
    """제목·소제목 크기의 조각인지 (문자 크기 중앙값 기준)."""
    return _big_chars(fragment.chars, body_size)


def _big_chars(chars: list[Char], body_size: float) -> bool:
    sizes = [c.size for c in chars if c.text.strip()]
    return bool(sizes) and statistics.median(sizes) >= HEADING_RATIO * body_size


def _merge_fragments(parts: list[Fragment]) -> Fragment:
    """한 줄의 조각들을 하나로 합친다 (제목 줄은 간격이 커도 쪼개지 않는다)."""
    chars = [c for f in parts for c in f.chars]
    return Fragment(x0=min(f.x0 for f in parts), x1=max(f.x1 for f in parts), top=min(f.top for f in parts),
                    bottom=max(f.bottom for f in parts), chars=chars, line_id=parts[0].line_id)


_JOINERS = set("-–—:·/")      # 칸 사이에 홀로 있으면 구분선이 아니라 이음표: "개선안 2 - 냉각 유로" 는 한 줄
# 제목 크기 줄 안에서 새 항목이 시작되는 표식: 번호("2.", "3)", "①")나 전용 글머리 기호. 대시("- 부제")는 이어지는 글로 본다.
_NEW_ITEM = re.compile(r"^\s*(?:\(?\d{1,3}[.)]|\(?[a-zA-Z][.)]|\(?[가-힣][.)]|[①-⑳]|[ⅰ-ⅹⅠ-Ⅹ][.)])\s+|^\s*[•∙‣⁃◦○●◎◇◆□■▪▫▶▷►▻➢➤➔※✓✔]")


def _heading_groups(parts: list[Fragment]) -> list[list[Fragment]]:
    """제목 크기 줄의 조각을 묶는다. 간격이 커도 한 제목이지만, 번호·글머리 기호로 시작하는 조각은 새 항목(옆 단의 소제목)이다."""
    groups: list[list[Fragment]] = []
    for f in sorted(parts, key=lambda f: f.x0):
        line = build_line(f.chars)
        text = line.text if line else ""
        if groups and not _NEW_ITEM.match(text):
            groups[-1].append(f)
        else:
            groups.append([f])
    return groups


def _cells(parts: list[Fragment]) -> list[tuple[Fragment, TextLine]]:
    """줄의 조각 중 글머리 기호·번호만 있는 조각을 뺀 칸 목록."""
    out = []
    for f in parts:
        tl = build_line(f.chars)
        if tl is not None and not _marker_only(tl.text):
            out.append((f, tl))
    return out


def _aligned(prev: list[tuple[Fragment, TextLine]], cur: list[tuple[Fragment, TextLine]], size: float) -> bool:
    """칸 수가 같고 세로로 바로 아래에 있으며 칸마다 왼쪽 또는 오른쪽 끝이 맞으면 같은 표의 행."""
    if len(prev) != len(cur):
        return False
    if cur[0][0].top - max(f.bottom for f, _ in prev) > 2.0 * size:
        return False
    tol = 1.5 * size
    return all(abs(a.x0 - b.x0) <= tol or abs(a.x1 - b.x1) <= tol for (a, _), (b, _) in zip(prev, cur))


def _prose_like(rows: list[list[tuple[Fragment, TextLine]]]) -> bool:
    """좌우 2단 본문처럼 보이는 행 묶음인지. 글머리 기호로 시작하는 칸이 둘 이상이거나,
    어느 열이든 칸 대부분이 길고(20자 이상) 열 폭을 거의 채우면(75% 이상) 표가 아니라 단으로 본다."""
    if sum(1 for cells in rows if any(list_marker(tl.text)[0] == "bullet" for _, tl in cells)) >= 2:
        return True
    for col in range(len(rows[0])):
        widths = [cells[col][0].x1 - cells[col][0].x0 for cells in rows]
        wmax = max(widths) or 1.0
        long_cells = sum(1 for cells, w in zip(rows, widths) if len(cells[col][1].text) >= 20 and w >= 0.75 * wmax)
        if long_cells >= max(2, 0.6 * len(rows)):
            return True
    return False


def text_tables(per_line: list[tuple[int, list[Fragment]]], size: float) -> tuple[list[dict[str, Any]], set[int], set[int]]:
    """칸이 둘 이상인 줄이 같은 꼴로 둘 이상 이어지면 선 없는 표로 본다.
    반환: (표 목록, 표에 들어간 줄 id, 칸이 둘 이상인 줄 id)."""
    cands: list[tuple[int, list[tuple[Fragment, TextLine]], list[Fragment]]] = []
    for line_id, parts in per_line:
        cells = _cells(parts)
        if len(cells) >= 2:
            cands.append((line_id, cells, parts))
    tabular = {line_id for line_id, _, _ in cands}
    runs: list[list[tuple[int, list[tuple[Fragment, TextLine]], list[Fragment]]]] = []
    current: list = []
    for cand in cands:
        if current and cand[0] == current[-1][0] + 1 and _aligned(current[-1][1], cand[1], size):
            current.append(cand)
        else:
            if len(current) >= 2:
                runs.append(current)
            current = [cand]
    if len(current) >= 2:
        runs.append(current)
    tables, used = [], set()
    for run in runs:
        if _prose_like([cells for _, cells, _ in run]):
            continue
        frags = [f for _, _, parts in run for f in parts]
        tables.append({"bbox": (min(f.x0 for f in frags), min(f.top for f in frags), max(f.x1 for f in frags), max(f.bottom for f in frags)),
                       "text_rows": [[tl.text for _, tl in cells] for _, cells, _ in run], "chars": []})
        used.update(line_id for line_id, _, _ in run)
    return tables, used, tabular


# ------------------------------------------------------------------ 페이지
class _PageParser:
    def __init__(self, page: pymupdf.Page) -> None:
        self.page = page
        self.rotation = int(page.rotation or 0)
        self.width = float(page.rect.width) or 1.0
        self.height = float(page.rect.height) or 1.0
        self.blocks: list[Block] = []
        self.x_gap = 10.0
        self.body_size = 10.0
        self.meta: dict[str, Any] = {"rotated_chars": 0, "x_cuts": 0, "tables": 0, "text_tables": 0, "dehyphenated": 0,
                                     "images": 0, "vectors": 0}

    # ---- 문자 수집 ----
    def _chars(self) -> list[Char]:
        page = self.page
        m = page.rotation_matrix
        lin = pymupdf.Matrix(m.a, m.b, m.c, m.d, 0, 0)
        chars: list[Char] = []
        rotated = 0
        for block in page.get_text("rawdict", flags=_FLAGS).get("blocks", []):
            if block.get("type") != 0:
                continue
            for ln in block.get("lines", []):
                d = pymupdf.Point(ln.get("dir", (1, 0))) * lin        # 화면 기준 글 진행 방향
                upright = abs(d.y) < 0.1 and d.x > 0
                for span in ln.get("spans", []):
                    size = float(span.get("size") or 0.0)
                    bold = bool(int(span.get("flags") or 0) & 16) or "bold" in str(span.get("font") or "").lower()
                    for ch in span.get("chars", []):
                        c = ch.get("c", "")
                        if not upright:
                            if c.strip():
                                rotated += 1
                            continue
                        r = pymupdf.Rect(ch["bbox"]) * m                    # 화면 기준 좌표
                        chars.append(Char(c, r.x0, r.x1, r.y0, r.y1, size or (r.y1 - r.y0), bold))
        self.meta["rotated_chars"] = rotated
        return chars

    def parse(self) -> None:
        page = self.page
        chars = self._chars()
        visible = [c for c in chars if c.text.strip()]
        unmapped = sum(1 for c in visible if c.text == "�")
        self.meta["text_chars"] = len(visible)
        self.meta["unmapped_ratio"] = unmapped / len(visible) if visible else 0.0
        try:
            images = page.get_image_info()
        except Exception:
            images = []
        area = self.width * self.height
        self.meta["images"] = len(images)
        self.meta["image_ratio"] = min(1.0, sum(max(0.0, i["bbox"][2] - i["bbox"][0]) * max(0.0, i["bbox"][3] - i["bbox"][1])
                                                for i in images if i.get("bbox")) / area) if area else 0.0
        try:
            self.meta["vectors"] = len(page.get_cdrawings())
        except Exception:
            self.meta["vectors"] = 0
        if not visible or self.meta["unmapped_ratio"] > 0.2:
            return

        body_size = self.body_size = statistics.median(c.size for c in visible)
        self.meta["body_size"] = body_size
        tables = self._tables(chars)
        table_chars = {id(c) for table in tables for c in table["chars"]}
        free = [c for c in chars if id(c) not in table_chars]

        # 위·아래 8% 띠의 줄(문서명·쪽 번호)은 단 나눔의 영향을 받지 않도록 본문 배치 분석에서 떼어 둔다. 지우지는 않는다.
        fragments: list[Fragment] = []
        header_lines: list[TextLine] = []
        footer_lines: list[TextLine] = []
        body_lines: list[list[Char]] = []
        for line_chars in cluster_lines(free):
            shown = [c for c in line_chars if c.text.strip()]
            if not shown:
                continue
            if build_line(line_chars) is None:
                continue
            if max(c.bottom for c in shown) < EDGE_ZONE * self.height:
                header_lines.extend(_band_lines(line_chars))
            elif min(c.top for c in shown) > (1 - EDGE_ZONE) * self.height:
                footer_lines.extend(_band_lines(line_chars))
            else:
                body_lines.append(line_chars)
        tops = []
        per_line: list[tuple[int, list[Fragment]]] = []
        for line_id, line_chars in enumerate(body_lines):
            parts = split_fragments(line_chars, line_id)
            if len(parts) > 1 and _big_chars(line_chars, body_size):
                # 제목 크기 줄은 간격이 커도 한 줄 ("개선안 2   - 냉각 유로 이중화"). 번호로 시작하는 옆 단 소제목만 따로.
                parts = [_merge_fragments(g) for g in _heading_groups(parts)]
            if parts:
                per_line.append((line_id, parts))
                tops.append((min(p.top for p in parts), max(p.bottom for p in parts)))
        plain, used, _tabular = text_tables(per_line, body_size)
        self.meta["text_tables"] = len(plain)
        tables = tables + plain
        for line_id, parts in per_line:
            if line_id not in used:
                fragments.extend(parts)
        for table in tables:
            x0, top, x1, bottom = table["bbox"]
            fragments.append(Fragment(x0=x0, x1=x1, top=top, bottom=bottom, table=table))

        tops.sort()
        median_gap = lower_quartile([b[0] - a[1] for a, b in zip(tops, tops[1:]) if b[0] - a[1] > 0])
        stats: dict[str, int] = {}
        self.x_gap = max(1.5 * body_size, 10.0)
        standalone = {id(f) for f in fragments if f.table is not None or _is_big(f, body_size)}
        leaves = xy_cut(fragments, x_gap=self.x_gap, y_gap=max(0.6 * body_size, 1.6 * median_gap + 1.0),
                        min_col_width=max(8 * body_size, 0.15 * self.width), stats=stats, standalone=standalone)
        self.meta["x_cuts"] = stats.get("x_cuts", 0)

        # 잎마다 줄과 문단을 먼저 만들고, 목록 수준은 같은 단의 목록 항목 중 가장 왼쪽 것을 기준으로 정한다.
        # 줄바꿈 판단에 쓰는 오른쪽 끝은 잎이 아니라 단 전체의 가장 긴 줄로 잡는다(짧은 줄 몇 개만 있는 잎에서 잘못 합치지 않게).
        col_right: dict[str, float] = {}
        for column, leaf in leaves:
            xs = [f.x1 for f in leaf if f.table is None]
            if xs:
                col_right[column] = max(col_right.get(column, 0.0), max(xs))
        prepared = [(column, self._leaf_items(leaf, col_right.get(column, 0.0))) for column, leaf in leaves]
        column_left: dict[str, float] = {}
        any_left: dict[str, float] = {}
        for column, items in prepared:
            for _top, item in items:
                if not isinstance(item, dict):
                    any_left[column] = min(any_left.get(column, float("inf")), item[0].x0)
                    if list_marker(item[0].text)[0] and item[0].size < HEADING_RATIO * body_size:
                        column_left[column] = min(column_left.get(column, float("inf")), item[0].x0)
        for column, left in any_left.items():
            column_left.setdefault(column, left)
        for line in sorted(header_lines, key=lambda l: (l.top, l.x0)):
            self._paragraph([line], body_size, line.x0)
        for column, items in prepared:
            for _top, item in items:
                if isinstance(item, dict):
                    self._table_block(item)
                else:
                    self._paragraph(item, body_size, column_left[column])
        for line in sorted(footer_lines, key=lambda l: (l.top, l.x0)):
            self._paragraph([line], body_size, line.x0)

    # ---- 표 ----
    def _tables(self, chars: list[Char]) -> list[dict[str, Any]]:
        vectors = self.meta.get("vectors", 0)
        if vectors == 0 or self.rotation:          # 선이 없으면 표도 없다. 회전 페이지의 표 좌표는 믿기 어려워 건너뛴다
            return []
        if vectors > MAX_VECTORS:
            self.meta["table_detection_skipped"] = True
            return []
        try:
            found = self.page.find_tables().tables
        except Exception:
            return []
        tables = []
        for table in found:
            rows = [[cell for cell in row.cells] for row in table.rows]
            if len(rows) < 2 or max((sum(1 for c in row if c) for row in rows), default=0) < 2:
                continue
            x0, top, x1, bottom = (float(v) for v in table.bbox)
            inside = [c for c in chars if x0 <= (c.x0 + c.x1) / 2 <= x1 and top <= (c.top + c.bottom) / 2 <= bottom]
            if not any(c.text.strip() for c in inside):
                continue
            tables.append({"bbox": (x0, top, x1, bottom), "rows": rows, "chars": inside})
        self.meta["tables"] = len(tables)
        return tables

    def _cell_text(self, table: dict[str, Any], bbox) -> str:
        x0, top, x1, bottom = (float(v) for v in bbox)
        cell_chars = [c for c in table["chars"] if x0 <= (c.x0 + c.x1) / 2 <= x1 and top <= (c.top + c.bottom) / 2 <= bottom]
        lines = [line for line in (build_line(group) for group in cluster_lines(cell_chars)) if line]
        if not lines:
            return ""
        text, removed = join_lines(sorted(lines, key=lambda l: l.top))
        self.meta["dehyphenated"] += removed
        return text

    def _table_block(self, table: dict[str, Any]) -> None:
        if "text_rows" in table:
            rows = table["text_rows"]
        else:
            rows = [[self._cell_text(table, bbox) if bbox else "" for bbox in row] for row in table["rows"]]
        if any(any(c.strip() for c in r) for r in rows):
            self.blocks.append(Block(kind="table_row", text="", top=table["bbox"][1], size=0.0, rows=rows))

    # ---- 본문 ----
    def _leaf_items(self, leaf: list[Fragment], right_edge: float = 0.0) -> list[tuple[float, Any]]:
        """잎 하나의 내용: (위쪽 좌표, 표 또는 문단의 줄 묶음)을 위에서 아래 순으로."""
        by_line: dict[int, list[Fragment]] = {}
        for fragment in leaf:
            if fragment.table is None:
                by_line.setdefault(fragment.line_id, []).append(fragment)
        # 조각 하나짜리 줄들이 이 잎의 본문 폭 [L, R]. 다른 줄에서 그 폭 바깥에 떨어져 있는 조각(옆 도형의 라벨 등)은 따로 뗀다.
        singles = [fs[0] for fs in by_line.values() if len(fs) == 1 and not _marker_only(build_line(fs[0].chars).text)]
        left = min((f.x0 for f in singles), default=None)
        right = max((f.x1 for f in singles), default=None)
        lines: list[TextLine] = []
        apart: list[TextLine] = []         # 본문 폭 바깥의 조각: 문단 묶기에 끼우지 않고 각각 한 줄로
        for frags in by_line.values():
            frags.sort(key=lambda f: f.x0)
            body, outliers = frags, []
            if left is not None and len(frags) >= 2:
                outliers = [f for f in frags if f.x1 < left - self.x_gap or f.x0 > right + self.x_gap]
                body = [f for f in frags if f not in outliers]
            for f in outliers:
                line = build_line(f.chars)
                if line is not None:
                    apart.append(line)
            texts = [build_line(f.chars).text.strip() for f in body]
            if not body:
                continue
            if _big_chars([c for f in body for c in f.chars], self.body_size):
                pieces = _heading_groups(body)                      # 제목 크기 줄: 번호로 시작하는 조각만 따로
            elif any(t in _JOINERS for t in texts[1:-1]):
                pieces = [body]                                     # 칸 사이에 이음표("-", ":")만 홀로 있으면 한 줄
            else:
                cells = [f for f, t in zip(body, texts) if not _marker_only(t)]
                # 칸이 둘 이상인 줄(도형 라벨 둘, 이름=값 쌍 둘)은 칸마다 한 줄로 두고 앞뒤 줄과 문단으로 묶지 않는다.
                pieces = [[f] for f in cells] if len(cells) >= 2 else [body]
            for group in pieces:
                line = build_line([c for f in group for c in f.chars])
                if line is not None:
                    line.tabular = len(pieces) >= 2
                    lines.append(line)
        lines.sort(key=lambda l: (l.top, l.x0))
        items: list[tuple[float, Any]] = [(f.top, f.table) for f in leaf if f.table is not None]
        items.extend((line.top, [line]) for line in apart)
        right_edge = max(right_edge, max((line.x1 for line in lines), default=0.0))
        for paragraph in group_paragraphs(lines, right_edge):
            items.append((paragraph[0].top, paragraph))
        return sorted(items, key=lambda entry: entry[0])

    def _paragraph(self, item: list[TextLine], body_size: float, left_edge: float) -> None:
        """줄 묶음 하나를 블록으로 만든다."""
        marker_kind = list_marker(item[0].text)[0]
        text, removed = join_lines(item)
        self.meta["dehyphenated"] += removed
        text = clean(text)
        if not text:
            return
        size = statistics.median(line.size for line in item)
        if size >= HEADING_RATIO * body_size and len(text) <= 120:
            kind = "heading"                 # "3. 제어 로직 상세" 처럼 번호가 붙은 소제목도 제목 후보
        elif marker_kind:
            kind = "list_item"
        else:
            kind = "paragraph"
        level = int((item[0].x0 - left_edge) / (1.2 * body_size) + 0.5) if marker_kind else 0
        self.blocks.append(Block(kind=kind, text=text, top=item[0].top, size=size,
                                 level=max(0, min(MAX_LEVEL, level)), bold=sum(1 for l in item if l.bold) * 2 > len(item),
                                 x0=min(l.x0 for l in item), x1=max(l.x1 for l in item)))


@dataclass
class _Parsed:
    no: int
    height: float
    blocks: list[Block]
    has_graphics: bool
    meta: dict[str, Any]


def _pick_title(p: _Parsed) -> None:
    """제목 후보를 고른다 (순서대로). ① 위쪽 35% 안의 제목 크기 줄 중 가장 큰 것(font)
    ② 굵은 글씨로 본문 크기 이상인 줄 중 가장 위의 것(bold) ③ 위쪽 35% 안에서 본문의 0.8배 이상 크기인 첫 줄(first-line;
    8pt 문서명·쪽 번호 같은 작은 글은 건너뛰고, 그런 줄뿐이면 그중 첫 줄). 표는 제외한다. 머리말이라고 지우거나 빼는 규칙은 없다."""
    body = float(p.meta.get("body_size") or 0.0)
    zone = [b for b in p.blocks if b.kind != "table_row" and b.top < TITLE_ZONE * p.height and 0 < len(b.text) <= 120]
    if not zone:
        return
    heads = [b for b in zone if b.kind == "heading"]
    if heads:
        best, source = max(heads, key=lambda b: (round(b.size, 1), -b.top)), "font"
    else:
        bolds = [b for b in zone if b.bold and b.size >= 0.9 * body]
        if bolds:
            best, source = min(bolds, key=lambda b: b.top), "bold"
        else:
            best, source = next((b for b in zone if b.size >= TITLE_MIN_RATIO * body), zone[0]), "first-line"
    best.is_title, best.title_source = True, source


def _to_page(p: _Parsed) -> Page:
    blocks = p.blocks
    title, title_i, title_source = "", None, "없음"
    chosen = next(((i, b) for i, b in enumerate(blocks) if b.is_title), None)
    if chosen is None:
        chosen = next(((i, b) for i, b in enumerate(blocks) if b.kind != "table_row" and b.text), None)
        if chosen is not None:
            chosen[1].is_title, chosen[1].title_source = True, "first-line"
    if chosen is not None:
        title_i, title, title_source = chosen[0], chosen[1].text, chosen[1].title_source
    lines: list[Line] = []
    for i, b in enumerate(blocks):
        if i == title_i:
            continue
        if b.kind == "table_row":
            lines.extend(table_lines(b.rows or []))
        else:
            lines.append(Line(idx=0, text=b.text, level=b.level))
    return Page(no=p.no, title=title, lines=lines, has_graphics=p.has_graphics, title_source=title_source)


def read_pdf(path: Path) -> Document:
    parsed, notes = _parse_pdf(path)
    pages = [_to_page(p) for p in parsed]
    return Document(path=Path(path), kind="pdf", pages=pages, title=pages[0].title if pages else "", notes=notes)


def layout_report(path: Path, pages: set[int] | None = None) -> list[str]:
    """진단용: 페이지마다 고른 제목과 블록 목록(종류, 글씨 크기, 굵기, 세로 위치 %, 가로 범위, 글자 수, 앞부분)."""
    parsed, notes = _parse_pdf(path)
    out = [f"== {path}", *[f"  안내: {n}" for n in notes]]
    for p in parsed:
        if pages and p.no not in pages:
            continue
        _to_page(p)
        title = next((b for b in p.blocks if b.is_title), None)
        out.append(f"-- {p.no}쪽  본문 글씨 {p.meta.get('body_size', 0):.1f}pt  제목: {title.text[:60] if title else '(없음)'}"
                   f"  [{title.title_source if title else '없음'}]  그림 {p.meta.get('images', 0)} 선 {p.meta.get('vectors', 0)}"
                   f" 표 {p.meta.get('tables', 0) + p.meta.get('text_tables', 0)} 세로문자 {p.meta.get('rotated_chars', 0)}")
        for b in p.blocks:
            if b.kind == "table_row":
                out.append(f"     표 {len(b.rows or [])}행  top {100 * b.top / p.height:4.0f}%")
                continue
            out.append(f"     {'제목' if b.is_title else b.kind:<9} {b.size:5.1f}pt{' 굵게' if b.bold else '    '} top {100 * b.top / p.height:4.0f}%"
                       f"  x {b.x0:4.0f}-{b.x1:4.0f}  lv{b.level}  {len(b.text):3d}자  {b.text[:50]}")
    return out


def _parse_pdf(path: Path) -> tuple[list[_Parsed], list[str]]:
    doc = pymupdf.open(path)
    parsed: list[_Parsed] = []
    notes: list[str] = []
    multi_column: list[int] = []
    rotated: list[int] = []
    unmapped: list[int] = []
    failed: list[int] = []
    table_total = 0
    try:
        for pno, page in enumerate(doc, 1):
            parser = _PageParser(page)
            try:
                parser.parse()
            except Exception as exc:          # 한 페이지의 오류가 전체를 막지 않게 한다
                failed.append(pno)
                parser.blocks = []
                notes.append(f"{pno}쪽 읽기 실패: {type(exc).__name__}")
            meta = parser.meta
            has_graphics = meta.get("images", 0) > 0 or meta.get("vectors", 0) > 3
            if meta.get("unmapped_ratio", 0) > 0.2:
                unmapped.append(pno)
                has_graphics = True
            if meta.get("x_cuts"):
                multi_column.append(pno)
            if meta.get("rotated_chars"):
                rotated.append(pno)
            table_total += meta.get("tables", 0) + meta.get("text_tables", 0)
            parsed.append(_Parsed(no=pno, height=parser.height, blocks=parser.blocks, has_graphics=has_graphics, meta=meta))
    finally:
        doc.close()

    # 머리말·꼬리말을 반복 횟수로 지우던 규칙은 없다(v0.6.2 폐기). 반복 문구는 전처리가 후보에서만 뺀다.
    for p in parsed:
        _pick_title(p)
    if multi_column:
        notes.append(f"다단/좌우 배치를 나눠 읽은 페이지 {len(multi_column)}쪽 ({_pages(multi_column)}): 읽기 순서를 확인하세요")
    if rotated:
        notes.append(f"세로로 선 문자를 읽지 않은 페이지 {len(rotated)}쪽 ({_pages(rotated)})")
    if unmapped:
        notes.append(f"글꼴 매핑이 깨져 본문을 읽지 못한 페이지 {len(unmapped)}쪽 ({_pages(unmapped)}): 이미지 페이지로 처리")
    if table_total:
        notes.append(f"표 {table_total}개를 셀 단위로 읽음 (열 제목: 셀)")
    return parsed, notes


def _pages(nums: list[int]) -> str:
    return ", ".join(str(n) for n in nums[:8]) + (" …" if len(nums) > 8 else "")
