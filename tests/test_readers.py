from pptx import Presentation
from pptx.util import Inches, Pt

from ip_finder.readers import load_document


def test_pptx_reader_skips_notes_and_reads_tables(sample_dir):
    doc = load_document(sample_dir / "sample_report.pptx")
    assert doc.kind == "pptx" and len(doc.pages) == 12
    all_text = " ".join(ln.text for p in doc.pages for ln in p.lines)
    assert "십자형" not in all_text              # 발표자 노트는 읽지 않는다
    assert doc.pages[4].title.startswith("개선안 1") and doc.pages[4].title_source == "placeholder"
    table_lines = [ln for ln in doc.pages[7].lines if ln.source == "table"]
    assert table_lines and "개선 전" in table_lines[0].text
    assert doc.pages[6].has_graphics and all("대외비" in ln.text for ln in doc.pages[6].lines)   # 도면 슬라이드: 바닥글만


def test_pdf_reader_titles(sample_dir):
    doc = load_document(sample_dir / "sample_report.pdf")
    assert doc.kind == "pdf" and len(doc.pages) == 12
    assert doc.pages[2].title == "배경 및 문제점" and doc.pages[2].title_source == "font"
    assert any("저탄성" in ln.text for ln in doc.pages[4].lines)
    assert doc.pages[6].has_graphics


def test_pptx_title_by_font_size_when_no_placeholder(tmp_path):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])            # 빈 레이아웃: 제목 플레이스홀더 없음
    small = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(4), Inches(0.5))
    small.text_frame.text = "대외비"
    small.text_frame.paragraphs[0].runs[0].font.size = Pt(9)
    big = slide.shapes.add_textbox(Inches(0.5), Inches(0.9), Inches(8), Inches(0.8))
    big.text_frame.text = "개선안 3: 냉각 유로 이중화"
    big.text_frame.paragraphs[0].runs[0].font.size = Pt(28)
    body = slide.shapes.add_textbox(Inches(0.5), Inches(2.5), Inches(8), Inches(3))
    body.text_frame.text = "냉각 유로를 이중 구조로 변경하여 열을 분산"
    body.text_frame.paragraphs[0].runs[0].font.size = Pt(14)
    p = tmp_path / "t.pptx"
    prs.save(str(p))
    doc = load_document(p)
    pg = doc.pages[0]
    assert pg.title == "개선안 3: 냉각 유로 이중화" and pg.title_source == "font"
    assert [ln.text for ln in pg.lines] == ["대외비", "냉각 유로를 이중 구조로 변경하여 열을 분산"]
