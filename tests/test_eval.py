from openpyxl import load_workbook

from ip_finder.config import Config
from ip_finder.eval import evaluate, make_gold_sheet, train_classifier
from ip_finder.eval.gold import GOLD_HEADERS
from ip_finder.pipeline import extract


def test_gold_sheet_and_scoring(sample_dir, cfg, fake_client, tmp_path):
    gold = make_gold_sheet(sample_dir / "sample_report.pptx", cfg, tmp_path / "g.xlsx", fake_client)
    wb = load_workbook(str(gold))
    assert wb.sheetnames == ["라벨링", "안내", "메타"]
    header = [c.value for c in wb["라벨링"][1]]
    assert header == GOLD_HEADERS
    rows = [r for r in wb["라벨링"].iter_rows(min_row=2, values_only=True) if r[0]]
    assert rows and all(r[10] in ("A", "B", "C", "D", "X") for r in rows)   # 정답 열이 모델 라벨로 미리 채워짐
    stored = evaluate(gold, cfg, rerun=False)
    assert stored["raw"]["accuracy"] == 1.0
    rerun = evaluate(gold, cfg, rerun=True, client=fake_client)
    assert rerun["rows"] == len(rows) and rerun["raw"]["accuracy"] == 1.0
    assert set(rerun["final"]["per_grade"]) == {"A", "B", "C", "D", "X"}


def test_train_and_use_classifier(sample_dir, cfg, cfg_hybrid, fake_client, fake_embedder, tmp_path):
    gold = make_gold_sheet(sample_dir / "sample_report.pptx", cfg, tmp_path / "g.xlsx", fake_client)
    out = tmp_path / "clf.npz"
    cfg_hybrid.embed_model = "fake-embed"
    stats = train_classifier([gold], cfg_hybrid, out, fake_embedder)
    assert out.exists() and stats["n"] >= 20 and 0.0 <= stats["cv_accuracy"] <= 1.0 and stats["train_accuracy"] > 0.8
    cfg_hybrid.classifier_path = str(out)
    _, res = extract(sample_dir / "sample_report.pptx", cfg_hybrid, tmp_path, fake_client, embedder=fake_embedder)
    assert res.info.classifier.startswith("학습") and res.info.threshold == 0.25
    rep = evaluate(gold, cfg_hybrid, rerun=True, client=fake_client, embedder=fake_embedder)
    assert rep["rows"] == stats["n"] and "hybrid" in rep["source"]
