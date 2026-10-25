from openpyxl import load_workbook

from ip_finder.eval import evaluate, make_gold_sheet


def test_gold_sheet_and_scoring(sample_dir, cfg, fake_client, tmp_path):
    gold = make_gold_sheet(sample_dir / "sample_report.pptx", cfg, tmp_path / "g.xlsx", fake_client)
    wb = load_workbook(str(gold))
    assert wb.sheetnames == ["라벨링", "안내", "메타"]
    rows = [r for r in wb["라벨링"].iter_rows(min_row=2, values_only=True) if r[0]]
    assert rows and all(r[8] in ("A", "B", "C", "D", "X") for r in rows)   # 정답 열이 모델 라벨로 미리 채워짐
    stored = evaluate(gold, cfg, rerun=False)
    assert stored["raw"]["accuracy"] == 1.0
    rerun = evaluate(gold, cfg, rerun=True, client=fake_client)
    assert rerun["rows"] == len(rows) and rerun["raw"]["accuracy"] == 1.0
    assert set(rerun["final"]["per_grade"]) == {"A", "B", "C", "D", "X"}
