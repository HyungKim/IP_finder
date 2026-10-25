from ip_finder.cache import LabelCache
from ip_finder.config import Config
from ip_finder.label import build_group_prompt, build_user_prompt, label_grouped, load_system_prompt
from ip_finder.models import Line, Page, RunInfo


def test_prompts():
    assert len(load_system_prompt("compact")) < len(load_system_prompt("full"))
    user = build_user_prompt("원인 분석", [Line(1, "응력 발생"), Line(2, "하위", level=1)], 4, "과제·원인 설명 페이지")
    assert user.splitlines()[0] == "[슬라이드 4] 제목: 원인 분석" and "(페이지 유형:" in user.splitlines()[1]
    assert user.splitlines()[3] == "[2]   하위"
    g = build_group_prompt("수단 설명 페이지", [("개선안 1: 아주 긴 제목이 있는 슬라이드 이름", "문장")])
    assert g.splitlines()[1] == "[1] (개선안 1: 아주 긴 제목이 있는 슬) 문장"   # 제목은 20자까지


def test_label_grouped_groups_by_page_type(fake_client):
    cfg = Config(use_cache=False, mode="hybrid")
    pages = [Page(no=4, title="원인 분석", lines=[Line(1, "열팽창계수 차이로 응력 발생"), Line(2, "두께 편차 확인")]),
             Page(no=5, title="개선안 1: 구조 변경", lines=[Line(1, "접착제를 실리콘계로 변경")]),
             Page(no=11, title="향후 계획", lines=[Line(1, "신규 방식 적용 예정")])]
    entries = [(p, ln) for p in pages for ln in p.lines]
    info = RunInfo(source="", model="", prompt_version="", started_at="")
    res = label_grouped(fake_client, entries, cfg, LabelCache(None), info)
    assert fake_client.calls == 3 and info.llm_calls == 3            # problem / means / plan 유형별 한 번씩
    assert res[(5, 1)] == "A" and res[(11, 1)] == "D" and res[(4, 1)] == "A"
    assert any("(원인 분석)" in u for u in fake_client.inputs)
