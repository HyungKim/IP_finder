from ip_finder.cues import has_tech_word, tech_cues, unit_hits


def test_units_and_words():
    assert "%" in "".join(unit_hits("수율 92.1% → 97.8%"))
    assert "㎛" in "".join(unit_hits("두께 편차 ±15㎛"))
    assert "향상" in tech_cues("조립 수율 92.1% → 97.8%로 향상")


def test_has_tech_word_ignores_units():
    assert not has_tech_word("재료비 단가 약 4% 상승")
    assert has_tech_word("2분기 필드 불량률 1.8%로 목표 0.5% 대비 초과")
