"""ip-finder 명령.
  일상 실행: extract / parse / ui / check / switches / pages / layout
  정확도 관리: gold-sheet / feedback / train / eval / history
  실험(비교): compare-classifiers / run-all / ladder / compare-runs
모든 명령은 로컬에서만 동작한다 (Ollama 는 127.0.0.1 임베딩만)."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import STAGE, __version__
from .config import CLASSIFIER_NAMES, Config
from .switches import BY_NAME, SWITCHES, describe as describe_switches, set_all, set_switch, table_rows


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--config", help="ip_finder.toml 경로 (기본: 현재 폴더 또는 설치 폴더의 ip_finder.toml)")
    p.add_argument("--classifier", choices=list(CLASSIFIER_NAMES), help="1차 분류기 (기본 proto). " + ", ".join(f"{k}={v}" for k, v in CLASSIFIER_NAMES.items()))
    p.add_argument("--embed-model", help="Ollama 임베딩 모델 (기본 bge-m3. KURE-v1 은 tools/import_kure.bat 후 kure-v1)")
    p.add_argument("--host", help="Ollama 주소. 로컬(127.0.0.1)만 허용")
    p.add_argument("--grades", help="추출 대상 등급 (기본 A,B). 예: A,B,C,D")
    p.add_argument("--accept-score", type=float, help="신뢰도×가중치 가 이 값 이상이어야 검토 목록 (기본 0.5). 미만은 보류 시트")
    p.add_argument("--on", action="append", default=[], metavar="SWITCH", help="켤 스위치 (반복 가능, all 이면 전부). 이름: " + ", ".join(BY_NAME))
    p.add_argument("--off", action="append", default=[], metavar="SWITCH", help="끌 스위치 (반복 가능, all 이면 전부)")
    p.add_argument("--gold", action="append", help="골드 파일이나 폴더 (반복 가능). 기본: 설치 폴더의 data/gold")
    p.add_argument("--no-gold", action="store_true", help="골드 정답 반영 끔 (분류기 판정만 보고 싶을 때)")
    p.add_argument("--no-cache", action="store_true", help="임베딩 캐시 안 씀")
    p.add_argument("--baseline", choices=["on", "off"], help="비교 기준선용 분류기(cue, ngram)를 compare-classifiers 기본 대상에 넣을지 (기본: 설정 baseline_classifiers, 처음엔 on)")


def _cfg(args) -> Config:
    cfg = Config.load(args.config, classifier=getattr(args, "classifier", None), embed_model=getattr(args, "embed_model", None),
                      host=getattr(args, "host", None), target_grades=getattr(args, "grades", None),
                      accept_score=getattr(args, "accept_score", None),
                      use_cache=False if getattr(args, "no_cache", False) else None,
                      history_path="" if getattr(args, "no_history", False) else None,
                      gold_paths=getattr(args, "gold", None) or None,
                      use_gold=False if getattr(args, "no_gold", False) else None,
                      baseline_classifiers={"on": True, "off": False}.get(getattr(args, "baseline", None)))
    for name in getattr(args, "on", []) or []:
        set_all(cfg, True) if name == "all" else set_switch(cfg, name, True)
    for name in getattr(args, "off", []) or []:
        set_all(cfg, False) if name == "all" else set_switch(cfg, name, False)
    return cfg


def _embedder_or_none(cfg: Config, cache=None, required: bool = True):
    """임베딩이 필요한 분류기면 임베더를 만들고 가용성을 확인한다. 아니면 None."""
    from .classify import needs_embedding
    from .pipeline import make_embedder
    if not needs_embedding(cfg.classifier) and not required:
        return None
    emb = make_embedder(cfg, cache)
    if needs_embedding(cfg.classifier) and not emb.available():
        raise SystemExit(f"임베딩 모델 {cfg.embed_model} 을 쓸 수 없습니다 ({cfg.host}). Ollama 실행과 'ollama pull {cfg.embed_model}' 을 확인하세요.")
    return emb


# ------------------------------------------------------------------ 일상 실행
def cmd_check(args) -> int:
    from .classify import REGISTRY
    from .ollama import assert_local, installed_models, server_available
    cfg = _cfg(args)
    ok = True
    print(f"ip-finder {__version__} / {STAGE} / Python {sys.version.split()[0]}")
    print(f"  설치 폴더: {cfg.base_dir}  (설정 파일: {cfg.config_path or '없음, 기본값'})")
    for mod, name in (("pymupdf", "PyMuPDF"), ("pptx", "python-pptx"), ("openpyxl", "openpyxl"), ("numpy", "numpy")):
        try:
            m = __import__(mod)
            print(f"  [OK] {name} {getattr(m, '__version__', getattr(m, 'version', ''))}")
        except ImportError:
            print(f"  [X ] {name} 없음 → pip install -e .")
            ok = False
    try:
        assert_local(cfg.host)
        print(f"  [OK] 호스트 {cfg.host} (로컬)")
    except Exception as e:
        print(f"  [X ] {e}")
        return 1
    if server_available(cfg.host):
        models = installed_models(cfg.host)
        has = cfg.embed_model in models or f"{cfg.embed_model}:latest" in models
        print(f"  [OK] Ollama 연결됨. 설치 모델: {', '.join(models) or '없음'}")
        print(f"  [{'OK' if has else 'X '}] 임베딩 모델 {cfg.embed_model} {'준비됨' if has else '없음 → ollama pull ' + cfg.embed_model}")
        ok = ok and has
    else:
        print(f"  [X ] Ollama 에 연결할 수 없음 ({cfg.host}). 임베딩을 쓰는 분류기(proto·knn·centroid·softmax·ovr)는 동작하지 않습니다. cue·ngram 은 동작.")
        ok = False
    cls = REGISTRY[cfg.classifier]
    if cls.trainable:
        f = cfg.classifier_file()
        print(f"  분류기: {CLASSIFIER_NAMES[cfg.classifier]} — {'학습 파일 ' + str(f) if f.exists() else '학습 파일 없음 → ip-finder train --classifier ' + cfg.classifier}")
    else:
        print(f"  분류기: {CLASSIFIER_NAMES[cfg.classifier]} (학습 없음)")
    print(f"  스위치: {describe_switches(cfg)}")
    print(f"  추출 등급 {','.join(cfg.targets())}, 목록 점수 기준 {cfg.accept_score}, 비교 기준선 분류기(cue·ngram) {'포함' if cfg.baseline_classifiers else '제외'}")
    print(f"  캐시: {cfg.cache_file()} (원문 미저장, 해시+벡터) / 이력: {cfg.history_dir() or '저장 안 함'}")
    golds = cfg.gold_files()
    print(f"  골드: {cfg.gold_dir()} — 파일 {len(golds)}개" + (" (골드 문장은 정답을 그대로 씀)" if cfg.use_gold else " (반영 끔)"))
    if sys.platform == "win32":
        try:
            import win32com.client  # noqa: F401
            print("  [OK] pywin32 (구형 .ppt 변환 가능)")
        except ImportError:
            print("  [- ] pywin32 없음. 구형 .ppt 는 PowerPoint 에서 .pptx 로 저장 후 입력")
    return 0 if ok else 1


def cmd_switches(args) -> int:
    cfg = _cfg(args)
    print(f"스위치 (설정 파일: {cfg.config_path or '기본값'}) — {describe_switches(cfg)}\n")
    print(f"  {'묶음':<8} {'이름':<12} {'상태':<4} {'이름(영문)':<13} 지금 일어나는 일")
    for (group, label, state, what), s in zip(table_rows(cfg), SWITCHES):
        print(f"  {group:<8} {label:<12} {state:<4} {s.name:<13} {what}")
    print("\n켜기: --on 이름 (여러 번), 전부: --on all. 끄기: --off 이름. 설정 파일에는 Config 필드 이름(예: rule_short_line = true)으로 적습니다.")
    return 0


def _summary(res) -> str:
    from .post import STATUS_CLF_OUT, STATUS_HOLD, STATUS_POST_OUT, STATUS_REVIEW, in_review_list, status_of
    from collections import Counter
    info = res.info
    grades = info.target_grades.split(",") if info.target_grades else ["A", "B"]
    listed = {g: sum(1 for ll in res.labeled if ll.label == g and in_review_list(ll)) for g in grades}
    st = Counter(status_of(ll) for ll in res.labeled)
    parts = ["검토 목록 " + ", ".join(f"{g} {c}" for g, c in listed.items()) + f" (합 {sum(listed.values())})",
             f"{STATUS_HOLD} {st.get(STATUS_HOLD, 0)}, {STATUS_CLF_OUT} {st.get(STATUS_CLF_OUT, 0)}, {STATUS_POST_OUT} {st.get(STATUS_POST_OUT, 0)}",
             f"전처리 제외 줄 {sum(v for k, v in res.removed.items() if k != '빈 줄')}"]
    if info.gold_lines:
        parts.append(f"골드 반영 {info.gold_lines}문장(분류기와 달랐던 것 {info.gold_changed})")
    if info.prev_run_id:
        ch = info.changes or {}
        parts.append(f"직전 실행 대비 진입 {ch.get('entered', 0)}, 이탈 {ch.get('left', 0)}, 등급 변경 {ch.get('grade', 0)}")
    return " | ".join(parts)


def _run_files(files: list[Path], cfg: Config, out_dir: Path | None, quiet: bool, use_gold: bool = True, with_ext: bool | None = None):
    """extract 와 run-all 이 함께 쓰는 실행 루프. 임베더·분류기는 한 번만 만든다."""
    from collections import Counter
    from .cache import LabelCache
    from .classify import load_classifier
    from .pipeline import extract, output_path
    cache = LabelCache(cfg.cache_file() if cfg.use_cache else None)
    results = []
    try:
        emb = _embedder_or_none(cfg, cache, required=False)
        clf = load_classifier(cfg, emb)
        taken = Counter(output_path(f, out_dir) for f in files)
        t_all = time.time()
        for f in files:
            print(f"\n== {f}")
            t0 = time.time()

            def status(msg, _t0=t0):
                if not quiet:
                    print(f"  {msg}  {time.time() - _t0:6.1f}s", flush=True)

            ext = with_ext if with_ext is not None else taken[output_path(f, out_dir)] > 1
            out, res = extract(f, cfg, out_dir, status=status, with_ext=ext, embedder=emb, classifier=clf, use_gold=use_gold)
            info = res.info
            print(f"  → {out}")
            print(f"  페이지 {info.pages_total} (판정 {info.pages_labeled}, 제외 {info.pages_excluded}, 이미지 {info.pages_image}) "
                  f"| 분류기 {info.classifier} | 판정 {info.clf_lines}문장, 캐시 적중 {info.cache_hits} | {info.elapsed_sec:.1f}초")
            print("  " + _summary(res))
            for s in info.settings_diff:
                print(f"  달라진 설정: {s}")
            for w in info.warnings:
                print(f"  안내: {w}")
            results.append((out, res))
        if len(files) > 1:
            print(f"\n총 {len(files)}개 파일, {time.time() - t_all:.0f}초")
    finally:
        cache.close()
    return results


def cmd_extract(args) -> int:
    from .pipeline import find_inputs
    cfg = _cfg(args)
    files = find_inputs([Path(p) for p in args.paths])
    if not files:
        print("처리할 파일이 없습니다 (.pdf, .pptx, .ppt)")
        return 1
    print(f"ip-finder {__version__} | 분류기 {CLASSIFIER_NAMES[cfg.classifier]} | 스위치 {describe_switches(cfg)}")
    _run_files(files, cfg, Path(args.out_dir) if args.out_dir else None, args.quiet)
    return 0


def cmd_pages(args) -> int:
    """페이지 제목·관련성·가중치·제외 여부만 보여 준다 (분류기 없음). 키워드와 페이지 규칙 스위치를 손볼 때 쓴다."""
    from .pipeline import prepare
    from .readers import load_document
    cfg = _cfg(args)
    for p in args.paths:
        doc = load_document(Path(p), layout=cfg.layout_analysis)
        prepare(doc, cfg)
        print(f"\n== {p}  (읽기 {doc.reader}, 스위치 {describe_switches(cfg)})")
        print(f"  {'p':>3} {'관련성':<4} {'가중치':>5} {'근거':<18} {'상태':<22} 제목")
        for pg in doc.pages:
            print(f"  {pg.no:>3} {pg.relevance:<4} {pg.weight:>5.2f} {pg.weight_reason[:18]:<18} {(pg.excluded_reason or '판정 ' + str(len(pg.active_lines())) + '문장')[:22]:<22} {pg.title[:50]}  [{pg.title_source}]")
    return 0


def cmd_parse(args) -> int:
    """파싱 점검 HTML: 쪽 그림 옆에 리더가 읽은 줄(레이아웃 분석 / 원시 읽기)과 현재 설정이 뺄 줄을 보여 준다. 분류기 없음."""
    import webbrowser
    from .pipeline import find_inputs
    from .report.parse_view import write_parse_view
    cfg = _cfg(args)
    files = find_inputs([Path(p) for p in args.paths])
    if not files:
        print("처리할 파일이 없습니다 (.pdf, .pptx, .ppt)")
        return 1
    from collections import Counter
    from .report.parse_view import view_name
    taken = Counter((f.parent if not args.out_dir else Path(args.out_dir), f.stem) for f in files)
    for f in files:
        ext = taken[(f.parent if not args.out_dir else Path(args.out_dir), f.stem)] > 1          # 같은 이름의 pdf·pptx 는 확장자로 구분
        out = write_parse_view(f, cfg, (Path(args.out_dir) / view_name(f, ext)) if args.out_dir else None, images=not args.no_images, with_ext=ext)
        print(f"{f.name} → {out}")
        if args.open:
            webbrowser.open(out.resolve().as_uri())
    print("브라우저로 열어 ⚠ 표시 쪽부터 확인하세요. 원시 읽기와 비교하려면 위의 '원시 읽기도 보기'를 켭니다.")
    return 0


def _page_set(spec: str) -> set[int]:
    """"3-5,8" → {3, 4, 5, 8}"""
    out: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.update(range(int(a), int(b) + 1))
        else:
            out.add(int(part))
    return out


def cmd_layout(args) -> int:
    """읽기 진단: 레이아웃 분석이 고른 제목과 블록(종류·글씨 크기·굵기·위치)을 보여 준다."""
    from .readers import layout_report
    pages = _page_set(args.pages) if args.pages else None
    for p in args.paths:
        print("\n".join(layout_report(Path(p), pages)))
    print("\n종류: heading=제목 크기 줄, list_item=목록 항목, paragraph=문단. 제목 출처: font=제목 크기, bold=굵은 글씨, first-line=위쪽 첫 줄.")
    return 0


# ------------------------------------------------------------------ 정확도 관리
def cmd_gold_sheet(args) -> int:
    from .cache import LabelCache
    from .classify import load_classifier
    from .eval import make_gold_sheet
    cfg = _cfg(args)
    cache = LabelCache(cfg.cache_file() if cfg.use_cache else None)
    try:
        emb = _embedder_or_none(cfg, cache, required=False)
        clf = load_classifier(cfg, emb)
        out = make_gold_sheet(Path(args.file), cfg, Path(args.out) if args.out else None, embedder=emb, classifier=clf)
    finally:
        cache.close()
    print(f"골드 시트 생성: {out}\n'정답' 열에서 틀린 등급만 고친 뒤 'ip-finder eval {out}' 로 채점하고, 'ip-finder compare-classifiers' 로 분류기를 비교하세요.")
    return 0


def cmd_feedback(args) -> int:
    from .eval import import_feedback
    from .history import History
    cfg = _cfg(args)
    rec = import_feedback(Path(args.result), Path(args.out) if args.out else None, confirm_unmarked=args.confirm_unmarked,
                          history=History(cfg.history_dir()), gold_dir=cfg.gold_dir())
    print(f"피드백 {rec['feedback_rows']}행 → 골드 시트 {rec['gold']} (추가 {rec['added']}, 갱신 {rec['updated']}, 건너뜀 {rec['skipped']}, 골드 총 {rec['gold_rows']}행)")
    if rec["corrections"]:
        print("  내역: " + ", ".join(f"{k} {v}" for k, v in sorted(rec["corrections"].items())))
    if rec["feedback_rows"] == 0:
        print("  피드백 열이 비어 있습니다. 결과 Excel 의 검토 목록·보류·제외 시트 '피드백' 열에 O / X / A~D 를 적고 저장한 뒤 다시 실행하세요.")
    return 0


def _gold_rows(cfg: Config, paths: list[str] | None) -> list[dict]:
    from .goldmap import find_gold_files, load_gold
    files = find_gold_files(paths, None) if paths else cfg.gold_files()
    rows: list[dict] = []
    for f in files:
        rows.extend(load_gold(f))
    if not rows:
        raise SystemExit(f"골드 문장이 없습니다 (찾은 파일 {len(files)}개: {cfg.gold_dir() if not paths else paths}). 먼저 gold-sheet 또는 feedback 으로 골드를 만드세요.")
    print(f"골드 {len(rows)}문장, 파일 {len(files)}개: " + ", ".join(f.name for f in files))
    return rows


def cmd_train(args) -> int:
    from .cache import LabelCache
    from .classify import REGISTRY
    from .eval import train_classifier
    from .pipeline import make_embedder
    cfg = _cfg(args)
    name = args.classifier or cfg.classifier
    if not REGISTRY[name].trainable:
        print(f"{name} 은 학습하지 않는 분류기입니다. 학습형: " + ", ".join(k for k, c in REGISTRY.items() if c.trainable))
        return 1
    from .goldmap import find_gold_files
    golds = find_gold_files(args.gold, None) if args.gold else cfg.gold_files()
    if not golds:
        print("골드 파일이 없습니다.")
        return 1
    cache = LabelCache(cfg.cache_file() if cfg.use_cache else None)
    try:
        emb = None
        if REGISTRY[name].needs_embedding:
            emb = make_embedder(cfg, cache)
            if not emb.available():
                print(f"임베딩 모델 {cfg.embed_model} 을 쓸 수 없습니다 → ollama pull {cfg.embed_model}")
                return 1
        stats = train_classifier(golds, cfg, Path(args.out) if args.out else None, emb, name=name)
    finally:
        cache.close()
    print(f"분류기 {CLASSIFIER_NAMES[name]}: 학습 문장 {stats['n']}개 (등급별 {stats['counts']}), 임베딩 {stats['embed_model'] or '-'}")
    print(f"5겹 교차검증 정확도 {stats['cv_accuracy']:.1%}, 학습 데이터 정확도 {stats['train_accuracy']:.1%}")
    print(f"저장: {stats['out']}  → extract --classifier {name} 또는 설정 classifier = \"{name}\" 로 씁니다.")
    if stats["n"] < 100:
        print("참고: 문장 100개 미만이면 교차검증 값이 크게 흔들립니다. 분류기 비교(compare-classifiers)의 표준편차를 함께 보세요.")
    return 0


def cmd_eval(args) -> int:
    from .cache import LabelCache
    from .classify import load_classifier
    from .eval import evaluate, print_report
    cfg = _cfg(args)
    emb = clf = None
    cache = LabelCache(cfg.cache_file() if cfg.use_cache else None)
    try:
        if not args.stored:
            emb = _embedder_or_none(cfg, cache, required=False)
            clf = load_classifier(cfg, emb)
        report = evaluate(Path(args.gold), cfg, rerun=not args.stored, embedder=emb, classifier=clf)
    finally:
        cache.close()
    print_report(report)
    return 0


def cmd_history(args) -> int:
    from .history import History
    cfg = _cfg(args)
    h = History(cfg.history_dir())
    if not h.enabled:
        print("이력 저장이 꺼져 있습니다 (history_path).")
        return 1
    runs = h.list_runs(limit=args.limit)
    if not runs:
        print(f"저장된 실행이 없습니다 ({h.root}).")
        return 0
    print(f"실행 이력 ({h.root}), 최근 {len(runs)}건")
    for r in runs:
        st, s = r.get("stats", {}), r.get("settings", {})
        ch = r.get("changes") or {}
        line = (f"  {r.get('run_id', '')}  {r.get('source_name', '')}  {s.get('classifier', '')}/{s.get('embed_model', '')}"
                f"  목록 {st.get('list', 0)} (A{st.get('A', 0)} B{st.get('B', 0)} C{st.get('C', 0)} D{st.get('D', 0)}) 보류 {st.get('held', 0)}")
        if r.get("prev_run_id"):
            line += f"  | 이전 대비 진입 {ch.get('entered', 0)} 이탈 {ch.get('left', 0)} 등급 {ch.get('grade', 0)}"
        print(line)
        for d in r.get("settings_diff", []):
            print(f"        달라진 설정: {d}")
    fb = h.feedback_log()
    if fb:
        print(f"\n피드백 이력 {len(fb)}건")
        for f in fb[-args.limit:]:
            print(f"  {f.get('time', '')}  {Path(f.get('result', '')).name} → {Path(f.get('gold', '')).name}: {f.get('feedback_rows', 0)}행 "
                  + ", ".join(f"{k} {v}" for k, v in sorted((f.get("corrections") or {}).items())))
    tr = h.train_log()
    if tr:
        print(f"\n학습 이력 {len(tr)}건")
        for t in tr[-args.limit:]:
            print(f"  {t.get('time', '')}  {t.get('classifier', '')} {t.get('n', 0)}문장, 교차검증 {t.get('cv_accuracy', 0):.1%} → {t.get('out', '')}")
    return 0


# ------------------------------------------------------------------ 실험 (비교)
def _write_md(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def cmd_compare_classifiers(args) -> int:
    from .cache import LabelCache
    from .classify import available_names, needs_embedding
    from .compare import classifiers_markdown, compare_classifiers, write_classifier_compare
    from .pipeline import make_embedder
    cfg = _cfg(args)
    names = [n.strip() for n in args.names.split(",") if n.strip()] if args.names else available_names(cfg)
    print(f"비교 대상: {', '.join(names)}" + ("" if cfg.baseline_classifiers else "  (기준선 cue·ngram 제외: baseline_classifiers = false)"))
    rows = _gold_rows(cfg, args.gold)
    cache = LabelCache(cfg.cache_file() if cfg.use_cache else None)
    try:
        emb = make_embedder(cfg, cache) if any(needs_embedding(n) for n in names) else None
        result = compare_classifiers(rows, cfg, emb, names, k=args.folds, repeats=args.repeats, seed=args.seed,
                                     status=lambda m: print(f"  {m}", flush=True))
    finally:
        cache.close()
    out = Path(args.out) if args.out else Path.cwd() / "분류기_비교.xlsx"
    write_classifier_compare(result, out)
    md = classifiers_markdown(result)
    _write_md(out.with_suffix(".md"), md)
    print("\n" + md)
    print(f"→ {out}\n→ {out.with_suffix('.md')}")
    return 0


def cmd_run_all(args) -> int:
    import json
    from .pipeline import find_inputs
    cfg = _cfg(args)
    files = find_inputs([Path(p) for p in args.paths])
    if not files:
        print("처리할 파일이 없습니다 (.pdf, .pptx, .ppt)")
        return 1
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = cfg.copy(use_gold=False if args.no_gold or True else cfg.use_gold, history_path="")   # 실험: 골드 반영·이력 끔
    print(f"run-all → {out_dir} | 분류기 {CLASSIFIER_NAMES[cfg.classifier]} | 스위치 {describe_switches(cfg)} | 골드 반영 끔")
    t0 = time.time()
    results = _run_files(files, cfg, out_dir, args.quiet, use_gold=False, with_ext=True)
    manifest = {"version": __version__, "name": out_dir.name, "settings": cfg.fingerprint(), "files": [str(f) for f in files],
                "outputs": [str(o) for o, _ in results], "elapsed_sec": round(time.time() - t0, 1),
                "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    (out_dir / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n설정·파일 목록 저장: {out_dir / 'run_manifest.json'}  — 다른 결과 폴더와 비교: ip-finder compare-runs <폴더A> {out_dir}")
    return 0


def cmd_compare_runs(args) -> int:
    from .compare import compare_records, gold_metrics, load_records, pair_records, runs_markdown, write_runs_compare
    a = load_records(Path(args.a))
    b = load_records(Path(args.b))
    if not a or not b:
        print(f"결과 파일이 없습니다 (A {len(a)}개, B {len(b)}개). *_검토후보.xlsx 파일이나 그 폴더를 주세요.")
        return 1
    pairs = pair_records(a, b)
    if not pairs:
        print("이름이 같은 보고서가 없어 짝지을 수 없습니다: A=" + ", ".join(r.name for r in a) + " / B=" + ", ".join(r.name for r in b))
        return 1
    title_a = args.label_a or Path(args.a).name
    title_b = args.label_b or Path(args.b).name
    diffs = [compare_records(x, y) for x, y in pairs]
    gold = None
    if args.gold:
        cfg = _cfg(args)
        rows = _gold_rows(cfg, args.gold)
        tg = tuple(cfg.targets())
        gold = [(gold_metrics(x, rows, tg), gold_metrics(y, rows, tg)) for x, y in pairs]
    out = Path(args.out) if args.out else Path(args.b).with_name(f"비교_{Path(args.a).stem}_vs_{Path(args.b).stem}.xlsx") if Path(args.b).is_file() else Path(args.b) / f"비교_{Path(args.a).name}_vs_{Path(args.b).name}.xlsx"
    write_runs_compare(diffs, out, title_a, title_b, gold)
    md = runs_markdown(diffs, title_a, title_b, gold)
    _write_md(out.with_suffix(".md"), md)
    print(md)
    print(f"→ {out}\n→ {out.with_suffix('.md')}")
    return 0


def cmd_ladder(args) -> int:
    from .compare import default_ladder, ladder_markdown, load_ladder, run_ladder, write_ladder
    from .pipeline import find_inputs
    cfg = _cfg(args)
    files = find_inputs([Path(p) for p in args.paths])
    if not files:
        print("처리할 파일이 없습니다 (.pdf, .pptx, .ppt)")
        return 1
    if args.ladder:
        ladder = load_ladder(Path(args.ladder))
    else:
        names = [n.strip() for n in args.steps.split(",")] if args.steps else None
        ladder = default_ladder(names)
    if args.mode:
        ladder.mode = args.mode
    gold_rows = None
    if not args.no_gold_metrics:
        try:
            gold_rows = _gold_rows(cfg, args.gold)
        except SystemExit as e:
            print(f"골드 없이 진행 (골드 지표 생략): {e}")
    out_dir = Path(args.out) if args.out else Path.cwd() / f"ladder_{ladder.name}"
    print(f"사다리 {ladder.name} ({'누적' if ladder.mode == 'cumulative' else '단독'}), 칸 {len(ladder.steps)}개, 파일 {len(files)}개 → {out_dir}")
    print("  칸 순서: 기준선 → " + " → ".join(s.label for s in ladder.steps))
    result = run_ladder(files, cfg, ladder, out_dir, gold_rows, status=lambda m: print(f"  {m}", flush=True))
    out = write_ladder(result, out_dir / f"사다리_{ladder.name}.xlsx")
    md = ladder_markdown(result)
    _write_md(out.with_suffix(".md"), md)
    print("\n" + md)
    print(f"→ {out}\n→ {out.with_suffix('.md')}\n칸별 결과 파일은 {out_dir}/step-XX-… 폴더에 있습니다. 두 칸을 직접 비교: ip-finder compare-runs <칸 폴더A> <칸 폴더B>")
    return 0


# ------------------------------------------------------------------ main
def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(prog="ip-finder", description=f"보고자료에서 특허 검토 후보 문장을 추출해 등급을 붙인 Excel 을 만든다 (온디바이스). {STAGE}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("extract", help="PDF/PPTX(/.ppt) 또는 폴더를 처리해 <이름>_검토후보.xlsx 생성",
                       epilog="윈도우에서는 파일이나 폴더를 extract.bat 위로 끌어다 놓아도 됩니다. 결과는 원본 옆에 <이름>_검토후보.xlsx 로 생깁니다.")
    p.add_argument("paths", nargs="+")
    p.add_argument("--out-dir", help="결과를 모을 폴더 (기본: 원본 옆)")
    p.add_argument("--no-history", action="store_true", help="실행 이력(변경 추적)을 남기지 않음")
    p.add_argument("-q", "--quiet", action="store_true")
    _common(p)
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("switches", help="스위치 목록과 현재 상태 (무엇을 켜고 끌 수 있는지)")
    _common(p)
    p.set_defaults(func=cmd_switches)

    p = sub.add_parser("pages", help="페이지 제목·관련성·가중치·제외 여부만 표시 (분류기 없음)")
    p.add_argument("paths", nargs="+")
    _common(p)
    p.set_defaults(func=cmd_pages)

    p = sub.add_parser("parse", help="파싱 점검 HTML: 쪽 그림 옆에 읽어 낸 줄(레이아웃 분석/원시 읽기)과 규칙이 뺄 줄을 보여 줌 (분류기 없음)")
    p.add_argument("paths", nargs="+")
    p.add_argument("--out-dir", help="HTML 을 모을 폴더 (기본: 원본 옆 <이름>_파싱점검.html)")
    p.add_argument("--no-images", action="store_true", help="쪽 그림 없이 글만 (파일이 작아짐)")
    p.add_argument("--open", action="store_true", help="만든 뒤 브라우저로 연다")
    _common(p)
    p.set_defaults(func=cmd_parse)

    p = sub.add_parser("layout", help="읽기 진단: 레이아웃 분석이 고른 제목과 블록(종류·글씨 크기·굵기·위치) 표시")
    p.add_argument("paths", nargs="+")
    p.add_argument("--pages", help='보여 줄 페이지 (예: "3-5,8"). 기본 전체')
    p.set_defaults(func=cmd_layout)

    p = sub.add_parser("ui", help="데스크톱 UI 실행 (Tkinter)")
    p.set_defaults(func=lambda a: __import__("ip_finder.ui", fromlist=["main"]).main([]))

    p = sub.add_parser("check", help="의존성, Ollama 연결, 임베딩 모델, 분류기 파일, 스위치 상태 확인")
    _common(p)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("gold-sheet", help="골드 세트 라벨링용 엑셀 생성 (분류기 초안 라벨 포함, 기본 저장 위치 data/gold)")
    p.add_argument("file")
    p.add_argument("--out", help="저장 경로 (기본: 골드 폴더 data/gold/<이름>_gold.xlsx)")
    _common(p)
    p.set_defaults(func=cmd_gold_sheet)

    p = sub.add_parser("feedback", help="결과 Excel 의 '피드백' 열(O/X/A~D)을 골드 시트로 가져오기")
    p.add_argument("result", help="<이름>_검토후보.xlsx")
    p.add_argument("--out", help="골드 시트 경로 (기본: 골드 폴더 data/gold/<이름>_gold.xlsx, 있으면 합침)")
    p.add_argument("--confirm-unmarked", action="store_true", help="검토 목록에서 피드백이 빈 행도 '맞음'으로 간주")
    _common(p)
    p.set_defaults(func=cmd_feedback)

    p = sub.add_parser("train", help="골드로 학습형 분류기(knn, centroid, softmax, ovr, ngram) 학습 → data/classifiers/<이름>.npz")
    p.add_argument("--out", help="분류기 저장 경로 (기본: classifier_dir/<이름>.npz)")
    _common(p)
    p.set_defaults(func=cmd_train)

    p = sub.add_parser("eval", help="골드 시트 하나를 현재 설정으로 다시 판정해 채점 (정확도·재현율·정밀도)")
    p.add_argument("gold")
    p.add_argument("--stored", action="store_true", help="다시 돌리지 않고 시트에 저장된 라벨을 채점")
    _common(p)
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser("history", help="실행·피드백·학습 이력과 직전 실행 대비 변경 요약")
    p.add_argument("--limit", type=int, default=20)
    _common(p)
    p.set_defaults(func=cmd_history)

    p = sub.add_parser("compare-classifiers", help="[실험] 골드 교차 검증으로 1차 분류기 후보 전부 비교 → 분류기_비교.xlsx + .md")
    p.add_argument("--names", help="비교할 분류기 (쉼표). 기본: 전부 (" + ",".join(CLASSIFIER_NAMES) + "), 설정 baseline_classifiers=false 또는 --baseline off 면 cue·ngram 제외")
    p.add_argument("--folds", type=int, default=5, help="교차 검증 겹 수 (기본 5)")
    p.add_argument("--repeats", type=int, default=2, help="겹 나누기 반복 횟수 (기본 2, 표준편차 계산용)")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", help="결과 Excel 경로 (기본: 현재 폴더/분류기_비교.xlsx)")
    _common(p)
    p.set_defaults(func=cmd_compare_classifiers)

    p = sub.add_parser("run-all", help="[실험] 보고서 전부를 한 설정으로 돌려 이름 붙인 결과 폴더에 저장 (골드 반영·이력 끔)")
    p.add_argument("paths", nargs="+")
    p.add_argument("--out", required=True, help="결과 폴더 (예: results/s1-proto)")
    p.add_argument("-q", "--quiet", action="store_true")
    _common(p)
    p.set_defaults(func=cmd_run_all)

    p = sub.add_parser("compare-runs", help="[실험] 결과 Excel(또는 결과 폴더) 둘을 문장 단위로 비교 → 비교_*.xlsx + .md")
    p.add_argument("a", help="이전·기준 결과 (파일 또는 폴더)")
    p.add_argument("b", help="이후·비교 결과 (파일 또는 폴더)")
    p.add_argument("--label-a", help="A 의 표시 이름 (기본: 경로 이름)")
    p.add_argument("--label-b", help="B 의 표시 이름")
    p.add_argument("--out", help="비교 Excel 경로")
    _common(p)
    p.set_defaults(func=cmd_compare_runs)

    p = sub.add_parser("ladder", help="[실험] 스위치를 한 칸씩 켜며 반복 실행하고 칸마다 변화를 비교 → 사다리_*.xlsx + .md")
    p.add_argument("paths", nargs="+")
    p.add_argument("--ladder", help="사다리 설정 TOML (기본: 스위치 전부를 순서대로)")
    p.add_argument("--steps", help="기본 사다리에서 쓸 스위치와 순서 (쉼표). 예: layout,short_line,korean")
    p.add_argument("--mode", choices=["cumulative", "single"], help="cumulative: 누적(기본) / single: 기준선에 한 칸만")
    p.add_argument("--out", help="결과 폴더 (기본: 현재 폴더/ladder_<이름>)")
    p.add_argument("--no-gold-metrics", action="store_true", help="골드 지표 계산 생략")
    _common(p)
    p.set_defaults(func=cmd_ladder)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n중단됨 (임베딩 캐시는 다음 실행에서 재사용됩니다)")
        return 130
    except SystemExit as e:
        if isinstance(e.code, str):
            print(e.code, file=sys.stderr)
            return 1
        raise
    except Exception as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
