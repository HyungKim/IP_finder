"""파싱 점검 HTML: 리더가 파일에서 무엇을 읽어 냈는지 사람이 눈으로 확인하는 페이지.

쪽마다 왼쪽에 원본 쪽 그림(PDF 는 PyMuPDF 로 그림, PPTX 는 윈도우 PowerPoint 가 있을 때 내보내기), 오른쪽에 **레이아웃 분석**이 읽은 줄
(제목·본문·표·도형, 목록 계층), 맨 위 체크를 켜면 **원시 읽기**가 읽은 줄도 나란히. 현재 설정의 전처리 규칙이 뺄 줄은 회색에 사유 표시.
맨 위 표에 쪽마다 줄 수·제목 출처·점검 표시(⚠)가 있어 어느 쪽을 봐야 하는지 바로 안다. 파일 하나로 완결되어(그림 내장) 브라우저로 연다.
분류기는 돌리지 않는다. 실행: ip-finder parse 보고서.pdf / parse.bat / UI '파싱 점검'."""
from __future__ import annotations

import base64
import html
import sys
from pathlib import Path

from .. import __version__
from ..config import Config
from ..models import Line, Page
from ..readers import load_document

MAX_IMAGE_WIDTH = 900
SOURCE_NAME = {"body": "", "table": "표", "diagram": "도형"}


# ------------------------------------------------------------------ 쪽 그림
def _data_uri(data: bytes, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


def pdf_images(path: Path, max_width: int = MAX_IMAGE_WIDTH) -> list[str]:
    """PDF 쪽을 JPEG(안 되면 PNG)로 그려 data URI 목록으로."""
    import pymupdf
    out: list[str] = []
    doc = pymupdf.open(path)
    try:
        for page in doc:
            zoom = min(2.0, max_width / float(page.rect.width or 1.0))
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
            try:
                out.append(_data_uri(pix.tobytes("jpg", jpg_quality=75), "image/jpeg"))
            except Exception:
                out.append(_data_uri(pix.tobytes("png"), "image/png"))
    finally:
        doc.close()
    return out


def pptx_images(path: Path, width: int = MAX_IMAGE_WIDTH) -> list[str] | None:
    """윈도우 PowerPoint(COM)로 슬라이드를 PNG 로 내보낸다. 다른 환경이나 실패 시 None (그림 없이 글만 보여 준다)."""
    if sys.platform != "win32":
        return None
    try:
        import tempfile
        import win32com.client  # type: ignore
        app = win32com.client.Dispatch("PowerPoint.Application")
        pres = app.Presentations.Open(str(path.resolve()), True, False, False)   # ReadOnly, Untitled, WithWindow
        try:
            with tempfile.TemporaryDirectory() as td:
                out: list[str] = []
                for i in range(1, pres.Slides.Count + 1):
                    f = Path(td) / f"s{i}.png"
                    pres.Slides(i).Export(str(f), "PNG", width, int(width * 9 / 16))
                    out.append(_data_uri(f.read_bytes(), "image/png"))
                return out
        finally:
            pres.Close()
    except Exception:
        return None


def page_images(path: Path, kind: str, images: bool) -> tuple[list[str] | None, str]:
    """(쪽 그림 목록 또는 None, 그림이 없을 때 안내)"""
    if not images:
        return None, "그림 생략(--no-images)"
    if kind == "pdf":
        try:
            return pdf_images(path), ""
        except Exception as e:
            return None, f"쪽 그림을 만들지 못함: {e}"
    src = path if path.suffix.lower() == ".pptx" else path.with_suffix(".pptx")
    imgs = pptx_images(src) if src.exists() else None
    return imgs, "" if imgs else "PPTX 쪽 그림은 윈도우의 PowerPoint 가 있을 때만 만듭니다. 글만 보여 줍니다."


# ------------------------------------------------------------------ 점검 표시
def page_flags(lay: Page, raw: Page) -> list[str]:
    """사람이 먼저 봐야 할 쪽을 표시한다."""
    flags = []
    nl, nr = len([l for l in lay.lines if l.text.strip()]), len([l for l in raw.lines if l.text.strip()])
    if nl == 0 and nr == 0 and not lay.title and not raw.title:
        flags.append("글 없음" + (" (그림·도형 있음)" if lay.has_graphics else ""))
    elif nl == 0 and nr > 0:
        flags.append("레이아웃 분석이 줄을 하나도 못 읽음")
    if lay.title_source in ("없음", "") and (nl or nr):
        flags.append("제목 없음")
    if nl and nr and (nl >= 2 * nr or nr >= 2 * nl):
        flags.append(f"두 읽기의 줄 수 차이 큼 ({nl} / {nr})")
    if lay.excluded_reason:
        flags.append(f"현재 설정에서 쪽 제외: {lay.excluded_reason}")
    return flags


# ------------------------------------------------------------------ HTML
CSS = """
:root{--bg:#fbfaf7;--fg:#1d1d1b;--muted:#6b6a63;--line:#e4e1d8;--card:#fff;--accent:#8a3b12;--warn:#b45309;--warnbg:#fff4e0;--out:#9a9890;--tag:#eef0f4;--tagfg:#334;--title:#1f4fa3}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#15161a;--fg:#e8e6df;--muted:#a09d93;--line:#2c2e35;--card:#1c1e24;--accent:#e9a06a;--warn:#f0b36c;--warnbg:#2a2113;--out:#777;--tag:#2a2d35;--tagfg:#cdd;--title:#8fb4ff}}
:root[data-theme="dark"]{--bg:#15161a;--fg:#e8e6df;--muted:#a09d93;--line:#2c2e35;--card:#1c1e24;--accent:#e9a06a;--warn:#f0b36c;--warnbg:#2a2113;--out:#777;--tag:#2a2d35;--tagfg:#cdd;--title:#8fb4ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.55 "Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif}
.wrap{max-width:1600px;margin:0 auto;padding:0 16px 60px}
h1{font-size:20px;margin:18px 0 4px}.sub{color:var(--muted);margin:0 0 10px}
.intro{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin:10px 0}
.intro ul{margin:6px 0 0 18px;padding:0}
.tools{position:sticky;top:0;background:var(--bg);padding:8px 0;border-bottom:1px solid var(--line);z-index:2;display:flex;gap:16px;flex-wrap:wrap;align-items:center}
.tools label{cursor:pointer;user-select:none}
table.sum{border-collapse:collapse;font-size:13px;margin:10px 0;width:100%}
.sum th,.sum td{border:1px solid var(--line);padding:4px 8px;text-align:left;vertical-align:top}.sum th{background:var(--tag)}
.sum td.flag{color:var(--warn)}.sum a{color:var(--accent);text-decoration:none}
section.page{border-top:1px solid var(--line);padding:14px 0 6px;margin-top:10px}
.phead{display:flex;flex-wrap:wrap;gap:10px 18px;align-items:baseline;margin-bottom:8px}
.phead h2{font-size:17px;margin:0}.phead .meta{color:var(--muted);font-size:13px}
.flags{background:var(--warnbg);color:var(--warn);border-radius:8px;padding:4px 10px;font-size:13px;margin:4px 0 8px;display:inline-block}
.cols{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:14px}
#raw:checked ~ .wrap .cols{grid-template-columns:minmax(0,1fr) minmax(0,1fr) minmax(0,1fr)}
.cols .raw{display:none}#raw:checked ~ .wrap .cols .raw{display:block}
#img:not(:checked) ~ .wrap .cols .shot{display:none}
#img:not(:checked) ~ .wrap .cols{grid-template-columns:minmax(0,1fr)}
#img:not(:checked) ~ .wrap #raw:checked ~ .cols{grid-template-columns:1fr 1fr}
.shot img{width:100%;height:auto;border:1px solid var(--line);border-radius:8px;background:#fff}
.shot .none{border:1px dashed var(--line);border-radius:8px;padding:30px 12px;color:var(--muted);text-align:center}
.list{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 10px}
.list h3{font-size:13px;color:var(--muted);margin:0 0 6px;font-weight:600}
.ln{display:flex;gap:8px;padding:3px 0;border-top:1px dashed var(--line);align-items:baseline}.ln:first-of-type{border-top:0}
.ln .n{color:var(--muted);font-size:12px;min-width:2em;text-align:right}
.ln .t{flex:1;white-space:pre-wrap;word-break:break-word}
.ln.title .t{color:var(--title);font-weight:600}
.ln.out .t{color:var(--out);text-decoration:line-through}
.tag{display:inline-block;font-size:11px;padding:0 6px;border-radius:999px;background:var(--tag);color:var(--tagfg);white-space:nowrap}
.tag.out{background:var(--warnbg);color:var(--warn)}
.lv1 .t{padding-left:1.2em}.lv2 .t{padding-left:2.4em}.lv3 .t{padding-left:3.6em}
@media (max-width:1000px){.cols,#raw:checked ~ .wrap .cols{grid-template-columns:1fr}}
"""


def _line_html(ln: Line, no: int) -> str:
    cls = ["ln", f"lv{min(ln.level, 3)}"]
    tags = []
    src = SOURCE_NAME.get(ln.source, ln.source)
    if src:
        tags.append(f'<span class="tag">{html.escape(src)}</span>')
    if ln.removed_by:
        cls.append("out")
        tags.append(f'<span class="tag out">제외: {html.escape(ln.removed_by)}</span>')
    if ln.split_from:
        tags.append('<span class="tag">분할</span>')
    return f'<div class="{" ".join(cls)}"><span class="n">{no}</span><span class="t">{html.escape(ln.text)}</span>{"".join(tags)}</div>'


def _list_html(page: Page, heading: str, cls: str) -> str:
    rows = []
    if page.title:
        rows.append(f'<div class="ln title"><span class="n">제목</span><span class="t">{html.escape(page.title)}</span><span class="tag">{html.escape(page.title_source or "")}</span></div>')
    n = 0
    for ln in page.lines:
        if not ln.text.strip():
            continue
        n += 1
        rows.append(_line_html(ln, n))
    if not rows:
        rows.append('<div class="ln"><span class="n"></span><span class="t" style="color:var(--muted)">읽은 글이 없습니다.</span></div>')
    return f'<div class="list {cls}"><h3>{html.escape(heading)} · {n}줄</h3>{"".join(rows)}</div>'


def build_parse_view(path: Path, cfg: Config, images: bool = True) -> str:
    from ..pipeline import prepare
    from ..switches import describe
    lay = load_document(path, layout=True)
    raw = load_document(path, layout=False)
    prepare(lay, cfg)        # 현재 설정의 규칙이 어떤 줄을 뺄지 표시용 (분류기는 돌리지 않는다)
    prepare(raw, cfg)
    imgs, img_note = page_images(path, lay.kind, images)
    n_pages = len(lay.pages)
    sum_rows = []
    sections = []
    flagged = 0
    for i in range(n_pages):
        lp, rp = lay.pages[i], raw.pages[i] if i < len(raw.pages) else Page(no=i + 1, title="")
        flags = page_flags(lp, rp)
        flagged += bool(flags)
        nl = sum(1 for l in lp.lines if l.text.strip())
        nr = sum(1 for l in rp.lines if l.text.strip())
        nt = sum(1 for l in lp.lines if l.source == "table")
        nd = sum(1 for l in lp.lines if l.source == "diagram")
        n_out = sum(1 for l in lp.lines if l.removed_by and l.text.strip())
        sum_rows.append(f'<tr><td><a href="#p{lp.no}">{lp.no}</a></td><td>{html.escape(lp.title[:60])}</td><td>{html.escape(lp.title_source or "")}</td>'
                        f'<td>{nl}</td><td>{nr}</td><td>{nt} / {nd}</td><td>{n_out}</td><td>{html.escape(lp.excluded_reason or "판정")}</td>'
                        f'<td class="flag">{html.escape("; ".join(flags))}</td></tr>')
        shot = (f'<img src="{imgs[i]}" alt="{lp.no}쪽" loading="lazy">' if imgs and i < len(imgs) and imgs[i]
                else f'<div class="none">{html.escape(img_note or "쪽 그림 없음")}</div>')
        meta = f"제목 출처 {lp.title_source or '없음'} · 관련성 {lp.relevance} · 가중치 {lp.weight:.2f}" + (f" · {lp.excluded_reason}" if lp.excluded_reason else "")
        sections.append(
            f'<section class="page" id="p{lp.no}"><div class="phead"><h2>{lp.no}쪽</h2><span class="meta">{html.escape(meta)}</span></div>'
            + (f'<div class="flags">⚠ {html.escape(" · ".join(flags))}</div>' if flags else "")
            + f'<div class="cols"><div class="shot">{shot}</div>{_list_html(lp, "레이아웃 분석이 읽은 줄", "lay")}{_list_html(rp, "원시 읽기가 읽은 줄", "raw")}</div></section>')
    notes = [*lay.notes, *[n for n in raw.notes if n not in lay.notes]]
    intro = (f'<div class="intro"><p><b>보는 법.</b> 쪽마다 왼쪽은 원본 쪽 그림, 오른쪽은 <b>레이아웃 분석</b>이 읽어 낸 줄이다(파란 글은 제목, 표·도형은 꼬리표, 회색 취소선은 현재 설정의 규칙이 뺄 줄과 그 사유). '
             f'위의 <b>원시 읽기도 보기</b>를 켜면 분석 없이 읽은 줄이 한 칸 더 나와 레이아웃 분석이 무엇을 합치고 나눴는지 비교할 수 있다. '
             f'아래 표의 ⚠ 표시 쪽부터 보면 된다. 분류기는 돌리지 않았다.</p>'
             f'<p><b>현재 설정.</b> 스위치 {html.escape(describe(cfg))}. 리더 판 layout-2, 프로그램 {__version__}.</p>'
             + ("<ul>" + "".join(f"<li>{html.escape(n)}</li>" for n in notes) + "</ul>" if notes else "")
             + (f'<p class="sub">{html.escape(img_note)}</p>' if img_note else "") + "</div>")
    table = ('<table class="sum"><thead><tr><th>쪽</th><th>제목 (레이아웃 분석)</th><th>제목 출처</th><th>레이아웃 줄</th><th>원시 줄</th><th>표 / 도형</th><th>규칙이 뺄 줄</th><th>상태</th><th>점검</th></tr></thead>'
             f'<tbody>{"".join(sum_rows)}</tbody></table>')
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>파싱 점검: {html.escape(path.name)}</title><style>{CSS}</style></head><body>
<input type="checkbox" id="img" checked hidden><input type="checkbox" id="raw" hidden>
<div class="wrap"><h1>파싱 점검 — {html.escape(path.name)}</h1><p class="sub">{n_pages}쪽 · 점검 표시 {flagged}쪽 · {html.escape(str(path))}</p>
<div class="tools"><label><input type="checkbox" onclick="document.getElementById('img').checked=this.checked" checked> 쪽 그림 보기</label>
<label><input type="checkbox" onclick="document.getElementById('raw').checked=this.checked"> 원시 읽기도 보기</label></div>
{intro}{table}{"".join(sections)}</div></body></html>"""


def view_name(path: Path, with_ext: bool = False) -> str:
    """결과 파일 이름. 같은 이름의 PDF 와 PPTX 가 함께 있으면 확장자를 넣어 구분한다."""
    stem = f"{path.stem}_{path.suffix.lstrip('.').lower()}" if with_ext else path.stem
    return f"{stem}_파싱점검.html"


def write_parse_view(path: Path, cfg: Config, out: Path | None = None, images: bool = True, with_ext: bool = False) -> Path:
    path = Path(path)
    out = out or path.with_name(view_name(path, with_ext))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_parse_view(path, cfg, images), encoding="utf-8")
    return out
