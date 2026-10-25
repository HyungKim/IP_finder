from openpyxl import load_workbook

from ip_finder.config import Config
from ip_finder.pipeline import extract, find_inputs, output_path
from tests.conftest import FakeEmbedder


def _rows(ws):
    return [r for r in ws.iter_rows(min_row=2, values_only=True) if r[0] is not None]


def test_extract_pptx_and_pdf_llm_mode(sample_dir, cfg, fake_client, tmp_path):
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
        assert all(r[5] for r in review) and all(r[6] == "LLM" for r in review)
        excluded = {r[0]: r[2] for r in _rows(wb["제외 페이지"])}
        assert 2 in excluded and "목차" in excluded[2]
        assert [r[0] for r in _rows(wb["이미지 페이지"])] == [7]
        info = dict(_rows(wb["실행 정보"]))
        assert info["LLM 모델"] == "fake-model" and info["판정 모드"] == "llm" and info["판정 페이지" if "판정 페이지" in info else "라벨링 페이지"] == 7
        assert res.info.llm_calls == 7 and res.info.cache_hits == 0 and res.info.llm_lines == len(res.labeled)
        assert any("(페이지 유형:" in u for u in fake_client.inputs)   # 힌트가 들어감


def test_title_fix_and_safety_net_in_pipeline(sample_dir, cfg, fake_client, tmp_path):
    out, res = extract(sample_dir / "sample_report.pptx", cfg, tmp_path, fake_client)
    fixed = [ll for ll in res.labeled if "보정(A→C)" in ll.notes]
    assert fixed and all(ll.page_title == "원인 분석" for ll in fixed)
    held = [ll for ll in res.labeled if ll.label == "X?"]
    assert any("불량률" in ll.text for ll in held)
    assert "십자형" not in " ".join(ll.text for ll in res.labeled)


def test_fast_mode_uses_only_classifier(sample_dir, cfg_hybrid, fake_client, fake_embedder, tmp_path):
    cfg_hybrid.mode = "fast"
    out, res = extract(sample_dir / "sample_report.pptx", cfg_hybrid, tmp_path, fake_client, embedder=fake_embedder)
    assert res.info.mode == "fast" and fake_client.calls == 0 and res.info.llm_calls == 0
    assert res.info.clf_lines == len(res.labeled) and all(ll.source == "clf" for ll in res.labeled)
    assert all(ll.clf_conf is not None for ll in res.labeled)
    info = dict(_rows(load_workbook(str(out))["실행 정보"]))
    assert info["판정 모드"] == "fast" and info["분류기"].startswith("제로샷")


def test_hybrid_mode_sends_only_ambiguous_lines(sample_dir, cfg_hybrid, fake_client, fake_embedder, tmp_path):
    cfg_hybrid.confidence_threshold = 1.0        # 전부 애매 → 전부 LLM, 유형별 묶음
    _, res = extract(sample_dir / "sample_report.pptx", cfg_hybrid, tmp_path, fake_client, embedder=fake_embedder)
    assert res.info.mode == "hybrid" and res.info.llm_lines == len(res.labeled) and res.info.clf_lines == 0
    assert 1 <= res.info.llm_calls <= 5          # 페이지 유형 수 이하
    assert all("분류기" in " ".join(ll.notes) for ll in res.labeled)

    fake_client2 = type(fake_client)()
    cfg_hybrid.confidence_threshold = 0.0        # 전부 확신 → LLM 없음
    _, res2 = extract(sample_dir / "sample_report.pptx", cfg_hybrid, tmp_path, fake_client2, embedder=FakeEmbedder())
    assert fake_client2.calls == 0 and res2.info.clf_lines == len(res2.labeled)

    fake_client3 = type(fake_client)()
    cfg_hybrid.confidence_threshold = None       # 기본 임계값 → 일부만 LLM
    out, res3 = extract(sample_dir / "sample_report.pptx", cfg_hybrid, tmp_path, fake_client3, embedder=FakeEmbedder())
    assert res3.info.clf_lines + res3.info.llm_lines == len(res3.labeled)
    judged = {r[6] for r in _rows(load_workbook(str(out))["검토 목록"])}
    assert judged <= {"분류기", "LLM"}


def test_hybrid_falls_back_to_llm_without_embedder(sample_dir, cfg_hybrid, fake_client, tmp_path):
    _, res = extract(sample_dir / "sample_report.pptx", cfg_hybrid, tmp_path, fake_client, embedder=FakeEmbedder(available=False))
    assert res.info.mode == "llm" and res.info.warnings and "llm 모드로 대체" in res.info.warnings[0]
    assert fake_client.calls == 7


def test_cache_reuses_labels_and_vectors(sample_dir, fake_client, fake_embedder, tmp_path):
    cfg = Config(use_cache=True, cache_path=str(tmp_path / "cache.sqlite"), mode="llm")
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
