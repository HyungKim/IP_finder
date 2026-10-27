import pytest

tk = pytest.importorskip("tkinter")

from ip_finder.config import Config
from ip_finder.models import LabeledLine
from ip_finder.ui import parse_patterns, patterns_text


def _ll(label, source="clf"):
    return LabeledLine(page_no=5, page_title="개선안 1", section="개선안", line_idx=1, text="문장", label=label, raw_label=label, source=source)


def test_ui_builds_and_fills(tmp_path):
    try:
        from ip_finder.ui import App
        app = App(Config(use_cache=False, mode="llm", classifier_path=str(tmp_path / "none.npz"), history_path=str(tmp_path / "hist"), gold_paths=[str(tmp_path / "gold")]))
    except tk.TclError as e:
        pytest.skip(f"디스플레이 없음: {e}")
    try:
        app.add_files([str(tmp_path / "a.pptx"), str(tmp_path / "b.txt"), str(tmp_path / "a.pptx")])
        assert list(app.files_list.get(0, "end")) == [str(tmp_path / "a.pptx")]      # 지원 형식만, 중복 없이
        app.last_labeled = [_ll("A"), _ll("B", "llm"), _ll("X"), _ll("X?")]
        app.fill_results()
        rows = app.tree.get_children()
        assert len(rows) == 2 and app.tree.item(rows[1])["values"][9] == "LLM"      # X, X? 는 미리보기에서 제외
        app.filter_var.set("보류")
        app.fill_results()
        assert len(app.tree.get_children()) == 1                                    # X? 는 보류 보기에
        app.filter_var.set("검토 목록")
        app.filter_var.set("A")
        app.fill_results()
        assert len(app.tree.get_children()) == 1
        assert app.build_cfg().mode == "llm"
        app.filter_var.set("2차 제외 (1차 통과분)")
        app.last_labeled[2].source, app.last_labeled[2].clf_label, app.last_labeled[2].llm_label, app.last_labeled[2].stage_out = "llm", "A", "X", 2
        app.fill_results()
        assert len(app.tree.get_children()) == 1 and list(app.tree.item(app.tree.get_children()[0])["values"][7:9]) == ["A", "X"]
        app.filter_var.set("검토 목록")
        assert app.nb.index("end") == 4
        app.accept_var.set("0.7")
        app.pw_var.set(False)
        app.low_var.set("0.2")
        app.low_text.delete("1.0", "end")
        app.low_text.insert("1.0", "# 주석\n현황\n(고객|클레임)")
        app.high_text.insert("1.0", "KPI\\s*개선")
        app.grades_var.set(app.grades_var.get())
        c = app.build_cfg()
        assert c.targets() == ["A", "B"]
        app.grades_var.set("A·B·C·D  —  과제·계획까지")
        assert app.build_cfg().targets() == ["A", "B", "C", "D"]
        assert c.accept_score == 0.7 and c.page_weight_enabled is False and c.low_relevance_weight == 0.2
        assert c.short_line_chars == 14
        app.short_var.set("20")
        assert app.build_cfg().short_line_chars == 20
        app.short_var.set("x")
        with pytest.raises(ValueError):
            app.build_cfg()
        app.short_var.set("14")
        assert c.low_relevance_patterns == ["현황", "(고객|클레임)"] and c.high_relevance_patterns == ["KPI\\s*개선"]
        app.low_text.insert("end", "\n(잘못된")
        with pytest.raises(ValueError):
            app.build_cfg()
        app.low_text.delete("1.0", "end")
        app.accept_var.set("abc")
        with pytest.raises(ValueError):
            app.build_cfg()
        app.accept_var.set("0.5")
        saved = tmp_path / "cfg.toml"
        Config(low_relevance_patterns=["현황"], accept_score=0.7, page_weight_enabled=False).save(saved)
        loaded = Config.load(saved)
        assert loaded.low_relevance_patterns == ["현황"] and loaded.accept_score == 0.7 and loaded.page_weight_enabled is False
    finally:
        app.destroy()


def test_parse_patterns_roundtrip():
    pats = ["(현황|실적)", "Action\\s*Plan"]
    assert parse_patterns(patterns_text(pats)) == pats
    assert parse_patterns("") == [] and parse_patterns("# 주석만\n") == []
    with pytest.raises(ValueError):
        parse_patterns("(열린 괄호")
