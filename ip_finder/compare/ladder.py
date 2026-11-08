"""사다리 실행(ladder): 스위치(또는 어떤 설정이든)를 한 칸씩 바꿔 가며 같은 보고서들을 반복 실행하고, 칸마다 무엇이 달라졌는지 비교한다.

  cumulative(누적): 기준선 → +1번째 칸 → +1·2번째 칸 → …  각 칸은 직전 칸과 비교한다 ("이 스위치를 켜니 무엇이 변했나")
  single(단독):     기준선 → 기준선+1번째 칸만 → 기준선+2번째 칸만 → …  각 칸은 기준선과 비교한다 (순서에 안 흔들리는 독립 기여)

설정 파일(TOML) 예:
    name = "prep"
    mode = "cumulative"
    [[step]]
    name = "layout"                 # switches.py 의 스위치 이름 → 켠다
    [[step]]
    label = "k-NN 분류기"
    set = { classifier = "knn" }    # 임의의 Config 필드도 바꿀 수 있다
실험이므로 골드 정답 반영(use_gold)과 실행 이력 저장은 끈다. 임베딩 캐시는 켜 두어 같은 문장은 한 번만 계산한다."""
from __future__ import annotations

import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from ..cache import LabelCache
from ..classify import load_classifier, needs_embedding
from ..config import Config
from ..pipeline import extract, make_embedder
from ..switches import BY_NAME, SWITCHES, set_switch
from .records import RunDiff, RunRecord, aggregate_gold, compare_records, gold_metrics, pair_records, record_from_result


@dataclass
class Step:
    name: str                       # 스위치 이름 또는 임의 이름
    label: str                      # 한글 이름
    set: dict = field(default_factory=dict)   # Config 필드 → 값

    def apply(self, cfg: Config) -> None:
        if self.name in BY_NAME:
            set_switch(cfg, self.name, True)
        for k, v in self.set.items():
            if not hasattr(cfg, k):
                raise ValueError(f"사다리 칸 '{self.name}': 모르는 설정 {k}")
            setattr(cfg, k, v)


@dataclass
class Ladder:
    name: str = "prep"
    mode: str = "cumulative"        # cumulative | single
    steps: list[Step] = field(default_factory=list)


def default_ladder(names: list[str] | None = None, mode: str = "cumulative") -> Ladder:
    """기본 사다리: 스위치 전부를 switches.py 순서대로 (레이아웃 → 줄 규칙 → 페이지 규칙 → 후처리)."""
    names = names or [s.name for s in SWITCHES]
    return Ladder("switches", mode, [Step(n, BY_NAME[n].label) for n in names])


def load_ladder(path: Path) -> Ladder:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    steps = []
    for i, st in enumerate(data.get("step", []), 1):
        name = str(st.get("name") or st.get("label") or f"step{i}")
        label = str(st.get("label") or (BY_NAME[name].label if name in BY_NAME else name))
        sets = dict(st.get("set") or {})
        if name not in BY_NAME and not sets:
            raise ValueError(f"사다리 칸 {i}: 스위치 이름(name)이거나 set 이 있어야 합니다")
        steps.append(Step(name, label, sets))
    mode = str(data.get("mode") or "cumulative")
    if mode not in ("cumulative", "single"):
        raise ValueError(f"mode 는 cumulative 또는 single: {mode}")
    return Ladder(str(data.get("name") or Path(path).stem), mode, steps)


def step_config(base: Config, ladder: Ladder, upto: int) -> Config:
    """upto = -1 이면 기준선 그대로. cumulative 는 0..upto 칸을 모두, single 은 upto 칸만 적용한다."""
    cfg = base.copy(use_gold=False, history_path="")
    if upto < 0:
        return cfg
    for i, st in enumerate(ladder.steps):
        if (ladder.mode == "cumulative" and i <= upto) or (ladder.mode == "single" and i == upto):
            st.apply(cfg)
    return cfg


@dataclass
class StepResult:
    index: int                      # -1 = 기준선
    name: str
    label: str
    cfg: Config
    out_dir: Path
    records: list[RunRecord] = field(default_factory=list)
    elapsed: float = 0.0
    gold: dict = field(default_factory=dict)            # 보고서 전체 합산 골드 지표
    per_file_gold: list[dict] = field(default_factory=list)

    def totals(self):
        from collections import Counter
        c: Counter = Counter()
        for r in self.records:
            c.update(r.by_status())
        return c

    def grade_counts(self):
        from collections import Counter
        c: Counter = Counter()
        for r in self.records:
            c.update(r.grade_counts())
        return c

    @property
    def title(self) -> str:
        return "기준선" if self.index < 0 else f"{self.index + 1}. {self.label}"


@dataclass
class LadderResult:
    ladder: Ladder
    inputs: list[Path]
    base_cfg: Config
    steps: list[StepResult]
    diffs: list[tuple[StepResult, StepResult, list[RunDiff]]]    # (비교 기준 칸, 이 칸, 파일별 비교)
    out_dir: Path
    gold_used: bool = False


def _slug(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)[:24] or "step"


def preflight(base_cfg: Config, ladder: Ladder, embedders: dict, cache) -> dict[tuple[str, str], object]:
    """모든 칸의 분류기를 미리 만들어 본다. 학습 파일이 없거나 임베딩 모델이 없으면 실행 전에 바로 알린다."""
    classifiers: dict[tuple[str, str], object] = {}
    for i in range(-1, len(ladder.steps)):
        cfg = step_config(base_cfg, ladder, i)
        key = (cfg.classifier, cfg.embed_model)
        if key in classifiers:
            continue
        emb = None
        if needs_embedding(cfg.classifier):
            emb = embedders.get(cfg.embed_model)
            if emb is None:
                emb = make_embedder(cfg, cache)
                embedders[cfg.embed_model] = emb
            if not emb.available():
                from ..ollama import explain_missing_model
                raise RuntimeError(f"임베딩 모델 {cfg.embed_model} 을 쓸 수 없습니다. {explain_missing_model(cfg.host, cfg.embed_model)}")
        classifiers[key] = load_classifier(cfg, emb)
    return classifiers


def run_ladder(inputs: list[Path], base_cfg: Config, ladder: Ladder, out_dir: Path, gold_rows: list[dict] | None = None,
               status=None, cancel=None, embedders: dict | None = None) -> LadderResult:
    """inputs 전부를 기준선과 각 칸 설정으로 실행한다. embedders 는 {임베딩 모델: 임베더} (테스트는 가짜를 넣는다)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    embedders = embedders if embedders is not None else {}
    cache = LabelCache(base_cfg.cache_file() if base_cfg.use_cache else None)
    try:
        classifiers = preflight(base_cfg, ladder, embedders, cache)
        results: list[StepResult] = []
        for i in range(-1, len(ladder.steps)):
            cfg = step_config(base_cfg, ladder, i)
            st = ladder.steps[i] if i >= 0 else None
            name = st.name if st else "baseline"
            label = st.label if st else "기준선"
            folder = out_dir / (f"step-{i + 1:02d}-{_slug(name)}")
            folder.mkdir(parents=True, exist_ok=True)
            sr = StepResult(i, name, label, cfg, folder)
            if status:
                status(f"[{i + 1}/{len(ladder.steps)}] {label}: 파일 {len(inputs)}개 실행")
            t0 = time.time()
            clf = classifiers[(cfg.classifier, cfg.embed_model)]
            emb = embedders.get(cfg.embed_model)
            for f in inputs:
                if cancel is not None:
                    cancel.check()
                out, res = extract(f, cfg, folder, embedder=emb, classifier=clf, use_gold=False, with_ext=True)
                rec = record_from_result(res, cfg, out)
                sr.records.append(rec)
                if gold_rows:
                    sr.per_file_gold.append(gold_metrics(rec, gold_rows, tuple(cfg.targets())))
            sr.elapsed = time.time() - t0
            if gold_rows:
                sr.gold = aggregate_gold(sr.per_file_gold)
            results.append(sr)
        diffs = []
        for n, sr in enumerate(results[1:], 1):
            base = results[n - 1] if ladder.mode == "cumulative" else results[0]
            pairs = pair_records(base.records, sr.records)
            diffs.append((base, sr, [compare_records(a, b) for a, b in pairs]))
    finally:
        cache.close()
    return LadderResult(ladder, list(inputs), base_cfg, results, diffs, out_dir, bool(gold_rows))
