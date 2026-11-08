"""명령줄 끝에서 끝까지 (임베딩이 필요 없는 cue 분류기로 Ollama 없이 돈다)."""
from pathlib import Path

from ip_finder.cli import main


def test_switches_and_check_and_extract(sample_dir, tmp_path, capsys):
    cfg = tmp_path / "ip_finder.toml"
    cfg.write_text(f'classifier = "cue"\nuse_cache = false\nhistory_path = "{(tmp_path / "hist").as_posix()}"\ngold_paths = ["{(tmp_path / "gold").as_posix()}"]\n', encoding="utf-8")
    assert main(["switches", "--config", str(cfg), "--on", "short_line"]) == 0
    out = capsys.readouterr().out
    assert "짧은 줄 제외" in out and "켬" in out
    assert main(["extract", str(sample_dir / "sample_report.pptx"), "--config", str(cfg), "--out-dir", str(tmp_path / "o"), "--on", "all", "--off", "layout", "-q"]) == 0
    out = capsys.readouterr().out
    assert "검토 목록" in out and (tmp_path / "o" / "sample_report_검토후보.xlsx").exists()
    assert main(["pages", str(sample_dir / "sample_report.pdf"), "--config", str(cfg), "--on", "page_exclude"]) == 0
    assert "제목 규칙" in capsys.readouterr().out


def test_run_all_compare_runs_and_ladder(sample_dir, tmp_path, capsys):
    cfg = tmp_path / "ip_finder.toml"
    cfg.write_text(f'classifier = "cue"\nuse_cache = false\nhistory_path = ""\ngold_paths = ["{(tmp_path / "gold").as_posix()}"]\n', encoding="utf-8")
    assert main(["run-all", str(sample_dir), "--config", str(cfg), "--out", str(tmp_path / "r0"), "-q"]) == 0
    assert main(["run-all", str(sample_dir), "--config", str(cfg), "--out", str(tmp_path / "r1"), "--on", "all", "-q"]) == 0
    assert (tmp_path / "r0" / "run_manifest.json").exists() and len(list((tmp_path / "r1").glob("*_검토후보.xlsx"))) == 2
    assert main(["compare-runs", str(tmp_path / "r0"), str(tmp_path / "r1"), "--out", str(tmp_path / "cmp.xlsx")]) == 0
    out = capsys.readouterr().out
    assert "## 실행 비교" in out and (tmp_path / "cmp.xlsx").exists() and (tmp_path / "cmp.md").exists()
    assert main(["ladder", str(sample_dir / "sample_report.pdf"), "--config", str(cfg), "--steps", "layout,short_line", "--out", str(tmp_path / "lad"), "--no-gold-metrics"]) == 0
    out = capsys.readouterr().out
    assert "## 사다리 실행" in out and (tmp_path / "lad" / "사다리_switches.xlsx").exists()
    assert sorted(p.name for p in (tmp_path / "lad").iterdir() if p.is_dir()) == ["step-00-baseline", "step-01-layout", "step-02-short_line"]


def test_cli_errors_are_reported(tmp_path, capsys):
    assert main(["compare-runs", str(tmp_path / "none"), str(tmp_path / "none2")]) == 1
    assert main(["switches", "--on", "nope"]) == 1
    assert "모르는 스위치" in capsys.readouterr().err
