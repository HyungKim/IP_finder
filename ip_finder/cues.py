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
