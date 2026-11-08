"""일회용: 예전(0.6.2) 줄 번호 기준 설명(n*.py, f_*.py 의 NOTES[(경로, 시작줄)][줄번호])을 글 기준 TSV 로 옮긴다.
옛 설명은 v0.6.2 시점의 파일 내용으로 글 열쇠를 만든다. 실행: python tools/walkthrough/migrate_notes.py <옛 notes 폴더>"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

REF = "v0.6.2"


def load_module(p: Path):
    spec = importlib.util.spec_from_file_location(p.stem, p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main(src_dir: Path) -> None:
    merged: dict[str, dict[int, str]] = {}
    for f in sorted(src_dir.glob("*.py")):
        if not (f.name.startswith("n0") or f.name.startswith("f_")):
            continue
        notes = getattr(load_module(f), "NOTES", {})
        for (path, _start), per_line in notes.items():
            merged.setdefault(path, {}).update({int(k): v for k, v in per_line.items()})
    total = 0
    for path, per_line in sorted(merged.items()):
        try:
            lines = lib.read_source(path, REF)
        except FileNotFoundError:
            print(f"  skip {path} (not in {REF})")
            continue
        pairs = []
        for no in sorted(per_line):
            if 1 <= no <= len(lines):
                k = lib.key_of(lines[no - 1])
                if k:
                    pairs.append((k, per_line[no]))
        lib.save_notes(path, pairs)
        total += len(pairs)
        print(f"  {path}: {len(pairs)} notes")
    print(f"total {total} notes from {len(merged)} files")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
