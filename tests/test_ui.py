import pytest

tk = pytest.importorskip("tkinter")

from ip_finder.config import Config
from ip_finder.models import LabeledLine
from ip_finder.ui import parse_rules, rules_text


def _ll(label, source="clf"):
    return LabeledLine(page_no=5, page_title="개선안 1", section="개선안", line_idx=1, text="문장", label=label, raw_label=label, source=source)


def test_ui_builds_and_fills(tmp_path):
    try:
        from ip_finder.ui import App
        app = App(Config(use_cache=False, mode="llm", classifier_path=str(tmp_path / "none.npz")))
    except tk.TclError as e:
        pytest.skip(f"디스플레이 없음: {e}")
    try:
        app.add_files([str(tmp_path / "a.pptx"), str(tmp_path / "b.txt"), str(tmp_path / "a.pptx")])
        assert list(app.files_list.get(0, "end")) == [str(tmp_path / "a.pptx")]      # 지원 형식만, 중복 없이
        app.last_labeled = [_ll("A"), _ll("B", "llm"), _ll("X"), _ll("X?")]
        app.fill_results()
        rows = app.tree.get_children()
        assert len(rows) == 2 and app.tree.item(rows[1])["values"][7] == "LLM"      # X, X? 는 미리보기에서 제외
        app.filter_var.set("보류")
        app.fill_results()
        assert len(app.tree.get_children()) == 1                                    # X? 는 보류 보기에
        app.filter_var.set("검토 목록")
        app.filter_var.set("A")
        app.fill_results()
        assert len(app.tree.get_children()) == 1
        assert app.build_cfg().mode == "llm"
        app.thr_var.set("0.3")
        assert app.build_cfg().confidence_threshold == 0.3
        app.thr_var.set("abc")
        with pytest.raises(ValueError):
            app.build_cfg()
        app.thr_var.set("")
        assert app.nb.index("end") == 4
        app.accept_var.set("0.7")
        app.verify_var.set(True)
        app.rules_text.delete("1.0", "end")
        app.rules_text.insert("1.0", "# 주석\n현황 = 0.2\n(고객|클레임) = 0")
        c = app.build_cfg()
        assert c.accept_score == 0.7 and c.verify_grades == "A" and c.page_weights == [["현황", 0.2], ["(고객|클레임)", 0.0]]
        assert c.page_type_weights["means"] == 1.0
        app.rules_text.insert("end", "\n잘못된 줄")
        with pytest.raises(ValueError):
            app.build_cfg()
        app.rules_text.delete("1.0", "end")
        saved = tmp_path / "cfg.toml"
        Config(page_weights=[["현황", 0.2]], accept_score=0.7).save(saved)
        assert Config.load(saved).page_weights == [["현황", 0.2]] and Config.load(saved).accept_score == 0.7
    finally:
        app.destroy()


def test_parse_rules_roundtrip():
    rules = [["(현황|실적)", 0.4], ["Action\\s*Plan", 0.6]]
    assert parse_rules(rules_text(rules)) == rules
    assert parse_rules("") == [] and parse_rules("a=b=0.5") == [["a=b", 0.5]]
    with pytest.raises(ValueError):
        parse_rules("가중치 없음")
