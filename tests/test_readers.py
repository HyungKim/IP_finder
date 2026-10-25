from ip_finder.readers import load_document


def test_pptx_reader_skips_notes_and_reads_tables(sample_dir):
    doc = load_document(sample_dir / "sample_report.pptx")
    assert doc.kind == "pptx" and len(doc.pages) == 12
    all_text = " ".join(ln.text for p in doc.pages for ln in p.lines)
    assert "십자형" not in all_text              # 발표자 노트는 읽지 않는다
    assert doc.pages[4].title.startswith("개선안 1")
    table_lines = [ln for ln in doc.pages[7].lines if ln.source == "table"]
    assert table_lines and "개선 전" in table_lines[0].text
    assert doc.pages[6].has_graphics and all("대외비" in ln.text for ln in doc.pages[6].lines)   # 도면 슬라이드: 바닥글만


def test_pdf_reader_titles(sample_dir):
    doc = load_document(sample_dir / "sample_report.pdf")
    assert doc.kind == "pdf" and len(doc.pages) == 12
    assert doc.pages[2].title == "배경 및 문제점"
    assert any("저탄성" in ln.text for ln in doc.pages[4].lines)
    assert doc.pages[6].has_graphics
