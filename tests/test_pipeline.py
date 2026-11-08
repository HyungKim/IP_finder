from openpyxl import load_workbook

from ip_finder.config import Config
from ip_finder.pipeline import extract, find_inputs, output_path, run_file
from ip_finder.post import STATUS_CLF_OUT, STATUS_REVIEW, in_review_list, status_of
from ip_finder.report.xlsx import LINE_HEADERS, SETTING_PREFIX
from ip_finder.switches import SWITCHES
from tests.conftest import FakeEmbedder


def test_baseline_runs_classifier_on_every_line(sample_dir, cfg, fake_embedder, tmp_path):
    out, res = extract(sample_dir / "sample_report.pptx", cfg, tmp_path, embedder=fake_embedder)
    assert out.exists() and res.info.reader == "raw" and res.info.classifier_name == "proto"
    assert res.removed == {} and res.info.pages_excluded == 0                   # 기준선: 아무 규칙도 없음
    assert all(ll.source == "clf" and ll.clf_conf is not None for ll in res.labeled)
    assert {status_of(ll) for ll in res.labeled} <= {STATUS_REVIEW, STATUS_CLF_OUT}
    assert any(in_review_list(ll) for ll in res.labeled)
    wb = load_workbook(str(out))
    assert wb.sheetnames == ["검토 목록", "보류", "분류기 제외 (참고)", "후처리 제외", "전처리 제외", "페이지", "변경 사항", "제외 페이지", "이미지 페이지", "실행 정보"]
    assert [c.value for c in wb["검토 목록"][1]] == LINE_HEADERS
    info = {r[0]: r[1] for r in wb["실행 정보"].iter_rows(min_row=2, values_only=True) if r and r[0]}
    assert info["읽기 방식"].startswith("원시") and "기준선" in info["스위치"]
    assert all(f"{SETTING_PREFIX}{s.field}" in info for s in SWITCHES)       # compare-runs 가 읽는 설정 행
    assert all(info[f"{SETTING_PREFIX}{s.field}"] in (False, "False", 0) for s in SWITCHES)


def test_all_switches_change_output(sample_dir, cfg_all, fake_embedder, tmp_path):
    out, res = extract(sample_dir / "sample_report.pptx", cfg_all, tmp_path, embedder=fake_embedder)
    assert res.info.reader == "layout" and res.removed["반복 문구"] >= 12 and res.info.pages_excluded >= 3
    wb = load_workbook(str(out))
    prep = [r for r in wb["전처리 제외"].iter_rows(min_row=2, values_only=True) if r[0] not in (None, "")]
    assert prep and {r[1] for r in prep} <= {"전처리 제외", "페이지 제외"} and any(r[2] == "반복 문구" for r in prep)
    titles = [r[1] for r in wb["페이지"].iter_rows(min_row=2, values_only=True)]
    assert any("개선안" in str(t) for t in titles)


def test_each_switch_alone_is_harmless(sample_dir, cfg, fake_embedder):
    """스위치를 하나씩만 켜도 실행이 끝나고, 켠 스위치가 실행 정보에 기록된다."""
    for s in SWITCHES:
        c = Config(**{**cfg.__dict__, s.field: True})
        res = run_file(sample_dir / "sample_report.pdf", c, embedder=fake_embedder)
        assert res.info.switches[s.name] is True and sum(res.info.switches.values()) == 1


def test_classifier_without_embedding(sample_dir, cfg, tmp_path):
    cfg.classifier = "cue"
    out, res = extract(sample_dir / "sample_report.pptx", cfg, tmp_path)         # 임베더 없이 동작
    assert res.info.embed_model == "" and res.info.classifier.startswith("단서어 규칙")
    assert any(in_review_list(ll) for ll in res.labeled)


def test_trained_classifier_file_required(sample_dir, cfg, fake_embedder):
    import pytest
    cfg.classifier = "knn"
    with pytest.raises(FileNotFoundError):
        run_file(sample_dir / "sample_report.pptx", cfg, embedder=fake_embedder)


def test_cache_reuses_vectors(sample_dir, fake_embedder, tmp_path):
    cfg = Config(use_cache=True, cache_path=str(tmp_path / "c.sqlite"), history_path="", embed_model="fake-embed", gold_paths=[str(tmp_path / "gold")])
    from ip_finder.cache import LabelCache
    from ip_finder.classify import OllamaEmbedder
    cache = LabelCache(cfg.cache_file())
    key = LabelCache.key("fake-embed", "embed", "접착제 변경")
    assert cache.get_vec(key) is None
    cache.set_vec(key, [0.1, 0.2])
    assert cache.get_vec(key) == [0.1, 0.2] if False else abs(cache.get_vec(key)[1] - 0.2) < 1e-6
    cache.close()
    assert OllamaEmbedder is not None


def test_find_inputs(sample_dir):
    files = find_inputs([sample_dir])
    assert [f.suffix for f in files] == [".pdf", ".pptx"]
    assert output_path(files[0], with_ext=True).name == "sample_report_pdf_검토후보.xlsx"


def test_page_weight_moves_low_pages_to_hold(sample_dir, cfg, fake_embedder, tmp_path):
    cfg.page_weight_enabled = True
    cfg.low_relevance_patterns = ["개선안"]            # 샘플의 개선안 페이지를 일부러 낮음으로
    _, res = extract(sample_dir / "sample_report.pptx", cfg, tmp_path, embedder=fake_embedder)
    low = [ll for ll in res.labeled if ll.page_weight < 1.0]
    assert low and all(ll.hold_reason.startswith("점수") for ll in low if ll.label in ("A", "B") and ll.stage_out == 0)
    assert res.info.pages_low >= 1


def test_history_diff_between_runs(sample_dir, cfg, fake_embedder, tmp_path):
    _, r1 = extract(sample_dir / "sample_report.pptx", cfg, tmp_path, embedder=fake_embedder)
    assert r1.info.run_id and not r1.info.prev_run_id
    cfg.rule_short_line = True
    out2, r2 = extract(sample_dir / "sample_report.pptx", cfg, tmp_path, embedder=fake_embedder)
    assert r2.info.prev_run_id == r1.info.run_id
    assert any("짧은 줄 제외" in s for s in r2.info.settings_diff)
    assert r2.info.changes.get("gone", 0) > 0                                   # 짧은 줄이 사라짐
    wb = load_workbook(str(out2))
    rows = [r for r in wb["변경 사항"].iter_rows(min_row=2, values_only=True)]
    assert rows[0][0] == "기준" and any(r[0] == "설정" and "짧은 줄" in str(r[3]) for r in rows)
