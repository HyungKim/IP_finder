import pytest

tk = pytest.importorskip("tkinter")

from ip_finder.config import Config
from ip_finder.models import LabeledLine
from ip_finder.switches import SWITCHES
from ip_finder.ui import parse_patterns, patterns_text


def _ll(label, source="clf", stage_out=0):
    return LabeledLine(page_no=5, page_title="개선안 1", section="개선안", line_idx=1, text="문장", label=label, raw_label=label, source=source,
                       clf_label=label, clf_conf=0.8, stage_out=stage_out)


def test_ui_builds_and_fills(tmp_path):
    try:
        from ip_finder.ui import App
        app = App(Config(use_cache=False, classifier_dir=str(tmp_path / "clf"), history_path=str(tmp_path / "hist"), gold_paths=[str(tmp_path / "gold")]))
    except tk.TclError as e:
        pytest.skip(f"디스플레이 없음: {e}")
    try:
        assert app.nb.index("end") == 5
        app.add_files([str(tmp_path / "a.pptx"), str(tmp_path / "b.txt"), str(tmp_path / "a.pptx")])
        assert list(app.files_list.get(0, "end")) == [str(tmp_path / "a.pptx")]
        app.last_labeled = [_ll("A"), _ll("B", "gold"), _ll("X", stage_out=1), _ll("X?", stage_out=1), _ll("C", stage_out=2)]
        app.fill_results()
        rows = app.tree.get_children()
        assert len(rows) == 2 and app.tree.item(rows[1])["values"][8] == "골드"
        app.filter_var.set("보류")
        app.fill_results()
        assert len(app.tree.get_children()) == 1
        app.filter_var.set("분류기 제외")
        app.fill_results()
        assert len(app.tree.get_children()) == 1
        app.filter_var.set("후처리 제외")
        app.fill_results()
        assert len(app.tree.get_children()) == 1
        app.filter_var.set("A")
        app.fill_results()
        assert len(app.tree.get_children()) == 1
        c = app.build_cfg()
        assert c.classifier == "proto" and all(getattr(c, s.field) is False for s in SWITCHES)
        app.set_switches(True)
        app.switch_vars["korean"].set(False)
        c = app.build_cfg()
        assert c.layout_analysis is True and c.rule_require_korean is False and c.page_weight_enabled is True
        assert app.pw_var is app.switch_vars["page_weight"]
        app.clf_var.set(next(d for k, d in __import__("ip_finder.ui", fromlist=["CLASSIFIER_CHOICES"]).CLASSIFIER_CHOICES if k == "knn"))
        assert app.build_cfg().classifier == "knn"
        app.accept_var.set("0.7")
        app.low_var.set("0.2")
        app.low_text.delete("1.0", "end")
        app.low_text.insert("1.0", "# 주석\n현황\n(고객|클레임)")
        app.grades_var.set("A·B·C·D  —  과제·계획까지")
        c = app.build_cfg()
        assert c.accept_score == 0.7 and c.low_relevance_weight == 0.2 and c.targets() == ["A", "B", "C", "D"] and c.low_relevance_patterns == ["현황", "(고객|클레임)"]
        app.short_var.set("x")
        with pytest.raises(ValueError):
            app.build_cfg()
        app.short_var.set("10")
        app.low_text.insert("end", "\n(잘못된")
        with pytest.raises(ValueError):
            app.build_cfg()
    finally:
        app.destroy()


def test_parse_patterns_roundtrip():
    pats = ["(현황|실적)", "Action\\s*Plan"]
    assert parse_patterns(patterns_text(pats)) == pats and parse_patterns("# 주석만\n") == []
    with pytest.raises(ValueError):
        parse_patterns("(열린 괄호")
