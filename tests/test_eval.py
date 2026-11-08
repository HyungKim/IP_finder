from pathlib import Path

import pytest
from openpyxl import load_workbook

from ip_finder.config import Config
from ip_finder.eval import GOLD_HEADERS, evaluate, import_feedback, interpret, make_gold_sheet, train_classifier
from ip_finder.goldmap import GoldMap, find_gold_files, load_gold
from ip_finder.history import History
from ip_finder.pipeline import extract, run_file
from ip_finder.post import in_review_list


def test_gold_sheet_and_scoring(sample_dir, cfg, fake_embedder, tmp_path):
    gold = make_gold_sheet(sample_dir / "sample_report.pptx", cfg, tmp_path / "g.xlsx", embedder=fake_embedder)
    wb = load_workbook(str(gold))
    assert wb.sheetnames == ["라벨링", "안내", "메타"]
    assert [c.value for c in wb["라벨링"][1]] == GOLD_HEADERS
    rows = [r for r in wb["라벨링"].iter_rows(min_row=2, values_only=True) if r[0]]
    assert rows and all(r[12] in ("A", "B", "C", "D", "X") for r in rows) and all(isinstance(r[9], float) for r in rows)   # 확신 열
    meta = dict(r[:2] for r in wb["메타"].iter_rows(values_only=True))
    assert meta["1차 분류기"].startswith("원형 문장") and "layout=끔" in meta["스위치"]
    stored = evaluate(gold, cfg, rerun=False)
    assert stored["raw"]["accuracy"] == 1.0
    rerun = evaluate(gold, cfg, rerun=True, embedder=fake_embedder)
    assert rerun["rows"] == len(rows) and rerun["raw"]["accuracy"] == 1.0 and rerun["candidates"]["recall"] == 1.0
    assert set(rerun["final"]["per_grade"]) == {"A", "B", "C", "D", "X"} and len(rerun["sweep"]) == 6


@pytest.mark.parametrize("name", ["knn", "centroid", "softmax", "ovr", "ngram"])
def test_train_each_classifier_and_use_it(name, sample_dir, cfg, fake_embedder, tmp_path):
    gold = make_gold_sheet(sample_dir / "sample_report.pptx", cfg, tmp_path / "g.xlsx", embedder=fake_embedder)
    stats = train_classifier([gold], cfg, None, fake_embedder, name=name)
    out = cfg.classifier_file(name)
    assert out.exists() and stats["classifier"] == name and stats["n"] >= 20 and 0.0 <= stats["cv_accuracy"] <= 1.0
    cfg.classifier = name
    _, res = extract(sample_dir / "sample_report.pptx", cfg, tmp_path, embedder=fake_embedder)
    assert res.info.classifier_name == name and "학습" in res.info.classifier
    rep = evaluate(gold, cfg, rerun=True, embedder=fake_embedder)
    assert rep["rows"] == stats["n"]


def test_train_rejects_non_trainable(sample_dir, cfg, fake_embedder, tmp_path):
    gold = make_gold_sheet(sample_dir / "sample_report.pptx", cfg, tmp_path / "g.xlsx", embedder=fake_embedder)
    with pytest.raises(ValueError):
        train_classifier([gold], cfg, None, fake_embedder, name="proto")


def test_interpret_feedback_values():
    assert interpret("O", "A") == "A" and interpret("맞음", "X?") == "X" and interpret("X", "A") == "X"
    assert interpret("c", "A") == "C" and interpret("", "A") is None and interpret("??", "A") is None


def test_feedback_import_builds_and_merges_gold(sample_dir, cfg, fake_embedder, tmp_path):
    out, res = extract(sample_dir / "sample_report.pptx", cfg, tmp_path, embedder=fake_embedder)
    from ip_finder.report.xlsx import FEEDBACK_COL as FC
    wb = load_workbook(str(out))
    ws = wb["검토 목록"]
    ws.cell(row=2, column=FC).value = "O"
    ws.cell(row=3, column=FC).value = "X"
    ws.cell(row=4, column=FC).value = "c"
    ws.cell(row=4, column=FC + 1).value = "원인 설명임"
    ws.cell(row=5, column=FC).value = "???"
    wb.save(str(out))
    h = History(cfg.history_dir())
    rec = import_feedback(out, history=h)
    gold = Path(rec["gold"])
    assert gold.name == "sample_report_gold.xlsx" and rec["skipped"] == 1 and rec["added"] == rec["feedback_rows"] == 3
    rows = load_gold(gold)
    first = [r for r in res.labeled if in_review_list(r)]
    by_text = {r["문장"]: r for r in rows}
    assert by_text[first[0].text]["정답"] == first[0].label and by_text[first[1].text]["정답"] == "X" and by_text[first[2].text]["정답"] == "C"
    assert by_text[first[2].text]["메모"] == "원인 설명임" and len(h.feedback_log()) == 1
    wb = load_workbook(str(out))
    wb["검토 목록"].cell(row=2, column=FC).value = "B"
    wb["검토 목록"].cell(row=6, column=FC).value = "O"
    wb.save(str(out))
    rec2 = import_feedback(out, history=h)
    assert rec2["updated"] == 3 and rec2["added"] == 1 and {r["문장"]: r for r in load_gold(gold)}[first[0].text]["정답"] == "B"


def test_gold_override_in_new_runs(sample_dir, cfg, fake_embedder, tmp_path):
    out, res = extract(sample_dir / "sample_report.pptx", cfg, tmp_path, embedder=fake_embedder)
    from ip_finder.report.xlsx import FEEDBACK_COL as FC
    wb = load_workbook(str(out))
    wb["검토 목록"].cell(row=2, column=FC).value = "X"
    wb["검토 목록"].cell(row=3, column=FC).value = "D"
    wb.save(str(out))
    rec = import_feedback(out, gold_dir=cfg.gold_dir(), history=History(cfg.history_dir()))
    assert Path(rec["gold"]).parent == tmp_path / "gold" and cfg.gold_files() == [Path(rec["gold"])]
    listed = [ll for ll in res.labeled if in_review_list(ll)]
    gm = GoldMap.load(cfg.gold_paths, cfg.base_dir)
    assert gm.get(listed[0].text) == "X" and gm.get(listed[1].text) == "D" and len(gm) == 2
    out2, res2 = extract(sample_dir / "sample_report.pptx", cfg, tmp_path, embedder=fake_embedder)
    by_key = {ll.key: ll for ll in res2.labeled}
    a, b = by_key[listed[0].key], by_key[listed[1].key]
    assert a.label == "X" and a.source == "gold" and "골드 반영(" in a.notes[-1] and a.stage_out == 2
    assert b.label == "D" and b.source == "gold" and b.score == 1.0 and b.stage_out == 2
    assert res2.info.gold_lines >= 2 and res2.info.gold_changed >= 2 and any("골드" in s for s in res2.info.settings_diff)   # 기준선은 반복 꼬리말도 판정하므로 같은 문장이 여러 쪽에 있을 수 있다
    wb2 = load_workbook(str(out2))
    assert any(r[5] == listed[0].text and r[10] == "골드" for r in wb2["후처리 제외"].iter_rows(min_row=2, values_only=True))
    cfg.use_gold = False
    _, res3 = extract(sample_dir / "sample_report.pptx", cfg, tmp_path, embedder=fake_embedder)
    assert {ll.key: ll for ll in res3.labeled}[listed[0].key].label == listed[0].label
    cfg.use_gold = True
    rep = evaluate(Path(rec["gold"]), cfg, rerun=True, embedder=fake_embedder)
    assert rep["raw"]["accuracy"] < 1.0                                         # 채점에는 골드 반영 없음
    res4 = run_file(sample_dir / "sample_report.pptx", cfg, embedder=fake_embedder, use_gold=False)
    assert res4.info.gold_lines == 0


def test_gold_map_conflicts_latest_wins(tmp_path):
    import os, time
    from ip_finder.eval import write_gold_workbook
    d = tmp_path / "g"
    d.mkdir()
    row = lambda n, text, ans: [n, "r.pptx", 3, "제목", n, text, "A", "A", "분류기", "", 1.0, 1.0, ans, ""]
    write_gold_workbook(d / "old_gold.xlsx", [row(1, "냉각 유로를  이중 구조로 변경", "A"), row(2, "일정 조정", "X")], [])
    write_gold_workbook(d / "new_gold.xlsx", [row(1, "냉각 유로를 이중 구조로 변경", "B")], [])
    t = time.time()
    os.utime(d / "old_gold.xlsx", (t - 100, t - 100))
    os.utime(d / "new_gold.xlsx", (t, t))
    assert [p.name for p in find_gold_files([d])] == ["new_gold.xlsx", "old_gold.xlsx"]
    gm = GoldMap.load([d])
    assert gm.get("냉각 유로를 이중 구조로 변경") == "B" and gm.get("  일정   조정 ") == "X" and gm.conflicts == 1
