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


def test_split_long_lines():
    text = "첫 번째 문장은 충분히 길게 써서 분할 기준을 넘긴다. 두 번째 문장도 마찬가지로 길게 이어진다. 끝."
    parts = split_sentences(text)
    assert len(parts) == 2 and parts[-1].endswith("끝.")
    doc = Document(path=None, kind="pptx", title="", pages=[Page(no=1, title="본문", lines=[Line(0, text), Line(0, "짧은 줄입니다")])])
    prepare(doc, Config(use_cache=False, cover_max_lines=0, split_len=40))
    act = doc.pages[0].active_lines()
    assert [ln.idx for ln in act] == [1, 2, 3] and act[0].split_from == 1 and act[2].split_from is None


def test_page_weight_rules_and_types():
    cfg = Config()
    assert page_weight("개선안 1: 패키지 접착 구조 변경", cfg).weight == 1.0
    assert page_weight("검증 결과", cfg).weight == 0.9
    assert page_weight("원인 분석", cfg).weight == 0.8
    assert page_weight("향후 계획", cfg).weight == 0.75
    assert page_weight("품질 현황", cfg).weight == 0.4 and page_weight("품질 현황", cfg).reason == "키워드 '현황'"
    assert page_weight("고객 대응 현황", cfg).weight == 0.3                       # 먼저 맞는 규칙
    assert page_weight("PS-200 보고", cfg).weight == 0.8 and page_weight("PS-200 보고", cfg).reason == "기본값"
    assert page_weight("문제점 및 개선 방안", cfg).weight == 1.0                   # 여러 유형이면 최대
    cfg2 = Config(page_weights=[["Action\\s*Plan", 0.6], ["KPI", 0]], page_type_weights={"problem": 0.5}, default_page_weight=0.2)
    assert page_weight("Action Plan", cfg2).weight == 0.6 and page_weight("KPI 현황", cfg2).weight == 0.0
    assert page_weight("원인 분석", cfg2).weight == 0.5 and page_weight("기타", cfg2).weight == 0.2
    cfg3 = Config(page_weights=[["(", 0.5], ["현황"]])                             # 잘못된 정규식·항목은 무시
    import pytest
    with pytest.raises(Exception):
        page_weight("현황", cfg3)
