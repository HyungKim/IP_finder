"""실행 설정. 기본값은 PROPOSAL.md v3의 결정 사항을 따르고, TOML 파일과 CLI 인자로 덮어쓴다."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

DEFAULT_PAGE_EXCLUDE = [
    r"목\s*차", r"차례", r"contents", r"agenda",
    r"일정", r"스케줄", r"schedule",
    r"비용", r"예산", r"투자비", r"cost", r"budget",
    r"조직", r"인력", r"담당자", r"체계도",
    r"감사합니다", r"thank", r"q\s*&\s*a", r"질의",
    r"참고\s*문헌", r"references",
    r"부록", r"appendix",
]


@dataclass
class Config:
    # LLM
    model: str = "qwen3:4b-instruct"
    host: str = "http://127.0.0.1:11434"
    num_ctx: int = 2048
    keep_alive: str = "30m"
    timeout_sec: int = 600
    max_chars_per_call: int = 1400      # 넘으면 페이지를 나눠 호출
    # 전처리
    split_len: int = 80                 # 이 길이를 넘는 줄은 문장 단위로 분할
    repeated_line_min_pages: int = 3    # 이 수 이상 페이지에 같은 줄이 있으면 반복 문구로 제거
    stoplist: list[str] = field(default_factory=list)   # 템플릿별 수동 제거 문구
    page_exclude_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_PAGE_EXCLUDE))
    cover_max_lines: int = 4            # 1페이지 본문이 이 수 이하이면 표지
    # 후처리
    title_fix: bool = True
    safety_net: bool = True
    # 캐시
    use_cache: bool = True
    cache_path: str = "~/.ip_finder/cache.sqlite"

    @classmethod
    def load(cls, path: str | Path | None = None, **overrides) -> "Config":
        data: dict = {}
        if path is None and Path("ip_finder.toml").exists():
            path = "ip_finder.toml"
        if path:
            data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
        known = {f.name for f in fields(cls)}
        merged = {k: v for k, v in data.items() if k in known}
        merged.update({k: v for k, v in overrides.items() if v is not None and k in known})
        return cls(**merged)

    def cache_file(self) -> Path:
        return Path(self.cache_path).expanduser()
