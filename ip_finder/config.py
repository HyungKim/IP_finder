"""실행 설정. 기본값은 PROPOSAL.md의 결정 사항을 따르고, TOML 파일과 CLI 인자로 덮어쓴다.

상태 파일(캐시, 학습 분류기, 실행 이력)은 기본적으로 **설치 폴더의 data/** 아래에 둔다. 설치본마다 완전히 따로 관리되고,
사용자 홈 폴더에는 아무것도 만들지 않는다. 상대 경로는 설정 파일이 있으면 그 파일의 폴더, 없으면 설치 폴더(app_root) 기준이다."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

CONFIG_NAME = "ip_finder.toml"


def app_root() -> Path:
    """설치 폴더. 소스 폴더에서 실행하면(ip_finder/ 옆에 pyproject.toml 또는 install.bat) 그 폴더, 아니면 현재 폴더."""
    root = Path(__file__).resolve().parent.parent
    if (root / "pyproject.toml").exists() or (root / "install.bat").exists():
        return root
    return Path(os.getcwd())

DEFAULT_PAGE_EXCLUDE = [
    r"목\s*차", r"차례", r"contents", r"agenda",
    r"일정", r"스케줄", r"schedule",
    r"비용", r"예산", r"투자비", r"cost", r"budget",
    r"조직", r"인력", r"담당자", r"체계도",
    r"감사합니다", r"thank", r"q\s*&\s*a", r"질의",
    r"참고\s*문헌", r"references",
    r"부록", r"appendix",
]

# 제목에 이 키워드가 있으면 '관련성 낮음' 페이지. 회사 템플릿의 제목어를 ip_finder.toml 의 low_relevance_patterns 에 추가한다.
DEFAULT_LOW_RELEVANCE = [
    r"(고객|클레임|영업|매출|수주|회의|교육|인사|채용|복지)",
    r"(현황|실적|진행\s*상황|동향|추진\s*경과|경과)",
]
MODES = ("cascade", "fast", "llm")


@dataclass
class Config:
    # LLM
    model: str = "qwen3:4b-instruct"
    host: str = "http://127.0.0.1:11434"
    num_ctx: int = 2048
    keep_alive: str = "30m"
    timeout_sec: int = 600
    max_chars_per_call: int = 1400      # 넘으면 페이지를 나눠 호출
    prompt_variant: str = "compact"     # compact | full  (label/prompts/system.md, system_full.md)
    # 판정 모드
    mode: str = "cascade"               # cascade: 분류기 1차 추출(X 제외) → 후보 전부 LLM 2차 판정 / fast: 분류기만 / llm: 전부 LLM
    embed_model: str = "bge-m3"         # Ollama 임베딩 모델. KURE-v1 은 tools/import_kure.bat 로 들여온 뒤 "kure-v1"
    classifier_path: str = "data/classifier.npz"   # 학습된 분류기(설치 폴더 기준). 없으면 원형 문장 제로샷
    group_max_chars: int = 1200         # 2차 LLM 묶음 호출 한 번에 넣는 최대 글자 수
    # 페이지 가중치 (관련성 높음/낮음 두 분류) 와 점수 (정밀도 우선)
    page_weight_enabled: bool = True    # 끄면 모든 페이지 가중치 1.0
    low_relevance_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_LOW_RELEVANCE))   # 제목 정규식 → 관련성 낮음
    high_relevance_patterns: list[str] = field(default_factory=list)   # 낮음보다 우선해 높음으로 두는 제목 정규식
    low_relevance_weight: float = 0.4   # 관련성 낮음 페이지의 가중치. 0 이면 그 페이지는 판정하지 않음
    accept_score: float = 0.5           # 신뢰도 × 가중치 가 이 값 이상이어야 검토 목록. 미만은 보류 시트
    # 전처리
    split_len: int = 80                 # 이 길이를 넘는 줄은 문장 단위로 분할
    repeated_line_min_pages: int = 3    # 이 수 이상 페이지에 같은 줄이 있으면 반복 문구로 제거
    stoplist: list[str] = field(default_factory=list)   # 템플릿별 수동 제거 문구
    page_exclude_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_PAGE_EXCLUDE))
    cover_max_lines: int = 4            # 1페이지 본문이 이 수 이하이면 표지
    # 후처리
    title_fix: bool = True
    safety_net: bool = True
    # 캐시와 이력
    use_cache: bool = True
    cache_path: str = "data/cache.sqlite"          # 설치 폴더 기준
    history_path: str = "data/history"             # 실행 스냅샷(원문 미저장)과 피드백 이력. 비우면 저장하지 않음
    # 골드 정답 반영
    gold_paths: list[str] = field(default_factory=lambda: ["data/gold"])   # 골드 파일 또는 폴더(*_gold.xlsx). feedback/gold-sheet 의 기본 저장 위치는 첫 항목
    use_gold: bool = True               # 골드에 있는 문장은 새 실행에서 모델 판정 대신 골드 정답을 그대로 쓴다
    config_path: str = ""               # 실제로 읽은 설정 파일 (정보용). 상대 경로의 기준 폴더가 된다

    @classmethod
    def load(cls, path: str | Path | None = None, **overrides) -> "Config":
        data: dict = {}
        if path is None:
            for cand in (Path(CONFIG_NAME), app_root() / CONFIG_NAME):
                if cand.exists():
                    path = cand
                    break
        if path:
            data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
            data["config_path"] = str(Path(path).resolve())
        known = {f.name for f in fields(cls)}
        merged = {k: v for k, v in data.items() if k in known}
        # 이전 버전 설정 호환: hybrid → cascade, page_weights 의 낮은 가중치 규칙 → 관련성 낮음 키워드
        if merged.get("mode") == "hybrid":
            merged["mode"] = "cascade"
        old_rules = data.get("page_weights")
        if isinstance(old_rules, list) and "low_relevance_patterns" not in merged:
            low = list(DEFAULT_LOW_RELEVANCE)
            for item in old_rules:
                try:
                    if float(item[1]) <= 0.5 and str(item[0]) not in low:
                        low.append(str(item[0]))
                except (TypeError, ValueError, IndexError):
                    continue
            merged["low_relevance_patterns"] = low
        merged.update({k: v for k, v in overrides.items() if v is not None and k in known})
        return cls(**merged)

    @property
    def base_dir(self) -> Path:
        """상대 경로의 기준: 설정 파일이 있으면 그 폴더, 없으면 설치 폴더."""
        return Path(self.config_path).resolve().parent if self.config_path else app_root()

    def resolve(self, p: str | Path) -> Path:
        p = Path(p).expanduser()
        return p if p.is_absolute() else self.base_dir / p

    def cache_file(self) -> Path:
        return self.resolve(self.cache_path)

    def classifier_file(self) -> Path:
        return self.resolve(self.classifier_path)

    def history_dir(self) -> Path | None:
        return self.resolve(self.history_path) if self.history_path else None

    def gold_dir(self) -> Path:
        """feedback / gold-sheet 가 골드를 저장하는 폴더: gold_paths 의 첫 폴더 항목, 없으면 data/gold."""
        for p in self.gold_paths:
            if not str(p).lower().endswith(".xlsx"):
                return self.resolve(p)
        return self.resolve("data/gold")

    def gold_files(self) -> list[Path]:
        from .goldmap import find_gold_files
        return find_gold_files(self.gold_paths, self.base_dir)

    def save(self, path: str | Path) -> Path:
        """설정을 TOML로 저장한다 (표준 라이브러리에 TOML 기록이 없어 직접 쓴다). UI '설정 저장'이 쓴다."""
        path = Path(path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(to_toml(self), encoding="utf-8")
        return path

    def fingerprint(self) -> dict:
        """결과에 영향을 주는 설정만. 실행 이력의 '무엇이 달라졌나' 비교에 쓴다."""
        return {
            "model": self.model, "prompt_variant": self.prompt_variant, "mode": self.mode,
            "embed_model": self.embed_model, "group_max_chars": self.group_max_chars,
            "page_weight_enabled": self.page_weight_enabled, "low_relevance_patterns": self.low_relevance_patterns,
            "high_relevance_patterns": self.high_relevance_patterns, "low_relevance_weight": self.low_relevance_weight,
            "accept_score": self.accept_score, "split_len": self.split_len,
            "repeated_line_min_pages": self.repeated_line_min_pages, "stoplist": self.stoplist,
            "page_exclude_patterns": self.page_exclude_patterns, "cover_max_lines": self.cover_max_lines,
            "title_fix": self.title_fix, "safety_net": self.safety_net, "use_gold": self.use_gold,
        }


def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    raise TypeError(f"TOML로 쓸 수 없는 값: {v!r}")


def to_toml(cfg: Config) -> str:
    lines = ["# IP Finder 설정. UI '페이지 가중치 → 설정 저장'이 만든 파일. 직접 고쳐도 된다.",
             "# 상대 경로(data/...)는 이 파일이 있는 폴더 기준이다.", ""]
    tables = []
    for f in fields(cfg):
        if f.name == "config_path":
            continue
        v = getattr(cfg, f.name)
        if v is None:
            lines.append(f"# {f.name} = (기본값)")
            continue
        if isinstance(v, dict):
            tables.append((f.name, v))
            continue
        lines.append(f"{f.name} = {_toml_value(v)}")
    for name, d in tables:
        lines += ["", f"[{name}]"] + [f"{k} = {_toml_value(val)}" for k, val in d.items()]
    return "\n".join(lines) + "\n"
