"""변경 리뷰 페이지: 기준 커밋(기본 v0.6.2)과 지금 작업 폴더의 차이를 파일별로, 바뀐 부분만 줄 설명과 함께 보여 준다.
파일마다 review_meta.py 의 '왜 바꿨나 / 어떻게 확인하나' 를 머리에 붙인다. 새 파일은 전체, 고친 파일은 바뀐 영역(앞뒤 3줄), 지운 파일은 목록만.
실행: python tools/walkthrough/build_review.py [기준 ref] [out.html]"""
from __future__ import annotations

import html
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402
from files import FILES  # noqa: E402
from review_meta import GROUPS, META, SUMMARY  # noqa: E402

HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
CONTEXT = 3
GAP = 6
INCLUDE_EXT = {".py", ".toml", ".md", ".json", ".bat"}


def changed_files(ref: str) -> list[tuple[str, str]]:
    """[(상태 A/M/D, 경로)] — 작업 폴더 기준 (스테이지 여부 무관)."""
    out = subprocess.run(["git", "diff", "--name-status", ref], cwd=lib.ROOT, capture_output=True, text=True, encoding="utf-8").stdout
    rows = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            rows.append((parts[0][0], parts[-1]))
    # 추적되지 않은 새 파일도 포함
    untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=lib.ROOT, capture_output=True, text=True, encoding="utf-8").stdout
    known = {p for _, p in rows}
    for p in untracked.splitlines():
        if p and p not in known:
            rows.append(("A", p))
    return rows


def new_ranges(ref: str, path: str) -> list[tuple[int, int]]:
    out = subprocess.run(["git", "diff", "--unified=0", ref, "--", path], cwd=lib.ROOT, capture_output=True, text=True, encoding="utf-8").stdout
    ranges = []
    for line in out.splitlines():
        m = HUNK.match(line)
        if m:
            start = int(m.group(1))
            count = int(m.group(2)) if m.group(2) is not None else 1
            if count > 0:
                ranges.append((start, start + count - 1))
    return ranges


def merge_ranges(ranges: list[tuple[int, int]], n_lines: int) -> list[tuple[int, int]]:
    out: list[list[int]] = []
    for a, b in sorted(ranges):
        a, b = max(1, a - CONTEXT), min(n_lines, b + CONTEXT)
        if out and a <= out[-1][1] + GAP:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def anchor_of(path: str) -> str:
    return "r-" + path.replace("/", "-").replace(".", "-")


def main(ref: str, out: Path) -> int:
    roles = {p: r for _, p, r in FILES}
    rows = changed_files(ref)
    sections = []
    nav: dict[str, list[tuple[str, str, str]]] = {}
    deleted = [p for s, p in rows if s == "D"]
    stats = {"A": 0, "M": 0, "D": len(deleted), "lines": 0}
    order = {p: i for i, (_, p, _) in enumerate(FILES)}
    shown = [(s, p) for s, p in rows if s != "D" and Path(p).suffix in INCLUDE_EXT and not p.startswith("tools/walkthrough/")]
    shown.sort(key=lambda sp: (order.get(sp[1], 999), sp[1]))
    for status, path in shown:
        lines = lib.read_source(path)
        notes, _ = lib.apply_notes(path, lines)
        meta = META.get(path, {})
        group = meta.get("group") or next((g for g, p, _ in FILES if p == path), "기타")
        if status == "A":
            ranges = [(1, len(lines))]
            stats["A"] += 1
        else:
            ranges = merge_ranges(new_ranges(ref, path), len(lines))
            stats["M"] += 1
        stats["lines"] += sum(b - a + 1 for a, b in ranges)
        badge = "새 파일" if status == "A" else f"수정 ({len(ranges)}곳)"
        head = (f'<section id="{anchor_of(path)}"><h2>{html.escape(path)}<small>{html.escape(badge)} · {len(lines)}줄</small></h2>'
                f'<p class="role">{html.escape(meta.get("role") or roles.get(path, ""))}</p><div class="card">'
                f'<p><b>왜 바꿨나.</b> {html.escape(meta.get("why", "(설명 없음)"))}</p>'
                f'<p><b>어떻게 확인하나.</b> {html.escape(meta.get("check", "(설명 없음)"))}</p></div>')
        if notes:
            blocks = [lib.code_block(path, lines, a, b, notes) for a, b in ranges]
        else:                                   # 문서·설정·배치 파일: 줄 설명 없이 머리말 카드만
            blocks = [f'<p class="role">문서·설정 파일이라 줄 설명은 없다. 내용은 저장소의 <code>{html.escape(path)}</code> 에서 본다.</p>']
            stats["lines"] -= sum(b - a + 1 for a, b in ranges)
        sections.append(head + "".join(blocks) + "</section>")
        nav.setdefault(group, []).append((anchor_of(path), Path(path).name, "새" if status == "A" else f"{len(ranges)}곳"))
    from ip_finder import __version__
    intro = [f'<div class="intro"><p><b>{html.escape(SUMMARY["title"])}</b></p><p>{html.escape(SUMMARY["lead"])}</p><ul>']
    intro += [f"<li>{html.escape(x)}</li>" for x in SUMMARY["points"]]
    intro.append("</ul>")
    intro.append(f'<p>기준 <code>{html.escape(ref)}</code> → 지금({__version__}). 새 파일 {stats["A"]}개, 고친 파일 {stats["M"]}개, 지운 파일 {stats["D"]}개, 이 페이지에 실린 줄 {stats["lines"]}개. '
                 '각 파일 머리의 카드가 "왜 바꿨나 / 어떻게 확인하나"다. 고친 파일은 바뀐 영역만(앞뒤 3줄) 보이고, 전체는 <a href="' + html.escape(SUMMARY.get("full_url", "#")) + '">전체 코드 주석</a>에서 본다.</p>')
    if deleted:
        intro.append("<p><b>지운 파일.</b> " + ", ".join(f"<code>{html.escape(p)}</code>" for p in deleted) + f" — {html.escape(SUMMARY.get('deleted_why', ''))}</p>")
    intro.append("</div>")
    nav_groups = [(g, nav[g]) for g in GROUPS if g in nav] + [(g, items) for g, items in nav.items() if g not in GROUPS]
    page = lib.render_page(SUMMARY["title"], f"{ref} → {__version__}", "".join(intro), nav_groups, "".join(sections), SUMMARY["lead"])
    out.write_text(page, encoding="utf-8")
    print(f"{out} ({out.stat().st_size // 1024} KB): 새 {stats['A']}, 수정 {stats['M']}, 삭제 {stats['D']}, 줄 {stats['lines']}")
    return 0


if __name__ == "__main__":
    ref = sys.argv[1] if len(sys.argv) > 1 else "v0.6.2"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent / "out" / "review.html"
    sys.exit(main(ref, out))
