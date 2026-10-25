from openpyxl import load_workbook

from ip_finder.config import Config
from ip_finder.pipeline import extract, find_inputs, output_path


def _rows(ws):
    return [r for r in ws.iter_rows(min_row=2, values_only=True) if r[0] is not None]


def test_extract_pptx_and_pdf(sample_dir, cfg, fake_client, tmp_path):
    for name in ("sample_report.pptx", "sample_report.pdf"):
        out, res = extract(sample_dir / name, cfg, tmp_path, fake_client)
        assert out == output_path(sample_dir / name, tmp_path) and out.exists()
        wb = load_workbook(str(out))
        assert wb.sheetnames == ["검토 목록", "보류", "제외 페이지", "이미지 페이지", "실행 정보"]
        review = _rows(wb["검토 목록"])
        assert review and all(r[3] in ("A", "B", "C", "D") for r in review)
        assert [r[0] for r in review] == list(range(1, len(review) + 1))
        pages = [r[2] for r in review]
        assert pages == sorted(pages)                        # 페이지 순서
        assert any(r[1] == "개선안" and r[3] == "A" for r in review)
        assert all(r[5] for r in review)                      # 논의 포인트 템플릿
        excluded = {r[0]: r[2] for r in _rows(wb["제외 페이지"])}
        assert 2 in excluded and "목차" in excluded[2]
        assert [r[0] for r in _rows(wb["이미지 페이지"])] == [7]
        info = dict(_rows(wb["실행 정보"]))
        assert info["모델"] == "fake-model" and info["라벨링 페이지"] == 7
        assert res.info.llm_calls == 7 and res.info.cache_hits == 0


def test_title_fix_and_safety_net_in_pipeline(sample_dir, cfg, fake_client, tmp_path):
    out, res = extract(sample_dir / "sample_report.pptx", cfg, tmp_path, fake_client)
    fixed = [ll for ll in res.labeled if "보정(A→C)" in ll.notes]
    assert fixed and all(ll.page_title == "원인 분석" for ll in fixed)
    held = [ll for ll in res.labeled if ll.label == "X?"]
    assert any("불량률" in ll.text for ll in held)
    notes_text = " ".join(ll.text for ll in res.labeled)
    assert "십자형" not in notes_text


def test_cache_reuses_labels(sample_dir, fake_client, tmp_path):
    cfg = Config(use_cache=True, cache_path=str(tmp_path / "cache.sqlite"))
    _, first = extract(sample_dir / "sample_report.pptx", cfg, tmp_path, fake_client)
    _, second = extract(sample_dir / "sample_report.pptx", cfg, tmp_path, fake_client)
    assert first.info.llm_calls == 7 and first.info.cache_hits == 0
    assert second.info.llm_calls == 0 and second.info.cache_hits == 7
    assert [ll.label for ll in first.labeled] == [ll.label for ll in second.labeled]
    raw = (tmp_path / "cache.sqlite").read_bytes()
    assert "저탄성".encode("utf-8") not in raw                # 캐시에 원문 미저장


def test_find_inputs(sample_dir):
    files = find_inputs([sample_dir])
    assert {f.suffix for f in files} == {".pdf", ".pptx"}
