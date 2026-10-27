from pathlib import Path

from openpyxl import load_workbook

from ip_finder.config import Config
from ip_finder.eval import GOLD_HEADERS, evaluate, import_feedback, interpret, make_gold_sheet, train_classifier
from ip_finder.eval.score import load_gold
from ip_finder.history import History
from ip_finder.pipeline import extract


def test_gold_sheet_and_scoring(sample_dir, cfg, fake_client, tmp_path):
    gold = make_gold_sheet(sample_dir / "sample_report.pptx", cfg, tmp_path / "g.xlsx", fake_client)
    wb = load_workbook(str(gold))
    assert wb.sheetnames == ["라벨링", "안내", "메타"]
    header = [c.value for c in wb["라벨링"][1]]
    assert header == GOLD_HEADERS
    rows = [r for r in wb["라벨링"].iter_rows(min_row=2, values_only=True) if r[0]]
    assert rows and all(r[12] in ("A", "B", "C", "D", "X") for r in rows)   # 정답 열이 모델 라벨로 미리 채워짐
    assert all(isinstance(r[10], (int, float)) and isinstance(r[11], (int, float)) for r in rows)   # 점수·가중치
    stored = evaluate(gold, cfg, rerun=False)
    assert stored["raw"]["accuracy"] == 1.0
    rerun = evaluate(gold, cfg, rerun=True, client=fake_client)
    assert rerun["rows"] == len(rows) and rerun["raw"]["accuracy"] == 1.0
    assert set(rerun["final"]["per_grade"]) == {"A", "B", "C", "D", "X"}
    assert rerun["list"]["precision_nonx"] == 1.0 and 0 < rerun["list"]["recall"] <= 1.0 and len(rerun["sweep"]) == 6
    assert stored["list"]["list"] > 0


def test_train_and_use_classifier(sample_dir, cfg, cfg_cascade, fake_client, fake_embedder, tmp_path):
    gold = make_gold_sheet(sample_dir / "sample_report.pptx", cfg, tmp_path / "g.xlsx", fake_client)
    out = tmp_path / "clf.npz"
    cfg_cascade.embed_model = "fake-embed"
    stats = train_classifier([gold], cfg_cascade, out, fake_embedder)
    assert out.exists() and stats["n"] >= 20 and 0.0 <= stats["cv_accuracy"] <= 1.0 and stats["train_accuracy"] > 0.8
    cfg_cascade.classifier_path = str(out)
    _, res = extract(sample_dir / "sample_report.pptx", cfg_cascade, tmp_path, fake_client, embedder=fake_embedder)
    assert res.info.classifier.startswith("학습")
    rep = evaluate(gold, cfg_cascade, rerun=True, client=fake_client, embedder=fake_embedder)
    assert rep["rows"] == stats["n"] and "cascade" in rep["source"]


def test_interpret_feedback_values():
    assert interpret("O", "A") == "A" and interpret("o", "C") == "C" and interpret("맞음", "X?") == "X"
    assert interpret("X", "A") == "X" and interpret("틀림", "B") == "X"
    assert interpret("c", "A") == "C" and interpret("", "A") is None and interpret("??", "A") is None


def test_feedback_import_builds_and_merges_gold(sample_dir, cfg, fake_client, tmp_path):
    cfg.history_path = str(tmp_path / "hist")
    out, res = extract(sample_dir / "sample_report.pptx", cfg, tmp_path, fake_client)
    from ip_finder.report.xlsx import FEEDBACK_COL as FC
    wb = load_workbook(str(out))
    ws = wb["검토 목록"]
    ws.cell(row=2, column=FC).value = "O"            # 첫 행 맞음
    ws.cell(row=3, column=FC).value = "X"            # 둘째 행 틀림
    ws.cell(row=4, column=FC).value = "c"            # 셋째 행 등급 C
    ws.cell(row=4, column=FC + 1).value = "원인 설명임"
    ws.cell(row=5, column=FC).value = "???"          # 해석 불가 → 건너뜀
    hold = wb["보류"]
    if hold.max_row > 1 and hold.cell(row=2, column=6).value and hold.cell(row=2, column=1).value:
        hold.cell(row=2, column=FC).value = "A"      # 보류 문장을 A로 살림
    wb.save(str(out))
    h = History(cfg.history_dir())
    rec = import_feedback(out, history=h)
    gold = Path(rec["gold"])
    assert gold.name == "sample_report_gold.xlsx" and rec["skipped"] == 1 and rec["added"] == rec["feedback_rows"] >= 3
    rows = load_gold(gold)
    from ip_finder.post import in_review_list
    first = [r for r in res.labeled if in_review_list(r)]
    by_text = {r["문장"]: r for r in rows}
    assert by_text[first[0].text]["정답"] == first[0].label and by_text[first[1].text]["정답"] == "X" and by_text[first[2].text]["정답"] == "C"
    assert by_text[first[2].text]["메모"] == "원인 설명임" and by_text[first[0].text]["제목"] == first[0].page_title
    assert len(h.feedback_log()) == 1 and h.feedback_log()[0]["corrections"]
    # 두 번째 가져오기: 같은 행은 갱신, 새 행은 추가
    wb = load_workbook(str(out))
    wb["검토 목록"].cell(row=2, column=FC).value = "B"
    wb["검토 목록"].cell(row=6, column=FC).value = "O"
    wb.save(str(out))
    rec2 = import_feedback(out, history=h)
    rows2 = load_gold(gold)
    assert rec2["updated"] >= 3 and rec2["added"] == 1 and len(rows2) == len(rows) + 1
    assert {r["문장"]: r for r in rows2}[first[0].text]["정답"] == "B"
    # 미표시 행을 맞음으로 간주
    rec3 = import_feedback(out, confirm_unmarked=True, history=h)
    hold_marked = 1 if (hold.max_row > 1 and hold.cell(row=2, column=1).value) else 0
    assert len(load_gold(gold)) == len(first) - 1 + hold_marked   # '???' 행은 끝까지 건너뜀
    assert rec3["gold_rows"] >= len(first) - 1


def test_gold_override_in_new_runs(sample_dir, cfg, fake_client, tmp_path):
    from ip_finder.goldmap import GoldMap
    from ip_finder.pipeline import run_file
    out, res = extract(sample_dir / "sample_report.pptx", cfg, tmp_path, fake_client)
    first_calls = fake_client.calls
    # 피드백: 목록의 첫 행은 X, 둘째 행은 D 로 확정 → 골드 폴더에 저장
    from ip_finder.report.xlsx import FEEDBACK_COL as FC
    wb = load_workbook(str(out))
    wb["검토 목록"].cell(row=2, column=FC).value = "X"
    wb["검토 목록"].cell(row=3, column=FC).value = "D"
    wb.save(str(out))
    rec = import_feedback(out, gold_dir=cfg.gold_dir(), history=History(cfg.history_dir()))
    assert Path(rec["gold"]).parent == tmp_path / "gold" and cfg.gold_files() == [Path(rec["gold"])]
    listed = [ll for ll in res.labeled if ll.label in ("A", "B", "C", "D") and not ll.hold_reason]
    gm = GoldMap.load(cfg.gold_paths, cfg.base_dir)
    assert gm.get(listed[0].text) == "X" and gm.get(listed[1].text) == "D" and len(gm) == 2
    # 다시 돌리면 같은 문장은 골드 정답을 그대로 쓴다
    client2 = type(fake_client)()
    out2, res2 = extract(sample_dir / "sample_report.pptx", cfg, tmp_path, client2)
    by_key = {ll.key: ll for ll in res2.labeled}
    a, b = by_key[listed[0].key], by_key[listed[1].key]
    assert a.label == "X" and a.source == "gold" and "골드 반영(" in a.notes[-1] and a.hold_reason == "" and a.stage_out == 2
    assert b.label == "D" and b.source == "gold" and b.score == 1.0 and b.confidence == 1.0 and b.stage_out == 2   # D 는 대상 등급 밖
    assert res2.info.gold_lines == 2 and res2.info.gold_changed == 2 and "2문장" in res2.info.gold_desc
    assert any("골드" in s for s in res2.info.settings_diff)                    # 이력에 골드 변화가 설정 차이로 찍힘
    wb2 = load_workbook(str(out2))
    assert not any(r[5] == listed[0].text for r in wb2["검토 목록"].iter_rows(min_row=2, values_only=True))   # X 로 확정 → 목록에서 빠짐
    assert any(r[5] == listed[0].text and r[11] == "골드" for r in wb2["2차 제외"].iter_rows(min_row=2, values_only=True))
    info = dict(r[:2] for r in wb2["실행 정보"].iter_rows(min_row=2, values_only=True) if r[0])
    assert info["골드 정답 반영"].startswith("2문장")
    # 골드 반영을 끄면 모델 판정으로 돌아간다. 채점(eval)과 골드 시트 초안에는 반영되지 않는다
    cfg.use_gold = False
    _, res3 = extract(sample_dir / "sample_report.pptx", cfg, tmp_path, type(fake_client)())
    assert {ll.key: ll for ll in res3.labeled}[listed[0].key].label == listed[0].label
    cfg.use_gold = True
    rep = evaluate(Path(rec["gold"]), cfg, rerun=True, client=type(fake_client)())
    assert rep["raw"]["accuracy"] < 1.0                                         # 골드를 그대로 쓰면 1.0 이 됐을 것
    draft = make_gold_sheet(sample_dir / "sample_report.pptx", cfg, None, type(fake_client)())
    assert draft == cfg.gold_dir() / "sample_report_gold.xlsx"                  # 기본 저장 위치 = 골드 폴더


def test_gold_lines_skip_llm_calls(sample_dir, cfg, cfg_cascade, fake_client, fake_embedder, tmp_path):
    from ip_finder.eval import write_gold_workbook
    from ip_finder.pipeline import run_file
    res = run_file(sample_dir / "sample_report.pptx", cfg, fake_client)
    page4 = [ll for ll in res.labeled if ll.page_no == 4]
    rows = [[n, "sample_report.pptx", ll.page_no, ll.page_title, ll.line_idx, ll.text, ll.label, ll.label, "LLM", "", 1.0, 1.0, "C", ""]
            for n, ll in enumerate(page4, 1)]
    (tmp_path / "gold").mkdir()
    write_gold_workbook(tmp_path / "gold" / "p4_gold.xlsx", rows, [("파일", "sample_report.pptx")])
    c = type(fake_client)()
    res_llm = run_file(sample_dir / "sample_report.pptx", cfg, c)              # llm 모드: 4페이지는 전부 골드 → 호출 7 → 6
    assert c.calls == 6 and all(ll.source == "gold" and ll.label == "C" for ll in res_llm.labeled if ll.page_no == 4)
    c2 = type(fake_client)()
    res_h = run_file(sample_dir / "sample_report.pptx", cfg_cascade, c2, embedder=fake_embedder)   # cascade: 골드 문장은 2차 후보에서 빠짐
    assert all(ll.source == "gold" for ll in res_h.labeled if ll.page_no == 4)
    assert res_h.info.llm_lines == sum(1 for ll in res_h.labeled if ll.page_no != 4 and ll.clf_label in ("A", "B"))
    assert not any("(원인 분석)" in u for u in c2.inputs)                        # 4페이지 문장은 LLM 입력에 없음


def test_gold_map_conflicts_latest_wins(tmp_path):
    import os, time
    from ip_finder.eval import write_gold_workbook
    from ip_finder.goldmap import GoldMap, find_gold_files
    d = tmp_path / "g"
    d.mkdir()
    row = lambda n, text, ans: [n, "r.pptx", 3, "제목", n, text, "A", "A", "LLM", "", 1.0, 1.0, ans, ""]
    write_gold_workbook(d / "old_gold.xlsx", [row(1, "냉각 유로를  이중 구조로 변경", "A"), row(2, "일정 조정", "X")], [])
    write_gold_workbook(d / "new_gold.xlsx", [row(1, "냉각 유로를 이중 구조로 변경", "B")], [])
    t = time.time()
    os.utime(d / "old_gold.xlsx", (t - 100, t - 100))
    os.utime(d / "new_gold.xlsx", (t, t))
    (d / "notes.xlsx").write_bytes(b"")
    assert [p.name for p in find_gold_files([d])] == ["new_gold.xlsx", "old_gold.xlsx"]
    gm = GoldMap.load([d])
    assert gm.get("냉각 유로를 이중 구조로 변경") == "B" and gm.get("  일정   조정 ") == "X" and gm.conflicts == 1
    assert gm.describe().startswith("2개 파일, 2문장") and GoldMap.load([tmp_path / "none"]).describe() == "없음"
