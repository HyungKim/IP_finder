"""기술 단서어와 변경 동사. 전처리(줄 제거를 건너뛸지)와 후처리(재현율 안전장치)가 함께 쓴다."""
from __future__ import annotations

import re

# 기술 내용을 암시하는 명사. 너무 일반적인 동사(적용, 변경, 개발)는 넣지 않는다.
TECH_WORDS = [
    "개선", "저감", "향상", "감소", "증가", "단축", "절감", "구조", "방식", "알고리즘", "조건", "원인", "불량",
    "특성", "성능", "효율", "수율", "대비", "신규", "최초", "자체", "정밀", "강도", "두께", "온도", "압력",
    "전압", "전류", "주파수", "조성", "코팅", "접착", "용접", "회로", "센서", "보정", "설계", "측정", "검사",
    "메커니즘", "응력", "드리프트", "노이즈", "오차", "편차",
]
_WORD_RE = re.compile("|".join(map(re.escape, TECH_WORDS)))
# 숫자 뒤에 단위가 붙은 경우 (예: 30%, 25㎛, 1.2ms, 85℃)
UNIT_RE = re.compile(
    r"\d\s*(%FS|％FS|%|％|㎛|um|µm|㎜|mm|cm|㎚|nm|ms|μs|us|ns|℃|°C|dB|Hz|kHz|MHz|GHz|mV|kV|mA|mW|kW|Ω|ohm|kN|MPa|GPa|bar|rpm|ppm|배|fps|FS)(?![A-Za-z가-힣])",
    re.IGNORECASE,
)
# 수단이 실제로 적혔음을 암시하는 동사 (제목 기반 보정에서 A를 유지할 조건)
CHANGE_VERBS = re.compile(
    r"(변경|적용|삽입|추가|도입|제어|보정|교체|채택|대체|확대|축소|조정|설계|구성|배치|코팅|증착|형성|부착|연결|분리|통합|최적화|구현|저장|로드)"
)
# 안전장치가 살리지 않는 문장 (돈·일정·담당·영업이 분명한 경우)
HARD_EXCLUDE = re.compile(
    r"(비용|단가|예산|투자비|억\s*원|만\s*원|\d\s*원\b|일정|납기|담당|클레임|매출|수주|회신|인사|감사합니다)"
)


def tech_words(text: str) -> list[str]:
    return sorted(set(_WORD_RE.findall(text)))


def unit_hits(text: str) -> list[str]:
    return sorted({m.group(0).strip() for m in UNIT_RE.finditer(text)})


def tech_cues(text: str) -> list[str]:
    """안전장치용: 단서 단어 + 단위."""
    return tech_words(text) + unit_hits(text)


def has_tech_word(text: str) -> bool:
    """전처리용: 단위는 세지 않고 단어만 본다 (금액 줄의 %는 단서가 아니다)."""
    return bool(_WORD_RE.search(text))

# ---- 분류기 특성 (학습 분류기와 하이브리드 판단에 사용) ----
PLAN_RE = re.compile(r"(예정|검토\s*중|검토$|검토\b|계획|추진|도입\s*검토|예상)")
PROBLEM_RE = re.compile(r"(원인|문제|불량|현상|한계|발생|저하|불가|오류|결함|불균형|편차|이슈)")
NONTECH_RE = re.compile(r"(일정|비용|예산|단가|담당|고객|클레임|매출|수주|회의|교육|표준|규정|감사|인사)")
EFFECT_RE = re.compile(r"(개선|저감|향상|감소|증가|단축|절감|확보|달성|대비|우위)")
NUM_RE = re.compile(r"\d")

FEATURE_NAMES = ["change_verb", "unit", "number", "effect_word", "problem_word", "plan_word", "nontech_word",
                 "len_short", "len_long", "pt_problem", "pt_result", "pt_means", "pt_plan"]


def cue_features(text: str, page_type_key: str = "general") -> list[float]:
    """정규식 단서 13개를 0/1 특성으로. 임베딩 뒤에 이어 붙여 학습 분류기 입력이 된다."""
    n = len(text)
    return [
        1.0 if CHANGE_VERBS.search(text) else 0.0,
        1.0 if UNIT_RE.search(text) else 0.0,
        1.0 if NUM_RE.search(text) else 0.0,
        1.0 if EFFECT_RE.search(text) else 0.0,
        1.0 if PROBLEM_RE.search(text) else 0.0,
        1.0 if PLAN_RE.search(text) else 0.0,
        1.0 if NONTECH_RE.search(text) else 0.0,
        1.0 if n <= 15 else 0.0,
        1.0 if n >= 60 else 0.0,
        1.0 if page_type_key == "problem" else 0.0,
        1.0 if page_type_key == "result" else 0.0,
        1.0 if page_type_key == "means" else 0.0,
        1.0 if page_type_key == "plan" else 0.0,
    ]

