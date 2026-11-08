"""전체 코드 주석 페이지: files.py 의 모든 파일을 줄마다 설명과 함께. 설명이 없는 줄은 todo/ 에 적고 개수를 출력한다.
실행: python tools/walkthrough/build_full.py [out.html]"""
from __future__ import annotations

import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402
from files import FILES  # noqa: E402


def anchor_of(path: str) -> str:
    return "f-" + path.replace("/", "-").replace(".", "-")


def main(out: Path) -> int:
    sections = []
    nav: dict[str, list[tuple[str, str, str]]] = {}
    total_lines = total_missing = 0
    for group, path, role in FILES:
        lines = lib.read_source(path)
        notes, missing = lib.apply_notes(path, lines)
        lib.write_todo(path, lines, missing)
        nonblank = sum(1 for l in lines if l.strip())
        total_lines += nonblank
        total_missing += len(missing)
        nav.setdefault(group, []).append((anchor_of(path), Path(path).name, f"{len(lines)}줄"))
        sections.append(f'<section id="{anchor_of(path)}"><h2>{html.escape(path)}<small>{len(lines)}줄</small></h2><p class="role">{html.escape(role)}</p>'
                        + lib.code_block(path, lines, 1, len(lines), notes, f"1–{len(lines)}") + "</section>")
        if missing:
            print(f"  {path}: 설명 없는 줄 {len(missing)}/{nonblank}")
    from ip_finder import __version__
    intro = ('<div class="intro"><p><b>읽는 법.</b> 왼쪽 차례는 폴더가 아니라 <b>한 번의 실행이 지나가는 순서</b>(조립 → 진입점 → 읽기 → 전처리 → 1차 분류기 → 후처리 → 골드·이력 → 비교 도구 → 출력 → 가짜 샘플 → 테스트)다. '
             '각 줄은 <b>번호 | 코드 | 설명</b>이고, 설명이 비스듬한 글씨면 앞 줄에 이어지는 부분이다. 차례 아래 단추로 설명을 숨겨 코드만 볼 수 있다. '
             f'프로그램 버전 {__version__}, 소스 파일 {len(FILES)}개, 비어 있지 않은 줄 {total_lines}개.</p>'
             '<p><b>0단계(rebuild)에서 바뀐 것.</b> LLM 2차 판정이 빠졌고, 읽기·전처리·후처리 규칙은 모두 <code>switches.py</code> 의 스위치(기본 끔)가 됐으며, 1차 분류기 7종이 <code>classify/</code> 에 같은 인터페이스로 있다. '
             '<code>compare/</code> 가 개량 전후를 문장 단위로 비교한다(run-all, compare-runs, ladder, compare-classifiers).</p></div>')
    page = lib.render_page("IP Finder 전체 코드 주석", f"rebuild {__version__} — 모든 줄에 설명", intro,
                           [(g, items) for g, items in nav.items()], "".join(sections),
                           "IP Finder rebuild 브랜치의 소스 파일 전부를 줄마다 설명과 함께 보는 페이지")
    out.write_text(page, encoding="utf-8")
    print(f"비어 있지 않은 줄 {total_lines}, 설명 없는 줄 {total_missing} → {out} ({out.stat().st_size // 1024} KB)")
    return 0 if total_missing == 0 else 1


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "out" / "full.html"))
