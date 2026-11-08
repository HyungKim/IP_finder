from ip_finder.config import Config
from ip_finder.models import LabeledLine
from ip_finder.post import (STATUS_CLF_OUT, STATUS_HOLD, STATUS_POST_OUT, STATUS_REVIEW, apply_safety_net, apply_scores, apply_title_fix,
                            discussion_point, in_hold_list, in_review_list, section_name, status_of)
from ip_finder.post.scoring import confidence


def _ll(text, label, title="개선안 1", conf=0.8):
    return LabeledLine(page_no=1, page_title=title, section="", line_idx=1, text=text, label=label, raw_label=label, clf_label=label, clf_conf=conf)


def test_section_name():
    assert section_name("개선안 1: 패키지 접착 구조 변경") == "개선안"
    assert section_name("3. 개선안") == "개선안" and section_name("검증 결과 - 1차") == "검증 결과"


def test_title_fix_downgrades_mechanism_on_problem_pages():
    rows = [_ll("열팽창계수 차이로 고온에서 다이에 응력 발생", "A", "원인 분석"),
            _ll("접착제를 저탄성 실리콘계로 변경하여 응력 저감", "A", "원인 분석"),
            _ll("열팽창계수 차이로 응력 발생", "A", "개선안")]
    assert apply_title_fix(rows) == 1 and [r.label for r in rows] == ["C", "A", "A"] and rows[0].notes == ["보정(A→C)"]


def test_safety_net_rescues_only_with_cues():
    rows = [_ll("2분기 필드 불량률 1.8%로 목표 0.5% 대비 초과", "X"), _ll("주요 고객 A사 클레임 3건 접수", "X"),
            _ll("접착제 변경에 따른 재료비 단가 약 4% 상승", "X"), _ll("펌웨어에서 2차 다항식으로 보정", "A")]
    assert apply_safety_net(rows) == 1 and [r.label for r in rows] == ["X?", "X", "X", "A"] and rows[0].notes[0].startswith("단서어")


def test_templates():
    assert "수단" in discussion_point("B") and discussion_point("Z") == ""


def test_confidence_is_classifier_confidence_or_gold():
    clf = _ll("a", "A", conf=0.72)
    gold = _ll("a", "A"); gold.source = "gold"
    failed = _ll("a", "?"); failed.raw_label = "?"
    none = _ll("a", "A", conf=None)
    assert abs(confidence(clf) - 0.72) < 1e-9 and confidence(gold) == 1.0 and confidence(failed) == 0.0 and confidence(none) == 0.9


def test_apply_scores_and_statuses():
    rows = [_ll("수단 문장", "A", conf=0.9), _ll("효과 문장", "B", conf=0.9), _ll("제외", "X"), _ll("단서어", "X?")]
    rows[1].page_weight = 0.4
    rows[2].stage_out = 1
    held = apply_scores(rows, Config(accept_score=0.5))
    assert held == 1 and rows[0].score == 0.9 and rows[1].score == 0.36 and rows[1].hold_reason.startswith("점수 0.36 < 0.50")
    assert [status_of(r) for r in rows] == [STATUS_REVIEW, STATUS_HOLD, STATUS_CLF_OUT, STATUS_HOLD]
    assert in_review_list(rows[0]) and in_hold_list(rows[1]) and not in_review_list(rows[2])
    post = _ll("보정됨", "C"); post.stage_out = 2
    assert status_of(post) == STATUS_POST_OUT
