"""파싱 점검 HTML: 쪽마다 그림(PDF)과 읽은 줄(레이아웃/원시), 규칙이 뺄 줄, 점검 표시."""
from ip_finder.cli import main
from ip_finder.report.parse_view import build_parse_view, page_flags, write_parse_view
from ip_finder.models import Line, Page


def test_parse_view_pdf_has_images_and_both_readings(sample_dir, cfg_all, tmp_path):
    out = write_parse_view(sample_dir / "sample_report.pdf", cfg_all, tmp_path / "v.html")
    s = out.read_text(encoding="utf-8")
    assert s.count('<section class="page"') == 12 and 'id="p5"' in s
    assert s.count("data:image/") == 12                                       # PDF 는 쪽마다 그림
    assert "레이아웃 분석이 읽은 줄" in s and "원시 읽기가 읽은 줄" in s and "개선안 1" in s
    assert "제외: 반복 문구" in s                                                # 전부 켠 설정이 뺄 줄에 사유
    assert "전부 켬" in s


def test_parse_view_pptx_without_images_and_baseline(sample_dir, cfg, tmp_path):
    s = build_parse_view(sample_dir / "sample_report.pptx", cfg, images=True)
    assert "data:image/" not in s and "PowerPoint" in s                        # 맥에서는 PPTX 그림 없음 → 안내
    assert "제외:" not in s and "기준선" in s                                      # 기준선 설정: 뺄 줄 없음
    assert s.count('<section class="page"') == 12 and '<span class="tag">표</span>' in s   # PPTX 표 셀 꼬리표


def test_page_flags():
    lay = Page(no=1, title="", lines=[], has_graphics=True)
    raw = Page(no=1, title="", lines=[])
    assert page_flags(lay, raw) == ["글 없음 (그림·도형 있음)"]
    lay = Page(no=2, title="제목", title_source="font", lines=[Line(0, "하나")])
    raw = Page(no=2, title="제목", lines=[Line(0, "하나"), Line(0, "둘"), Line(0, "셋")])
    assert page_flags(lay, raw) == ["두 읽기의 줄 수 차이 큼 (1 / 3)"]
    lay = Page(no=3, title="", title_source="없음", lines=[], excluded_reason="표지")
    assert page_flags(lay, Page(no=3, title="", lines=[Line(0, "글")])) == ["레이아웃 분석이 줄을 하나도 못 읽음", "제목 없음", "현재 설정에서 쪽 제외: 표지"]


def test_cli_parse(sample_dir, tmp_path, capsys):
    assert main(["parse", str(sample_dir / "sample_report.pdf"), "--out-dir", str(tmp_path), "--no-images"]) == 0
    out = tmp_path / "sample_report_파싱점검.html"
    assert out.exists() and "그림 생략" in out.read_text(encoding="utf-8") and "브라우저로 열어" in capsys.readouterr().out
    assert main(["parse", str(sample_dir), "--out-dir", str(tmp_path / "both"), "--no-images"]) == 0
    assert sorted(p.name for p in (tmp_path / "both").iterdir()) == ["sample_report_pdf_파싱점검.html", "sample_report_pptx_파싱점검.html"]   # 같은 이름은 확장자로 구분
