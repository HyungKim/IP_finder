from ip_finder.models import LabeledLine
from ip_finder.post import apply_safety_net, apply_title_fix, discussion_point, section_name


def _ll(text, label, title="개선안 1"):
    return LabeledLine(page_no=1, page_title=title, section="", line_idx=1, text=text, label=label, raw_label=label)


def test_section_name():
    assert section_name("개선안 1: 패키지 접착 구조 변경") == "개선안"
    assert section_name("개선안 2: 온도 보상 알고리즘") == "개선안"
    assert section_name("3. 개선안") == "개선안"
    assert section_name("PS-200 압력 센서 모듈 개선") == "PS-200 압력 센서 모듈 개선"
    assert section_name("검증 결과 - 1차") == "검증 결과"


def test_title_fix_downgrades_mechanism_on_problem_pages():
    rows = [_ll("열팽창계수 차이로 고온에서 다이에 응력 발생", "A", "원인 분석"),
            _ll("접착제를 저탄성 실리콘계로 변경하여 응력 저감", "A", "원인 분석"),
            _ll("열팽창계수 차이로 응력 발생", "A", "개선안")]
    assert apply_title_fix(rows) == 1
    assert [r.label for r in rows] == ["C", "A", "A"]
    assert rows[0].notes == ["보정(A→C)"]


def test_safety_net_rescues_only_with_cues():
    rows = [_ll("2분기 필드 불량률 1.8%로 목표 0.5% 대비 초과", "X"),
            _ll("주요 고객 A사 클레임 3건 접수", "X"),
            _ll("접착제 변경에 따른 재료비 단가 약 4% 상승", "X"),
            _ll("펌웨어에서 2차 다항식으로 보정", "A")]
    assert apply_safety_net(rows) == 1
    assert [r.label for r in rows] == ["X?", "X", "X", "A"]
    assert rows[0].notes and rows[0].notes[0].startswith("단서어")


def test_templates():
    assert "수단" in discussion_point("B")
    assert discussion_point("Z") == ""
