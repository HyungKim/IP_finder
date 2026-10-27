from ip_finder.config import Config
from ip_finder.models import LabeledLine
from ip_finder.post import apply_safety_net, apply_scores, apply_title_fix, discussion_point, in_hold_list, in_review_list, section_name
from ip_finder.post.scoring import confidence


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


def test_confidence_by_source_and_agreement():
    llm_only = _ll("a", "A"); llm_only.source = "llm"
    agree = _ll("a", "A"); agree.source = "llm"; agree.clf_label = "A"; agree.clf_conf = 0.01
    disagree = _ll("a", "A"); disagree.source = "llm"; disagree.clf_label = "C"; disagree.clf_conf = 0.01; disagree.notes = ["불일치"]
    zero = _ll("a", "A"); zero.source = "clf"; zero.clf_label = "A"; zero.clf_conf = 0.1; zero.clf_top = 0.8
    trained = _ll("a", "A"); trained.source = "clf"; trained.clf_label = "A"; trained.clf_conf = 0.3; trained.clf_top = 0.72
    verified = _ll("a", "A"); verified.source = "verified"; verified.clf_label = "A"; verified.clf_conf = 0.3
    failed = _ll("a", "?"); failed.raw_label = "?"
    assert confidence(llm_only, False) == 0.9 and confidence(agree, False) == 1.0 and confidence(disagree, False) == 0.65
    assert abs(confidence(zero, False) - 0.75) < 1e-9 and abs(confidence(trained, True) - 0.72) < 1e-9
    assert confidence(verified, True) == 1.0 and confidence(failed, True) == 0.0


def test_apply_scores_holds_below_accept():
    rows = [_ll("수단 문장", "A"), _ll("효과 문장", "B"), _ll("제외", "X"), _ll("단서어", "X?")]
    for r in rows:
        r.source = "llm"
    rows[0].page_weight, rows[1].page_weight = 1.0, 0.4
    held = apply_scores(rows, Config(accept_score=0.5), trained=False)
    assert held == 1 and rows[0].score == 0.9 and rows[1].score == 0.36
    assert rows[1].hold_reason.startswith("점수 0.36 < 0.50") and "가중치 0.40" in rows[1].hold_reason
    assert in_review_list(rows[0]) and not in_review_list(rows[1]) and in_hold_list(rows[1]) and in_hold_list(rows[3])
    assert not in_review_list(rows[2]) and not in_hold_list(rows[2])
