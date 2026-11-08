"""비교 도구: 문장 맞추기, 결과 기록(Excel 왕복), 두 실행 비교, 골드 지표, 분류기 비교, 사다리."""
from pathlib import Path

from openpyxl import load_workbook

from ip_finder.compare import (KIND_ORDER, Step, compare_classifiers, compare_records, default_ladder, gold_metrics, ladder_markdown,
                               load_ladder, load_record, load_records, match_texts, norm_key, pair_records, record_from_result, run_ladder,
                               step_config, write_classifier_compare, write_ladder, write_runs_compare, runs_markdown, classifiers_markdown)
from ip_finder.compare.records import KIND_ENTER, KIND_GONE, KIND_LEAVE, KIND_MERGED, KIND_NEW, KIND_SPLIT, KIND_STATUS, RunRecord, Unit
from ip_finder.config import Config
from ip_finder.eval import make_gold_sheet
from ip_finder.goldmap import load_gold
from ip_finder.pipeline import extract
from ip_finder.post import STATUS_CLF_OUT, STATUS_PREP_OUT, STATUS_REVIEW
from ip_finder.switches import SWITCHES


def test_match_texts_three_levels():
    a = ["접착제를 저탄성 실리콘계로", "변경하여 응력 저감", "조립 수율 92.1% 향상", "대외비", "삭제될 문장"]
    b = ["접착제를 저탄성 실리콘계로 변경하여 응력 저감", "조립 수율 92.1 % 향상", "대외비", "완전히 새 문장", "조립 수율 92.1% 향상이 확인됨 추가"]
    m = match_texts(a, b, [1] * 5, [1] * 5)
    kinds = m.kind_of()
    assert kinds[(2, 1)] == "동일" and kinds[(3, 2)] == "동일"                 # 공백 차이는 동일
    assert kinds[(0, 0)] == "포함" and kinds[(1, 0)] == "포함"                 # 두 줄이 한 문단에 포함(합쳐짐)
    assert m.unmatched_a == [4] and 3 in m.unmatched_b
    m2 = match_texts(["접착제를 저탄성 실리콘계로 변경하여 응력 저감"], ["접착제를 저탄성 실리콘계로", "변경하여 응력 저감"], [1], [1, 1])
    assert sorted(m2.pairs) == [(0, 0, "포함"), (0, 1, "포함")]                   # 한 문장이 두 줄로 나뉨
    m3 = match_texts(["냉각 유로를 이중 구조로 변경하여 열 분산"], ["냉각 유로를 이중 구조로 바꾸어 열 분산"], [2], [2])
    assert m3.pairs == [(0, 0, "유사")]
    assert match_texts(["같은 글"], ["같은 글"], [1], [2]).pairs == [(0, 0, "동일")]  # 동일은 쪽이 달라도
    assert norm_key(" 접착제  변경 ") == "접착제변경"


def _unit(text, status=STATUS_REVIEW, grade="A", score=0.9, page=1):
    return Unit(page, 1, text, status, grade, score, 1.0, 0.8)


def test_compare_records_kinds():
    a = RunRecord("r.pdf", "", [_unit("가 문장 하나"), _unit("나 문장 둘", STATUS_CLF_OUT, "X"), _unit("다 문장 셋"), _unit("라 사라짐"),
                                 _unit("마 앞부분의 긴 줄 내용", STATUS_REVIEW), _unit("마 뒷부분의 긴 줄 내용", STATUS_REVIEW)], {"rule_short_line": False})
    b = RunRecord("r.pdf", "", [_unit("가 문장 하나", STATUS_PREP_OUT, ""), _unit("나 문장 둘", STATUS_REVIEW, "B"), _unit("다 문장 셋", STATUS_REVIEW, "B"),
                                 _unit("바 새로움"), _unit("마 앞부분의 긴 줄 내용 마 뒷부분의 긴 줄 내용")], {"rule_short_line": True})
    d = compare_records(a, b)
    c = d.counts()
    assert c[KIND_LEAVE] == 1 and c[KIND_ENTER] == 1 and c["등급 변경"] == 1 and c[KIND_GONE] == 1 and c[KIND_NEW] == 1 and c[KIND_MERGED] == 2
    assert any("짧은 줄 제외" in s for s in d.settings_diff)
    rows = d.summary_rows()
    assert rows[0][0] == STATUS_REVIEW and rows[0][1] == 5 and rows[0][2] == 4
    assert [ch["kind"] for ch in d.changes] == sorted([ch["kind"] for ch in d.changes], key=KIND_ORDER.index)
    md = runs_markdown([d], "A", "B")
    assert "검토 목록 진입" in md and "| 검토 목록 | 5 | 4 | -1 |" in md


def test_record_roundtrip_through_excel(sample_dir, cfg_all, fake_embedder, tmp_path):
    out, res = extract(sample_dir / "sample_report.pptx", cfg_all, tmp_path, embedder=fake_embedder)
    mem = record_from_result(res, cfg_all, out)
    disk = load_record(out)
    assert disk.name == "sample_report.pptx" and disk.pages == 12 and len(disk.units) == len(mem.units)
    assert dict(disk.by_status()) == dict(mem.by_status()) and disk.settings["rule_short_line"] in (True, "True")
    assert [u.text for u in disk.review()] == [u.text for u in mem.review()]
    assert load_records(tmp_path)[0].path == str(out)
    d = compare_records(mem, disk)
    assert d.counts()["total"] if False else sum(d.counts().values()) == 0        # 같은 결과 → 변화 없음


def test_gold_metrics_with_matching(sample_dir, cfg, fake_embedder, tmp_path):
    gold = make_gold_sheet(sample_dir / "sample_report.pptx", cfg, tmp_path / "g.xlsx", embedder=fake_embedder)
    rows = load_gold(gold)
    out, res = extract(sample_dir / "sample_report.pptx", cfg, tmp_path, embedder=fake_embedder, use_gold=False)
    rec = record_from_result(res, cfg, out)
    m = gold_metrics(rec, rows)
    assert m["gold_rows"] == len(rows) and m["matched"] == len(rows) and m["recall"] == 1.0 and m["precision"] == 1.0 and m["review_unscored"] == 0
    cfg.layout_analysis = True                                                  # 문장 단위가 달라져도 포함·유사로 맞춘다
    out2, res2 = extract(sample_dir / "sample_report.pptx", cfg, tmp_path / "l", embedder=fake_embedder, use_gold=False)
    m2 = gold_metrics(record_from_result(res2, cfg, out2), rows)
    assert m2["matched"] >= 0.8 * len(rows) and m2["recall"] is not None


def test_compare_classifiers_on_fake_gold(sample_dir, cfg, fake_embedder, tmp_path):
    gold = make_gold_sheet(sample_dir / "sample_report.pptx", cfg, tmp_path / "g.xlsx", embedder=fake_embedder)
    rows = load_gold(gold)
    result = compare_classifiers(rows, cfg, fake_embedder, k=3, repeats=2)
    reps = {r.name: r for r in result["reports"]}
    assert set(reps) == {"proto", "knn", "centroid", "softmax", "ovr", "cue", "ngram"}
    assert reps["proto"].accuracy == 1.0 and not reps["proto"].trainable and reps["proto"].acc_std is None
    assert all(r.accuracy is not None and len(r.preds) == len(rows) for r in reps.values() if not r.skipped)
    assert len(reps["knn"].repeat_acc) == 2 and reps["knn"].acc_std is not None
    out = write_classifier_compare(result, tmp_path / "cmp.xlsx")
    wb = load_workbook(str(out))
    assert wb.sheetnames == ["요약", "등급별", "혼동 행렬", "문장별", "불일치", "실행 정보"] and wb["요약"].max_row >= 8
    md = classifiers_markdown(result)
    assert "| 원형 문장 코사인 (제로샷) |" in md
    skipped = compare_classifiers(rows, cfg, None, ["proto", "cue"])
    assert skipped["reports"][0].skipped and skipped["reports"][1].accuracy is not None   # 임베더 없음 → proto 건너뜀, cue 는 동작


def test_ladder_cumulative_and_single(sample_dir, cfg, fake_embedder, tmp_path):
    gold = make_gold_sheet(sample_dir / "sample_report.pptx", cfg, tmp_path / "g.xlsx", embedder=fake_embedder)
    rows = load_gold(gold)
    ladder = default_ladder(["layout", "short_line", "repeated"])
    res = run_ladder([sample_dir / "sample_report.pptx", sample_dir / "sample_report.pdf"], cfg, ladder, tmp_path / "lad", rows,
                     embedders={"fake-embed": fake_embedder})
    assert [s.title for s in res.steps] == ["기준선", "1. 레이아웃 분석", "2. 짧은 줄 제외", "3. 반복·고정 문구 제외"]
    assert len(res.diffs) == 3 and res.diffs[2][0] is res.steps[2]                # 누적: 직전 칸과 비교
    assert res.steps[0].cfg.layout_analysis is False and res.steps[1].cfg.layout_analysis is True and res.steps[2].cfg.rule_short_line is True
    assert res.steps[2].totals()[STATUS_PREP_OUT] > 0 and res.gold_used and res.steps[0].gold["recall"] is not None
    assert all(s.cfg.use_gold is False and s.cfg.history_path == "" for s in res.steps)
    assert sorted(p.name for p in (tmp_path / "lad").iterdir()) == ["step-00-baseline", "step-01-layout", "step-02-short_line", "step-03-repeated"]
    assert len(list((tmp_path / "lad" / "step-01-layout").glob("*_검토후보.xlsx"))) == 2
    out = write_ladder(res, tmp_path / "lad" / "사다리.xlsx")
    wb = load_workbook(str(out))
    assert wb.sheetnames == ["사다리 요약", "칸별 변화", "변경 종류별", "파일별", "칸 설정"] and wb["사다리 요약"].max_row >= 5
    md = ladder_markdown(res)
    assert "| 기준선 |" in md and "3. 반복·고정 문구 제외" in md
    single = default_ladder(["short_line", "repeated"], mode="single")
    res2 = run_ladder([sample_dir / "sample_report.pdf"], cfg, single, tmp_path / "single", None, embedders={"fake-embed": fake_embedder})
    assert res2.diffs[1][0] is res2.steps[0] and res2.steps[2].cfg.rule_short_line is False   # 단독: 기준선과 비교, 다른 칸은 끔
    assert not res2.gold_used


def test_ladder_toml_and_arbitrary_settings(tmp_path):
    f = tmp_path / "l.toml"
    f.write_text('name = "clf"\nmode = "single"\n[[step]]\nname = "layout"\n[[step]]\nlabel = "k-NN"\nset = { classifier = "knn", knn_k = 3 }\n', encoding="utf-8")
    lad = load_ladder(f)
    assert lad.name == "clf" and lad.mode == "single" and [s.label for s in lad.steps] == ["레이아웃 분석", "k-NN"]
    base = Config()
    c1 = step_config(base, lad, 1)
    assert c1.classifier == "knn" and c1.knn_k == 3 and c1.layout_analysis is False and c1.use_gold is False
    assert step_config(base, lad, -1).classifier == "proto"
    import pytest
    with pytest.raises(ValueError):
        Step("x", "x", {"no_such_field": 1}).apply(base)


def test_write_runs_compare_and_pairing(sample_dir, cfg, cfg_all, fake_embedder, tmp_path):
    outs_a = [extract(sample_dir / f, cfg, tmp_path / "a", embedder=fake_embedder, with_ext=True)[0] for f in ("sample_report.pdf", "sample_report.pptx")]
    outs_b = [extract(sample_dir / f, cfg_all, tmp_path / "b", embedder=fake_embedder, with_ext=True)[0] for f in ("sample_report.pdf", "sample_report.pptx")]
    a, b = load_records(tmp_path / "a"), load_records(tmp_path / "b")
    pairs = pair_records(a, b)
    assert len(pairs) == 2 and all(x.name == y.name for x, y in pairs)
    diffs = [compare_records(x, y) for x, y in pairs]
    out = write_runs_compare(diffs, tmp_path / "cmp.xlsx", "기준선", "전부 켬")
    wb = load_workbook(str(out))
    assert wb.sheetnames == ["요약", "설정 차이", "변경 문장", "페이지별", "실행 정보"]
    assert wb["변경 문장"].max_row > 1 and any("스위치" in str(r[1]) for r in wb["설정 차이"].iter_rows(min_row=2, values_only=True))
