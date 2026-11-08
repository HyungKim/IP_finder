"""코드 리뷰 페이지 빌더 공용 (개발용 도구, 프로그램 의존성 아님).

저장소 파일을 줄마다 (번호 | 코드 | 한 줄 설명) 으로 늘어놓는 HTML 을 만든다. 설명은 notes/<경로>.tsv 에
`줄의 글(앞뒤 공백 제거)<TAB>설명` 꼴로 저장한다 — 줄 번호가 아니라 줄의 글로 묶어 두므로 코드가 위아래로 밀려도 설명이 따라간다.
같은 글이 여러 번 나오면 나오는 순서대로 짝짓는다. 구문 강조는 pygments 가 있으면 빌드 때 넣는다(브라우저 스크립트 불필요)."""
from __future__ import annotations

import html
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NOTES_DIR = Path(__file__).resolve().parent / "notes"
TODO_DIR = Path(__file__).resolve().parent / "todo"

try:
    from pygments import lex
    from pygments.lexers import get_lexer_by_name
    from pygments.token import Comment, Keyword, Name, Number, Operator, String
    HAVE_PYGMENTS = True
except ImportError:          # pragma: no cover
    HAVE_PYGMENTS = False

_LEXER_NAME = {".py": "python", ".json": "json", ".toml": "toml", ".md": "markdown", ".bat": "bat", ".txt": "text"}


# ------------------------------------------------------------------ 설명 저장소 (글 기준)
def key_of(line: str) -> str:
    return line.expandtabs(4).strip()


def notes_file(path: str) -> Path:
    return NOTES_DIR / (path.replace("/", "__") + ".tsv")


def load_notes(path: str) -> dict[str, list[str]]:
    """{줄의 글: [설명, ...]} (파일에 적힌 순서)."""
    f = notes_file(path)
    store: dict[str, list[str]] = {}
    if not f.exists():
        return store
    for raw in f.read_text(encoding="utf-8").splitlines():
        if "\t" not in raw:                 # 머리 주석과 빈 줄 (코드의 주석 줄은 열쇠가 # 으로 시작해도 탭이 있다)
            continue
        text, _, note = raw.partition("\t")
        if note.strip():
            store.setdefault(text, []).append(note.strip())
    return store


def save_notes(path: str, pairs: list[tuple[str, str]]) -> None:
    """(줄의 글, 설명) 목록을 파일 순서대로 저장한다."""
    f = notes_file(path)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(f"# {path} — 줄의 글<TAB>설명. tools/walkthrough/lib.py 가 읽는다.\n"
                 + "\n".join(f"{t}\t{n}" for t, n in pairs) + "\n", encoding="utf-8")


def read_source(path: str, ref: str | None = None) -> list[str]:
    """작업 폴더의 파일, 또는 git ref 시점의 파일."""
    if ref:
        out = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        if out.returncode != 0:
            raise FileNotFoundError(f"{ref}:{path}")
        return out.stdout.splitlines()
    return (ROOT / path).read_text(encoding="utf-8").splitlines()


def apply_notes(path: str, lines: list[str], store: dict[str, list[str]] | None = None) -> tuple[dict[int, str], list[int]]:
    """줄 번호 → 설명. 설명이 없는 비어 있지 않은 줄 번호도 함께 돌려준다."""
    store = load_notes(path) if store is None else store
    counters: dict[str, int] = {}
    notes: dict[int, str] = {}
    missing: list[int] = []
    for no, raw in enumerate(lines, 1):
        k = key_of(raw)
        if not k:
            continue
        lst = store.get(k)
        if lst:
            i = counters.get(k, 0)
            notes[no] = lst[min(i, len(lst) - 1)]
            counters[k] = i + 1
        else:
            missing.append(no)
    return notes, missing


def normalize_notes(path: str) -> int:
    """현재 파일 순서대로 TSV 를 다시 쓴다(옛 줄 설명은 그대로 두되 순서만 정리). 설명 수를 돌려준다."""
    lines = read_source(path)
    notes, _ = apply_notes(path, lines)
    pairs = [(key_of(lines[no - 1]), notes[no]) for no in sorted(notes)]
    save_notes(path, pairs)
    return len(pairs)


def add_notes_by_line(path: str, staged: dict[int, str]) -> int:
    """{줄 번호: 설명} 을 현재 파일 기준으로 글 열쇠로 바꿔 저장한다. 이미 있는 설명은 새 것으로 바뀐다."""
    lines = read_source(path)
    notes, _ = apply_notes(path, lines)
    for no, note in staged.items():
        if 1 <= no <= len(lines) and key_of(lines[no - 1]) and note.strip():
            notes[no] = note.strip()
    pairs = [(key_of(lines[no - 1]), notes[no]) for no in sorted(notes)]
    save_notes(path, pairs)
    return len(pairs)


def write_todo(path: str, lines: list[str], missing: list[int]) -> Path | None:
    TODO_DIR.mkdir(parents=True, exist_ok=True)
    f = TODO_DIR / (path.replace("/", "__") + ".tsv")
    if not missing:
        if f.exists():
            f.unlink()
        return None
    f.write_text("\n".join(f"{no}\t{lines[no - 1].rstrip()}" for no in missing) + "\n", encoding="utf-8")
    return f


# ------------------------------------------------------------------ HTML
def _tok_class(ttype) -> str:
    if ttype in Comment:
        return "cmt"
    if ttype in String:
        return "str"
    if ttype in Keyword or ttype is Operator.Word:
        return "kw"
    if ttype in Number:
        return "num"
    if ttype in Name.Decorator:
        return "meta"
    if ttype in Name.Class or ttype in Name.Exception:
        return "cls"
    if ttype in Name.Function or ttype in Name.Builtin:
        return "fn"
    return ""


def _esc(part: str) -> str:
    return html.escape(part).replace("�", "&#xFFFD;")


def highlight_lines(text: str, suffix: str) -> list[str]:
    lines_src = text.split("\n")
    if not HAVE_PYGMENTS or suffix not in _LEXER_NAME:
        return [_esc(l) for l in lines_src]
    lexer = get_lexer_by_name(_LEXER_NAME[suffix])
    out: list[list[str]] = [[]]
    for ttype, value in lex(text, lexer):
        cls = _tok_class(ttype)
        for i, part in enumerate(value.split("\n")):
            if i:
                out.append([])
            if part:
                e = _esc(part)
                out[-1].append(f'<span class="{cls}">{e}</span>' if cls else e)
    rendered = ["".join(l) for l in out]
    while len(rendered) > len(lines_src) and rendered[-1] == "":
        rendered.pop()
    while len(rendered) < len(lines_src):
        rendered.append("")
    return rendered


def code_block(path: str, lines: list[str], start: int, end: int, notes: dict[int, str], caption: str | None = None) -> str:
    """lines[start-1:end] 를 (번호 | 코드 | 설명) 행으로."""
    segment = lines[start - 1:end]
    rendered = highlight_lines("\n".join(segment), Path(path).suffix)
    rows = []
    for offset, (raw, hl) in enumerate(zip(segment, rendered)):
        no = start + offset
        blank = not raw.strip()
        n = html.escape(notes.get(no, ""))
        cls = "ln"
        if blank:
            cls += " blank"
            n = ""
        elif not n:
            cls += " cont"
            n = "↳ 앞 줄에 이어지는 부분"
        elif n.startswith("↳"):
            cls += " cont"
        rows.append(f'<div class="{cls}"><span class="n">{no}</span><code>{hl or "&nbsp;"}</code><span class="note">{n}</span></div>')
    cap = caption or f"{start}–{end}"
    return (f'<figure class="code"><figcaption><span class="path">{html.escape(path)}</span><span class="lines">{html.escape(cap)}</span></figcaption>'
            f'<div class="ann">{"".join(rows)}</div></figure>')


CSS = """
:root{--bg:#fbfaf7;--fg:#1d1d1b;--muted:#5f5e58;--line:#e4e1d8;--card:#ffffff;--accent:#8a3b12;--codebg:#f3f1ea;--kw:#7a1f8a;--str:#1b6e3a;--cmt:#7b776c;--num:#9a4b00;--fn:#1f4fa3;--cls:#8a5a00;--meta:#6a1f7a;--note:#2e2d2a;--notebg:#fff9ec;--sticky:#fbfaf7e6}
:root:not([data-theme="light"]){color-scheme:light dark}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#15161a;--fg:#e8e6df;--muted:#a09d93;--line:#2c2e35;--card:#1c1e24;--accent:#e9a06a;--codebg:#111216;--kw:#d78be8;--str:#8fd3a3;--cmt:#8b887c;--num:#f0b36c;--fn:#8fb4ff;--cls:#f0c86c;--meta:#d6a3e6;--note:#e0ddd3;--notebg:#1f1c14;--sticky:#15161ae6}}
:root[data-theme="dark"]{--bg:#15161a;--fg:#e8e6df;--muted:#a09d93;--line:#2c2e35;--card:#1c1e24;--accent:#e9a06a;--codebg:#111216;--kw:#d78be8;--str:#8fd3a3;--cmt:#8b887c;--num:#f0b36c;--fn:#8fb4ff;--cls:#f0c86c;--meta:#d6a3e6;--note:#e0ddd3;--notebg:#1f1c14;--sticky:#15161ae6}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 "IBM Plex Sans KR","Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif}
a{color:var(--accent)}
.wrap{display:grid;grid-template-columns:260px minmax(0,1fr);gap:24px;max-width:1500px;margin:0 auto;padding:0 16px}
nav{position:sticky;top:0;align-self:start;max-height:100vh;overflow:auto;padding:18px 0;font-size:13px}
nav h1{font-size:16px;margin:0 0 6px}nav .sub{color:var(--muted);margin:0 0 12px}
nav .grp{margin:10px 0 2px;color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.04em}
nav a{display:block;color:var(--fg);text-decoration:none;padding:2px 6px;border-left:2px solid transparent;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
nav a.on{border-left-color:var(--accent);color:var(--accent)}
nav .count{color:var(--muted);font-size:11px}
nav button{margin:10px 0 0;padding:6px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--fg);cursor:pointer;font:inherit;font-size:13px}
main{padding:18px 0 80px;min-width:0}
h2{font-size:20px;margin:40px 0 6px;padding-top:12px;border-top:1px solid var(--line)}
h2 small{color:var(--muted);font-weight:400;font-size:13px;margin-left:8px}
.role{color:var(--muted);margin:0 0 10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin:8px 0 14px}
.card p{margin:4px 0}.card b{color:var(--accent)}
.badge{display:inline-block;font-size:12px;padding:1px 8px;border-radius:999px;border:1px solid var(--line);color:var(--muted);margin-right:6px}
.intro{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 18px;margin:16px 0}
.intro ul{margin:6px 0 0 18px;padding:0}
figure.code{margin:10px 0 18px;border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--card)}
figcaption{display:flex;justify-content:space-between;gap:12px;padding:6px 12px;font-size:12px;color:var(--muted);background:var(--codebg);border-bottom:1px solid var(--line)}
.ann{font-size:13px}
.ln{display:grid;grid-template-columns:3.4em minmax(0,1fr) minmax(0,1fr);border-top:1px solid var(--line)}
.ln:first-child{border-top:0}
.ln .n{color:var(--muted);text-align:right;padding:3px 8px 3px 0;font:12px/1.65 "IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;background:var(--codebg);user-select:none}
.ln code{display:block;padding:3px 10px;white-space:pre-wrap;word-break:break-all;font:12.5px/1.65 "IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;background:var(--codebg)}
.ln .note{padding:3px 10px;color:var(--note);background:var(--notebg);font-size:13px;line-height:1.5}
.ln.blank .note{background:var(--card)}.ln.cont .note{color:var(--muted);font-style:italic}
.kw{color:var(--kw);font-weight:600}.str{color:var(--str)}.cmt{color:var(--cmt);font-style:italic}.num{color:var(--num)}.fn{color:var(--fn)}.cls{color:var(--cls)}.meta{color:var(--meta)}
body.plain .ln{grid-template-columns:3.4em minmax(0,1fr)}body.plain .ln .note{display:none}
table{border-collapse:collapse;font-size:13px;margin:8px 0}td,th{border:1px solid var(--line);padding:4px 8px;text-align:left;vertical-align:top}th{background:var(--codebg)}
@media (max-width:960px){.wrap{grid-template-columns:1fr}nav{position:static;max-height:none;border-bottom:1px solid var(--line)}
.ln{grid-template-columns:3em minmax(0,1fr)}.ln .note{grid-column:1/-1;border-top:1px dashed var(--line)}}
"""

JS = """
(function(){var b=document.getElementById('toggle-notes');var k='ipf-walkthrough-plain';
function set(on){document.body.classList.toggle('plain',on);if(b)b.textContent=on?'설명 보이기':'설명 숨기기 (코드만)';try{localStorage.setItem(k,on?'1':'0')}catch(e){}}
try{set(localStorage.getItem(k)==='1')}catch(e){}
if(b)b.addEventListener('click',function(){set(!document.body.classList.contains('plain'))});
var links=[].slice.call(document.querySelectorAll('nav a[href^="#"]'));var map={};links.forEach(function(a){map[a.getAttribute('href').slice(1)]=a});
if('IntersectionObserver' in window){var io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){links.forEach(function(a){a.classList.remove('on')});var a=map[e.target.id];if(a)a.classList.add('on')}})},{rootMargin:'-10% 0px -80% 0px'});
document.querySelectorAll('main section[id]').forEach(function(s){io.observe(s)})}})();
"""


def render_page(title: str, subtitle: str, intro_html: str, nav_groups: list[tuple[str, list[tuple[str, str, str]]]], body_html: str,
                description: str = "") -> str:
    """nav_groups = [(묶음 이름, [(anchor, 표시 이름, 덧붙임), ...])]"""
    nav = []
    for group, items in nav_groups:
        nav.append(f'<div class="grp">{html.escape(group)}</div>')
        for anchor, label, extra in items:
            nav.append(f'<a href="#{anchor}">{html.escape(label)} <span class="count">{html.escape(extra)}</span></a>')
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><meta name="description" content="{html.escape(description or subtitle)}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans+KR:wght@400;600&display=swap">
<style>{CSS}</style></head><body>
<div class="wrap"><nav><h1>{html.escape(title)}</h1><p class="sub">{html.escape(subtitle)}</p><button id="toggle-notes" type="button">설명 숨기기 (코드만)</button>{''.join(nav)}</nav>
<main>{intro_html}{body_html}</main></div><script>{JS}</script></body></html>"""
