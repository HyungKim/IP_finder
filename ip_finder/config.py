"""실행 설정. TOML 파일(ip_finder.toml)과 CLI 인자로 덮어쓴다.

규칙은 모두 스위치(bool)이고 **기본값은 전부 끔**이다. 아무 스위치도 켜지 않은 실행이 기준선이며, 사다리 실행이 한 칸씩 켜며 비교한다.
상태 파일(캐시, 학습 분류기, 실행 이력, 골드)은 설치 폴더의 data/ 아래에 둔다. 설치본마다 완전히 따로 관리되고 사용자 홈에는 아무것도 만들지 않는다.
상대 경로는 설정 파일이 있으면 그 파일의 폴더, 없으면 설치 폴더(app_root) 기준이다."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

from . import READER_VERSION, __version__

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

# 제목에 이 키워드가 있으면 '관련성 낮음' 페이지 (page_weight 스위치를 켰을 때만 쓰인다).
DEFAULT_LOW_RELEVANCE = [
    r"(고객|클레임|영업|매출|수주|회의|교육|인사|채용|복지)",
    r"(현황|실적|진행\s*상황|동향|추진\s*경과|경과)",
]

# 1차 분류기 이름 → 한글 이름. 구현은 classify/ 에 있다 (registry).
CLASSIFIER_NAMES = {
    "proto": "원형 문장 코사인 (제로샷)",
    "knn": "최근접 이웃 k-NN",
    "centroid": "등급 평균 벡터",
    "softmax": "소프트맥스 회귀",
    "ovr": "일대다 로지스틱",
    "cue": "단서어 규칙 (기준선)",
    "ngram": "글자 n-gram + 소프트맥스",
}

# 옛 설정 파일(0.x) 의 키를 새 필드로 옮긴다. 값이 없는 키는 그냥 무시된다.
_RENAMED = {"require_korean": "rule_require_korean"}


@dataclass
class Config:
    # ---- 연결 (임베딩용 Ollama) ----
    host: str = "http://127.0.0.1:11434"      # 로컬 주소만 허용
    timeout_sec: int = 300
    keep_alive: str = "30m"
    # ---- 1차 분류기 ----
    classifier: str = "proto"                 # CLASSIFIER_NAMES 의 키. proto·cue 는 학습 없이 동작, 나머지는 train 으로 만든 파일이 필요
    embed_model: str = "bge-m3"               # Ollama 임베딩 모델. KURE-v1 은 tools/import_kure.bat 로 들여온 뒤 "kure-v1"
    classifier_dir: str = "data/classifiers"  # 학습한 분류기 파일 <이름>.npz 가 놓이는 폴더 (설치 폴더 기준)
    knn_k: int = 5                            # knn 분류기의 이웃 수
    target_grades: str = "A,B"                # 추출 대상 등급. 이 등급으로 판정된 문장만 검토 목록 후보
    accept_score: float = 0.5                 # 신뢰도 × 가중치 가 이 값 이상이어야 검토 목록. 미만은 보류 시트
    # ---- 스위치 (switches.py 와 짝). 기본 전부 끔 = 기준선 ----
    layout_analysis: bool = False             # 읽기: 레이아웃 분석 (다단·문단·제목·표·항목 나누기)
    rule_short_line: bool = False             # 줄: 짧은 조각 제외
    rule_require_korean: bool = False         # 줄: 한글 없음 제외
    rule_split_long: bool = False             # 줄: 긴 줄 문장 분할
    rule_repeated_line: bool = False          # 줄: 반복 문구·stoplist 제외
    rule_pattern_lines: bool = False          # 줄: 숫자만·담당자·일정/금액 제외
    rule_page_exclude: bool = False           # 페이지: 제목 패턴으로 쪽 제외
    rule_cover: bool = False                  # 페이지: 표지 제외
    page_weight_enabled: bool = False         # 페이지: 관련성 낮음 가중치
    title_fix: bool = False                   # 후처리: 원인 쪽의 A → C
    safety_net: bool = False                  # 후처리: 단서어 있는 X → X?
    # ---- 규칙 매개변수 (해당 스위치를 켰을 때만 쓰인다) ----
    short_line_chars: int = 10
    split_len: int = 80
    repeated_line_min_pages: int = 3
    stoplist: list[str] = field(default_factory=list)
    page_exclude_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_PAGE_EXCLUDE))
    cover_max_lines: int = 4
    low_relevance_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_LOW_RELEVANCE))
    high_relevance_patterns: list[str] = field(default_factory=list)
    low_relevance_weight: float = 0.4
    # ---- 캐시·이력·골드 ----
    use_cache: bool = True
    cache_path: str = "data/cache.sqlite"     # 임베딩 캐시 (원문 미저장, 해시 → 벡터)
    history_path: str = "data/history"        # 실행 스냅샷(원문 미저장). 비우면 저장하지 않음
    gold_paths: list[str] = field(default_factory=lambda: ["data/gold"])   # 골드 파일 또는 폴더(*_gold.xlsx)
    use_gold: bool = True                     # 골드에 있는 문장은 새 실행에서 분류기 판정 대신 골드 정답을 쓴다 (실험 명령은 끈다)
    config_path: str = ""                     # 실제로 읽은 설정 파일 (정보용). 상대 경로의 기준 폴더가 된다

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
        for old, new in _RENAMED.items():
            if old in data and new not in data:
                data[new] = data.pop(old)
        known = {f.name for f in fields(cls)}
        merged = {k: v for k, v in data.items() if k in known}
        merged.update({k: v for k, v in overrides.items() if v is not None and k in known})
        cfg = cls(**merged)
        if cfg.classifier not in CLASSIFIER_NAMES:
            raise ValueError(f"모르는 분류기: {cfg.classifier!r} (가능: {', '.join(CLASSIFIER_NAMES)})")
        return cfg

    def copy(self, **changes) -> "Config":
        """값을 바꾼 복사본. 사다리 실행이 칸마다 쓴다."""
        from dataclasses import replace
        return replace(self, **changes)

    @property
    def base_dir(self) -> Path:
        """상대 경로의 기준: 설정 파일이 있으면 그 폴더, 없으면 설치 폴더."""
        return Path(self.config_path).resolve().parent if self.config_path else app_root()

    def resolve(self, p: str | Path) -> Path:
        p = Path(p).expanduser()
        return p if p.is_absolute() else self.base_dir / p

    def cache_file(self) -> Path:
        return self.resolve(self.cache_path)

    def classifier_file(self, name: str | None = None) -> Path:
        """학습 분류기 파일: <classifier_dir>/<이름>.npz"""
        return self.resolve(self.classifier_dir) / f"{name or self.classifier}.npz"

    def history_dir(self) -> Path | None:
        return self.resolve(self.history_path) if self.history_path else None

    def targets(self) -> list[str]:
        out = [g.strip().upper() for g in self.target_grades.replace(";", ",").split(",") if g.strip()]
        return [g for g in ("A", "B", "C", "D") if g in out] or ["A", "B"]

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
        """설정을 TOML 로 저장한다 (표준 라이브러리에 TOML 기록이 없어 직접 쓴다). UI '설정 저장'이 쓴다."""
        path = Path(path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(to_toml(self), encoding="utf-8")
        return path

    def fingerprint(self) -> dict:
        """결과에 영향을 주는 설정만. 실행 이력과 비교 명령의 '무엇이 달라졌나'에 쓴다. 스위치는 전부 들어간다."""
        from .switches import SWITCHES
        d = {"version": __version__, "reader_version": READER_VERSION,
             "classifier": self.classifier, "embed_model": self.embed_model, "knn_k": self.knn_k,
             "target_grades": ",".join(self.targets()), "accept_score": self.accept_score}
        for s in SWITCHES:
            d[s.field] = bool(getattr(self, s.field))
        d.update({"short_line_chars": self.short_line_chars, "split_len": self.split_len,
                  "repeated_line_min_pages": self.repeated_line_min_pages, "stoplist": self.stoplist,
                  "page_exclude_patterns": self.page_exclude_patterns, "cover_max_lines": self.cover_max_lines,
                  "low_relevance_patterns": self.low_relevance_patterns, "high_relevance_patterns": self.high_relevance_patterns,
                  "low_relevance_weight": self.low_relevance_weight, "use_gold": self.use_gold})
        return d


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
    lines = ["# IP Finder 설정. UI '설정 저장'이 만든 파일. 직접 고쳐도 된다.",
             "# 상대 경로(data/...)는 이 파일이 있는 폴더 기준이다. 스위치(true/false)는 switches.py 의 설명을 본다.", ""]
    for f in fields(cfg):
        if f.name == "config_path":
            continue
        v = getattr(cfg, f.name)
        if v is None:
            lines.append(f"# {f.name} = (기본값)")
            continue
        lines.append(f"{f.name} = {_toml_value(v)}")
    return "\n".join(lines) + "\n"
