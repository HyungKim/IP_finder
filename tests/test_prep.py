from pathlib import Path

from ip_finder.config import Config
from ip_finder.models import Document, Line, Page
from ip_finder.pipeline import prepare
from ip_finder.prep import page_weight
from ip_finder.prep.page_rules import IMAGE_PAGE
from ip_finder.prep.splitter import split_sentences
from ip_finder.readers import load_document


def test_page_and_line_rules_on_sample(sample_dir, cfg):
    doc = load_document(sample_dir / "sample_report.pptx")
    removed = prepare(doc, cfg)
    reasons = {p.no: p.excluded_reason for p in doc.pages}
    assert reasons[1] == "표지"
    assert "목차" in reasons[2]
    assert reasons[7] == IMAGE_PAGE
    assert "일정" in reasons[10]
    assert reasons[12] is not None
    assert all(reasons[n] is None for n in (3, 4, 5, 6, 8, 9, 11))
    assert removed["반복 문구"] >= 12           # 모든 슬라이드의 바닥글
    assert removed["담당자"] == 1
    p3 = [ln.text for ln in doc.pages[2].active_lines()]
    assert any(t.startswith("2분기 필드 불량률") for t in p3)   # 단서어가 있어 날짜 규칙에서 살아남음
    idxs = [ln.idx for ln in doc.pages[2].active_lines()]
    assert idxs == list(range(1, len(idxs) + 1))


def test_short_schedule_and_money_lines_removed(cfg):
    doc = Document(path=None, kind="pptx", title="", pages=[Page(no=5, title="진행 현황", lines=[
        Line(0, "3분기 파일럿 라인 적용, 4분기 양산 전환"),
        Line(0, "도포 설비 개조 비용 1.2억 원"),
        Line(0, "담당: 품질팀"),
        Line(0, "12"),
        Line(0, "접착제를 저탄성 실리콘계로 변경하여 응력 저감"),
    ])])
    prepare(doc, cfg)
    active = [ln.text for ln in doc.pages[0].active_lines()]
    assert active == ["접착제를 저탄성 실리콘계로 변경하여 응력 저감"]


def test_short_lines_are_excluded(cfg):
    doc = Document(path=None, kind="pptx", title="", pages=[Page(no=5, title="개선안", lines=[
        Line(0, "접착 구조 변경"),                                   # 7자 → 짧은 조각
        Line(0, "제어 알고리즘 최적화"),                               # 공백 빼면 9자 → 짧은 조각
        Line(0, "제어 알고리즘 최적화 적용 완료"),                     # 공백 빼면 13자 → 유지
        Line(0, "저탄성 실리콘계 접착제로 변경하여 응력 저감"),          # 19자 → 유지
        Line(0, "12"),                                              # 숫자만 (더 구체적인 사유가 우선)
    ])])
    removed = prepare(doc, cfg)
    assert [ln.text for ln in doc.pages[0].active_lines()] == ["제어 알고리즘 최적화 적용 완료", "저탄성 실리콘계 접착제로 변경하여 응력 저감"]
    assert removed["짧은 조각"] == 2 and removed["숫자만"] == 1
    doc2 = Document(path=None, kind="pptx", title="", pages=[Page(no=5, title="개선안", lines=[Line(0, "접착 구조 변경")])])
    prepare(doc2, Config(use_cache=False, cover_max_lines=0, short_line_chars=0))
    assert len(doc2.pages[0].active_lines()) == 1                      # 0 이면 끔
    long = "첫 번째 문장은 충분히 길게 써서 분할 기준을 넘긴다. 두 번째 문장도 마찬가지로 길게 이어진다. 적용 완료."
    assert split_sentences(long)[-1].endswith("적용 완료.") and len(split_sentences(long)) == 2   # 짧은 꼬리는 앞 문장에 붙음


def test_split_long_lines():
    text = "첫 번째 문장은 충분히 길게 써서 분할 기준을 넘긴다. 두 번째 문장도 마찬가지로 길게 이어진다. 끝."
    parts = split_sentences(text)
    assert len(parts) == 2 and parts[-1].endswith("끝.")
    doc = Document(path=None, kind="pptx", title="", pages=[Page(no=1, title="본문", lines=[Line(0, text), Line(0, "분할되지 않을 만큼 짧지만 열 자는 넘는 줄입니다")])])
    prepare(doc, Config(use_cache=False, cover_max_lines=0, split_len=40))
    act = doc.pages[0].active_lines()
    assert [ln.idx for ln in act] == [1, 2, 3] and act[0].split_from == 1 and act[2].split_from is None


def test_page_weight_two_classes():
    cfg = Config()
    for title in ("개선안 1: 패키지 접착 구조 변경", "검증 결과", "원인 분석", "향후 계획", "PS-200 보고"):
        pw = page_weight(title, cfg)
        assert pw.weight == 1.0 and pw.relevance == "높음" and pw.reason == "기본(높음)"
    pw = page_weight("품질 현황", cfg)
    assert pw.weight == 0.4 and pw.relevance == "낮음" and pw.reason == "낮음 키워드 '현황'"
    assert page_weight("고객 대응 현황", cfg).relevance == "낮음"
    cfg2 = Config(low_relevance_patterns=["Action\\s*Plan", "KPI"], high_relevance_patterns=["KPI\\s*개선"], low_relevance_weight=0.2)
    assert page_weight("Action Plan", cfg2).weight == 0.2 and page_weight("KPI 현황", cfg2).weight == 0.2
    assert page_weight("KPI 개선 구조", cfg2).weight == 1.0 and page_weight("KPI 개선 구조", cfg2).reason.startswith("높음 키워드")
    assert page_weight("원인 분석", cfg2).weight == 1.0
    off = Config(page_weight_enabled=False)
    assert page_weight("품질 현황", off) .weight == 1.0 and page_weight("품질 현황", off).reason == "가중치 끔"
    bad = Config(low_relevance_patterns=["(", "현황"])                          # 잘못된 정규식은 무시
    assert page_weight("품질 현황", bad).relevance == "낮음"


def test_old_config_keys_are_migrated(tmp_path):
    f = tmp_path / "ip_finder.toml"
    f.write_text('mode = "hybrid"\npage_weights = [["KPI", 0.3], ["개선", 0.9]]\n', encoding="utf-8")
    c = Config.load(f)
    assert c.mode == "cascade" and "KPI" in c.low_relevance_patterns and "개선" not in c.low_relevance_patterns
    assert c.low_relevance_patterns[:2] == Config().low_relevance_patterns[:2]


def test_state_paths_are_inside_install_folder(tmp_path):
    from ip_finder.config import app_root
    root = app_root()
    c = Config()
    assert c.cache_file() == root / "data" / "cache.sqlite" and c.history_dir() == root / "data" / "history"
    assert c.classifier_file() == root / "data" / "classifier.npz"
    assert Config(cache_path=str(tmp_path / "x.sqlite")).cache_file() == tmp_path / "x.sqlite"      # 절대 경로는 그대로
    cfg_file = tmp_path / "ip_finder.toml"
    cfg_file.write_text('cache_path = "data/c.sqlite"\nhistory_path = ""\n', encoding="utf-8")
    loaded = Config.load(cfg_file)
    assert loaded.cache_file() == tmp_path / "data" / "c.sqlite" and loaded.history_dir() is None   # 설정 파일 폴더 기준
    assert loaded.base_dir == tmp_path
    assert not (Path.home() / ".ip_finder" / "history").exists()
