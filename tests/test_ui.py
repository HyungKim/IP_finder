import pytest

tk = pytest.importorskip("tkinter")

from ip_finder.config import Config
from ip_finder.models import LabeledLine


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
        assert len(rows) == 2 and app.tree.item(rows[1])["values"][6] == "LLM"      # X, X? 는 미리보기에서 제외
        app.filter_var.set("A")
        app.fill_results()
        assert len(app.tree.get_children()) == 1
        assert app.build_cfg().mode == "llm"
        app.thr_var.set("0.3")
        assert app.build_cfg().confidence_threshold == 0.3
        app.thr_var.set("abc")
        with pytest.raises(ValueError):
            app.build_cfg()
        assert app.nb.index("end") == 2
    finally:
        app.destroy()
