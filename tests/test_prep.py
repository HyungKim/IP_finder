from pathlib import Path

from ip_finder.config import Config
from ip_finder.models import Document, Line, Page
from ip_finder.pipeline import prepare
from ip_finder.prep import page_weight
from ip_finder.prep.page_rules import IMAGE_PAGE
from ip_finder.prep.splitter import split_sentences
from ip_finder.readers import load_document
from ip_finder.switches import BY_NAME, SWITCHES, describe, set_all, set_switch, switch_state


def _doc(*texts, title="개선안", no=5):
    return Document(path=None, kind="pptx", title="", pages=[Page(no=no, title=title, lines=[Line(0, t) for t in texts])])


def test_baseline_removes_nothing(sample_dir, cfg):
    doc = load_document(sample_dir / "sample_report.pptx", layout=True)
    removed = prepare(doc, cfg)
    assert dict(removed) == {} and all(p.excluded_reason in (None, IMAGE_PAGE) for p in doc.pages)
    assert all(ln.idx > 0 for p in doc.pages for ln in p.lines if ln.text.strip())


def test_all_rules_on_sample(sample_dir, cfg_all):
    doc = load_document(sample_dir / "sample_report.pptx", layout=True)
    removed = prepare(doc, cfg_all)
    reasons = {p.no: p.excluded_reason for p in doc.pages}
    assert reasons[1] == "표지" and "목차" in reasons[2] and reasons[7] == IMAGE_PAGE and "일정" in reasons[10]
    assert removed["반복 문구"] >= 12 and removed["담당자"] == 1
    idxs = [ln.idx for ln in doc.pages[2].active_lines()]
    assert idxs == list(range(1, len(idxs) + 1))


def test_switches_registry_and_config_fields():
    cfg = Config()
    assert all(hasattr(cfg, s.field) for s in SWITCHES) and len(SWITCHES) == 11
    assert all(v is False for v in switch_state(cfg).values()) and describe(cfg) == "전부 끔 (기준선)"
    set_switch(cfg, "short_line", True)
    assert cfg.rule_short_line is True and "짧은 줄 제외" in describe(cfg)
    set_all(cfg, True)
    assert describe(cfg) == "전부 켬" and BY_NAME["layout"].field == "layout_analysis"


def test_short_line_switch():
    doc = _doc("접착 구조 변경", "제어 알고리즘 최적화 적용 완료", "12")
    assert len(doc.pages[0].active_lines()) == 0 or prepare(doc, Config()) == {}
    doc = _doc("접착 구조 변경", "제어 알고리즘 최적화 적용 완료", "12")
    removed = prepare(doc, Config(rule_short_line=True))
    assert [ln.text for ln in doc.pages[0].active_lines()] == ["제어 알고리즘 최적화 적용 완료"] and removed["짧은 조각"] == 2
    doc = _doc("접착 구조 변경", "12")
    prepare(doc, Config(rule_short_line=True, rule_pattern_lines=True))
    assert [ln.removed_by for ln in doc.pages[0].lines] == ["짧은 조각", "숫자만"]        # 더 구체적인 사유가 우선


def test_korean_and_pattern_switches():
    texts = ["Adaptive gain scheduling for PID controller", "12.5 / 30 / 45", "담당: 품질팀", "도포 설비 개조 비용 1.2억 원", "PID 게인을 부하 구간별로 3단계 스케줄링"]
    doc = _doc(*texts)
    removed = prepare(doc, Config(rule_require_korean=True))
    assert removed["한글 없음"] == 2 and len(doc.pages[0].active_lines()) == 3
    doc = _doc(*texts)
    removed = prepare(doc, Config(rule_pattern_lines=True))
    assert removed["숫자만"] == 1 and removed["담당자"] == 1 and removed["일정/금액"] == 1
    assert [ln.text for ln in doc.pages[0].active_lines()] == [texts[0], texts[4]]


def test_repeated_switch_and_stoplist():
    pages = [Page(no=n, title=f"p{n}", lines=[Line(0, "대외비"), Line(0, f"본문 {n} 접착제 변경"), Line(0, "Confidential")]) for n in range(1, 4)]
    doc = Document(path=None, kind="pdf", title="", pages=pages)
    assert prepare(doc, Config()) == {}
    removed = prepare(doc, Config(rule_repeated_line=True, stoplist=["confidential"]))
    assert removed["반복 문구"] == 3 and removed["수동 목록"] == 3


def test_split_long_switch():
    text = "첫 번째 문장은 충분히 길게 써서 분할 기준을 넘긴다. 두 번째 문장도 마찬가지로 길게 이어진다. 끝."
    assert len(split_sentences(text)) == 2 and split_sentences(text)[-1].endswith("끝.")
    doc = _doc(text, "분할되지 않을 만큼 짧지만 열 자는 넘는 줄입니다", title="본문", no=1)
    prepare(doc, Config(split_len=40))
    assert [ln.idx for ln in doc.pages[0].active_lines()] == [1, 2]                       # 스위치 끔: 그대로
    doc = _doc(text, "분할되지 않을 만큼 짧지만 열 자는 넘는 줄입니다", title="본문", no=1)
    prepare(doc, Config(rule_split_long=True, split_len=40))
    act = doc.pages[0].active_lines()
    assert [ln.idx for ln in act] == [1, 2, 3] and act[0].split_from == 1 and act[2].split_from is None


def test_page_exclude_and_cover_switches():
    doc = Document(path=None, kind="pptx", title="", pages=[Page(no=1, title="표지", lines=[Line(0, "PS-200 개선 보고")]),
                                                               Page(no=2, title="목차", lines=[Line(0, "1. 배경 2. 개선안")])])
    prepare(doc, Config())
    assert [p.excluded_reason for p in doc.pages] == [None, None]
    prepare(doc, Config(rule_page_exclude=True))
    assert doc.pages[0].excluded_reason is None and doc.pages[1].excluded_reason.startswith("제목 규칙")
    prepare(doc, Config(rule_cover=True))
    assert doc.pages[0].excluded_reason == "표지" and doc.pages[1].excluded_reason is None


def test_page_weight_two_classes():
    on = Config(page_weight_enabled=True)
    for title in ("개선안 1: 패키지 접착 구조 변경", "검증 결과", "원인 분석", "PS-200 보고"):
        assert page_weight(title, on).weight == 1.0 and page_weight(title, on).reason == "기본(높음)"
    pw = page_weight("품질 현황", on)
    assert pw.weight == 0.4 and pw.relevance == "낮음" and pw.reason == "낮음 키워드 '현황'"
    cfg2 = Config(page_weight_enabled=True, low_relevance_patterns=["Action\\s*Plan", "KPI"], high_relevance_patterns=["KPI\\s*개선"], low_relevance_weight=0.2)
    assert page_weight("KPI 현황", cfg2).weight == 0.2 and page_weight("KPI 개선 구조", cfg2).weight == 1.0
    assert page_weight("품질 현황", Config()).reason == "가중치 끔"                 # 기본(끔)
    assert page_weight("품질 현황", Config(page_weight_enabled=True, low_relevance_patterns=["(", "현황"])).relevance == "낮음"   # 잘못된 정규식은 무시


def test_old_config_keys_are_migrated(tmp_path):
    f = tmp_path / "ip_finder.toml"
    f.write_text('mode = "cascade"\nmodel = "qwen3"\nrequire_korean = true\nshort_line_chars = 12\n', encoding="utf-8")
    c = Config.load(f)
    assert c.rule_require_korean is True and c.short_line_chars == 12 and c.classifier == "proto"


def test_state_paths_are_inside_install_folder(tmp_path):
    from ip_finder.config import app_root
    root = app_root()
    c = Config()
    assert c.cache_file() == root / "data" / "cache.sqlite" and c.history_dir() == root / "data" / "history"
    assert c.classifier_file() == root / "data" / "classifiers" / "proto.npz" and c.classifier_file("knn").name == "knn.npz"
    cfg_file = tmp_path / "ip_finder.toml"
    cfg_file.write_text('cache_path = "data/c.sqlite"\nhistory_path = ""\n', encoding="utf-8")
    loaded = Config.load(cfg_file)
    assert loaded.cache_file() == tmp_path / "data" / "c.sqlite" and loaded.history_dir() is None and loaded.base_dir == tmp_path
    assert not (Path.home() / ".ip_finder" / "history").exists()
    saved = Config(rule_short_line=True, classifier="knn").save(tmp_path / "s.toml")
    again = Config.load(saved)
    assert again.rule_short_line is True and again.classifier == "knn" and again.layout_analysis is False
