"""ip-finder 명령: extract / ui / check / gold-sheet / feedback / train / eval / history / pages"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import PROMPT_VERSION, __version__
from .config import Config


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--config", help="ip_finder.toml 경로 (기본: 현재 폴더 또는 설치 폴더의 ip_finder.toml)")
    p.add_argument("--model", help="Ollama LLM 모델 (기본 qwen3:4b-instruct. 정확도 우선이면 qwen3:8b)")
    p.add_argument("--host", help="Ollama 주소. 로컬(127.0.0.1)만 허용")
    p.add_argument("--mode", choices=["cascade", "fast", "llm"], help="cascade: 분류기 1차 추출(X 제외) → 후보 전부 LLM 2차 판정 (기본) / fast: 분류기만 / llm: 전부 LLM")
    p.add_argument("--embed-model", help="Ollama 임베딩 모델 (기본 bge-m3. KURE-v1 은 tools/import_kure.bat 후 kure-v1)")
    p.add_argument("--grades", help="추출 대상 등급 (기본 A,B). 1차는 이 등급 문장만 후보로, 2차는 이 등급인지 판정. 예: A,B,C,D")
    p.add_argument("--group-by", choices=["page", "type"], help="2차 LLM 묶음 기준 (기본 page: 페이지별 / type: 페이지 유형별, 호출 적음)")
    p.add_argument("--accept-score", type=float, help="신뢰도×가중치 가 이 값 이상이어야 검토 목록 (기본 0.5). 미만은 보류 시트")
    p.add_argument("--no-page-weight", action="store_true", help="페이지 가중치 끔 (모든 페이지 1.0)")
    p.add_argument("--low-weight", type=float, help="관련성 낮음 페이지의 가중치 (기본 0.4, 0 이면 판정 안 함)")
    p.add_argument("--short-chars", type=int, help="글자수(공백 제외)가 이 값 이하인 줄은 후보에서 제외 (기본 10)")
    p.add_argument("--keep-non-korean", action="store_true", help="한글 없는 줄(영어·숫자·기호만)도 후보에 넣음 (기본은 제외)")
    p.add_argument("--prompt", choices=["compact", "full"], help="시스템 프롬프트 판 (기본 compact)")
    p.add_argument("--classifier", help="학습된 분류기 파일(.npz) 경로 (기본: 설치 폴더의 data/classifier.npz)")
    p.add_argument("--gold", action="append", help="골드 파일이나 폴더 (반복 가능). 기본: 설치 폴더의 data/gold. 골드에 있는 문장은 정답을 그대로 씀")
    p.add_argument("--no-gold", action="store_true", help="골드 정답 반영 끔 (모델 판정만 보고 싶을 때)")


def _cfg(args) -> Config:
    return Config.load(args.config, model=args.model, host=args.host, mode=getattr(args, "mode", None),
                       embed_model=getattr(args, "embed_model", None),
                       accept_score=getattr(args, "accept_score", None), target_grades=getattr(args, "grades", None),
                       group_by=getattr(args, "group_by", None),
                       page_weight_enabled=False if getattr(args, "no_page_weight", False) else None,
                       low_relevance_weight=getattr(args, "low_weight", None),
                       short_line_chars=getattr(args, "short_chars", None),
                       require_korean=False if getattr(args, "keep_non_korean", False) else None,
                       prompt_variant=getattr(args, "prompt", None), classifier_path=getattr(args, "classifier", None),
                       use_cache=False if getattr(args, "no_cache", False) else None,
                       title_fix=False if getattr(args, "no_title_fix", False) else None,
                       safety_net=False if getattr(args, "no_safety_net", False) else None,
                       history_path="" if getattr(args, "no_history", False) else None,
                       gold_paths=getattr(args, "gold", None) or None,
                       use_gold=False if getattr(args, "no_gold", False) else None)


def cmd_check(args) -> int:
    from .llm import OllamaClient, assert_local
    cfg = _cfg(args)
    ok = True
    print(f"ip-finder {__version__} / 프롬프트 {PROMPT_VERSION} / Python {sys.version.split()[0]}")
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
    client = OllamaClient(cfg.host, cfg.model, timeout_sec=10)
    if client.available():
        models = client.installed_models()
        print(f"  [OK] Ollama 연결됨. 설치 모델: {', '.join(models) or '없음'}")
        if client.has_model():
            print(f"  [OK] 모델 {cfg.model} 준비됨")
        else:
            print(f"  [X ] 모델 {cfg.model} 없음 → ollama pull {cfg.model}")
            ok = False
        from .classify import OllamaEmbedder
        emb = OllamaEmbedder(cfg.host, cfg.embed_model, timeout_sec=10)
        if emb.available():
            print(f"  [OK] 임베딩 모델 {cfg.embed_model} 준비됨 (cascade/fast 모드)")
        else:
            print(f"  [- ] 임베딩 모델 {cfg.embed_model} 없음 → ollama pull {cfg.embed_model}  (없으면 llm 모드로 동작)")
    else:
        print(f"  [X ] Ollama에 연결할 수 없음 ({cfg.host}). Ollama를 실행하세요.")
        ok = False
    clf = cfg.classifier_file()
    print(f"  분류기: {'학습된 분류기 ' + str(clf) if clf.exists() else '제로샷(원형 문장). 골드 세트로 ip-finder train 하면 학습 분류기 사용'}")
    print(f"  판정 모드 기본값: {cfg.mode} (cascade = 분류기 1차 추출 → LLM 2차 판정), 추출 등급: {','.join(cfg.targets())}, 프롬프트: {cfg.prompt_variant}, 목록 점수 기준: {cfg.accept_score}")
    print(f"  페이지 가중치: {'켬' if cfg.page_weight_enabled else '끔'}, 관련성 낮음 가중치 {cfg.low_relevance_weight}, 낮음 키워드 {len(cfg.low_relevance_patterns)}개, 높음 키워드 {len(cfg.high_relevance_patterns)}개 (ip-finder pages <파일> 로 확인)")
    print(f"  캐시: {cfg.cache_file()} (원문 미저장, 해시+라벨+벡터)")
    print(f"  이력: {cfg.history_dir() or '저장 안 함'}  — 캐시·분류기·이력은 모두 설치 폴더의 data/ 아래. 설치본마다 따로 관리됩니다")
    golds = cfg.gold_files()
    print(f"  골드: {cfg.gold_dir()} — 파일 {len(golds)}개" + (" (골드에 있는 문장은 새 실행에서 정답을 그대로 씀)" if cfg.use_gold else " (반영 끔)"))
    if sys.platform == "win32":
        try:
            import win32com.client  # noqa: F401
            print("  [OK] pywin32 (구형 .ppt 변환 가능)")
        except ImportError:
            print("  [- ] pywin32 없음. 구형 .ppt는 PowerPoint에서 .pptx로 저장 후 입력")
    print("오프라인 확인: 방화벽에서 python.exe / ollama.exe 아웃바운드를 차단한 상태로 extract 가 정상 동작해야 합니다.")
    return 0 if ok else 1


def _summary(res) -> str:
    from .post import in_hold_list, in_review_list
    from .report.xlsx import is_clf_rejected, is_llm_rejected
    info = res.info
    grades = info.target_grades.split(",") if info.target_grades else ["A", "B"]
    listed = {g: sum(1 for ll in res.labeled if ll.label == g and in_review_list(ll)) for g in grades}
    held = sum(1 for ll in res.labeled if ll.hold_reason)
    xq = sum(1 for ll in res.labeled if in_hold_list(ll) and ll.label in ("X?", "?"))
    parts = [f"검토 목록 " + ", ".join(f"{g} {c}" for g, c in listed.items()) + f" (합 {sum(listed.values())})",
             f"보류 {held + xq} (점수 미달 {held}, 단서어 {xq})"]
    if info.mode == "cascade":
        parts.append(f"1차 제외 {sum(1 for ll in res.labeled if is_clf_rejected(ll))}, 2차 후보 {sum(1 for ll in res.labeled if ll.llm_label)}, "
                     f"2차 제외 {sum(1 for ll in res.labeled if is_llm_rejected(ll))}")
    if info.gold_lines:
        parts.append(f"골드 반영 {info.gold_lines}문장(모델과 달랐던 것 {info.gold_changed})")
    if info.prev_run_id:
        ch = info.changes or {}
        parts.append(f"직전 실행 대비 진입 {ch.get('entered', 0)}, 이탈 {ch.get('left', 0)}, 등급 변경 {ch.get('grade', 0)}")
    return " | ".join(parts)


def cmd_extract(args) -> int:
    from .pipeline import extract, find_inputs, make_client
    cfg = _cfg(args)
    files = find_inputs([Path(p) for p in args.paths])
    if not files:
        print("처리할 파일이 없습니다 (.pdf, .pptx, .ppt)")
        return 1
    client = make_client(cfg)
    if not client.available():
        print(f"Ollama에 연결할 수 없습니다 ({cfg.host}). 'ip-finder check'로 확인하세요.")
        return 1
    out_dir = Path(args.out_dir) if args.out_dir else None
    from collections import Counter
    from .pipeline import output_path
    taken = Counter(output_path(f, out_dir) for f in files)
    t_all = time.time()
    for f in files:
        print(f"\n== {f}")
        t0 = time.time()

        def progress(k, n, page, _t0=t0):
            if not args.quiet:
                print(f"  [{k:>2}/{n}] p{page.no:<3} {page.title[:40]:<40} {time.time() - _t0:6.0f}s", flush=True)

        def status(msg, _t0=t0):
            if not args.quiet:
                print(f"  {msg}  {time.time() - _t0:6.0f}s", flush=True)

        out, res = extract(f, cfg, out_dir, client, progress, with_ext=taken[output_path(f, out_dir)] > 1, status=status)
        info = res.info
        print(f"  → {out}")
        print(f"  모드 {info.mode} | 페이지 {info.pages_total} (판정 {info.pages_labeled}, 제외 {info.pages_excluded}, 이미지 {info.pages_image}) "
              f"| 분류기 {info.clf_lines}문장, LLM {info.llm_lines}문장, LLM 호출 {info.llm_calls}, 캐시 {info.cache_hits} | {info.elapsed_sec:.0f}초")
        print("  " + _summary(res))
        for s in info.settings_diff:
            print(f"  달라진 설정: {s}")
        for w in info.warnings:
            print(f"  경고: {w}")
    if len(files) > 1:
        print(f"\n총 {len(files)}개 파일, {time.time() - t_all:.0f}초")
    return 0


def cmd_pages(args) -> int:
    """LLM 없이 페이지 제목·관련성·가중치만 보여 준다. 키워드를 손볼 때 쓴다."""
    from .pipeline import prepare
    from .readers import load_document
    cfg = _cfg(args)
    for p in args.paths:
        doc = load_document(Path(p))
        prepare(doc, cfg)
        print(f"\n== {p}  (페이지 가중치 {'켬' if cfg.page_weight_enabled else '끔'}, 관련성 낮음 {cfg.low_relevance_weight}, 목록 점수 기준 {cfg.accept_score})")
        print(f"  {'p':>3} {'관련성':<4} {'가중치':>5} {'근거':<18} {'상태':<22} 제목")
        for pg in doc.pages:
            print(f"  {pg.no:>3} {pg.relevance:<4} {pg.weight:>5.2f} {pg.weight_reason[:18]:<18} {(pg.excluded_reason or '판정 ' + str(len(pg.active_lines())) + '문장')[:22]:<22} {pg.title[:50]}  [{pg.title_source}]")
    print("\n관련성 낮음 키워드는 ip_finder.toml 의 low_relevance_patterns, 강제로 높음은 high_relevance_patterns. UI '페이지 가중치' 탭에서도 됩니다.")
    return 0


def cmd_gold_sheet(args) -> int:
    from .eval import make_gold_sheet
    from .pipeline import make_client
    cfg = _cfg(args)
    client = make_client(cfg)
    if not client.available():
        print(f"Ollama에 연결할 수 없습니다 ({cfg.host}).")
        return 1
    out = make_gold_sheet(Path(args.file), cfg, Path(args.out) if args.out else None, client)
    print(f"골드 시트 생성: {out}\n'정답' 열에서 틀린 등급만 고친 뒤 'ip-finder eval {out}' 로 채점하고, 'ip-finder train {out}' 으로 분류기를 학습하세요.\n"
          f"골드 폴더({cfg.gold_dir()}) 안의 골드는 다음 실행부터 자동으로 반영됩니다 (같은 문장은 정답 그대로).")
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
        print("  피드백 열이 비어 있습니다. 결과 Excel의 검토 목록·보류·제외 문장 시트 '피드백' 열에 O / X / A~D 를 적고 저장한 뒤 다시 실행하세요.")
    else:
        print(f"  다음 실행부터 이 문장들은 골드 정답을 그대로 씁니다. 분류기도 갱신하려면: ip-finder train {rec['gold']} [다른 골드 ...]")
    return 0


def cmd_eval(args) -> int:
    from .eval import evaluate, print_report
    from .pipeline import make_client
    cfg = _cfg(args)
    client = None
    if not args.stored:
        client = make_client(cfg)
        if not client.available():
            print(f"Ollama에 연결할 수 없습니다 ({cfg.host}). 저장된 라벨만 채점하려면 --stored")
            return 1
    report = evaluate(Path(args.gold), cfg, rerun=not args.stored, client=client)
    print_report(report)
    return 0


def cmd_train(args) -> int:
    from .cache import LabelCache
    from .eval import train_classifier
    from .pipeline import make_embedder
    cfg = _cfg(args)
    cache = LabelCache(cfg.cache_file() if cfg.use_cache else None)
    try:
        emb = make_embedder(cfg, cache)
        if not emb.available():
            print(f"임베딩 모델 {cfg.embed_model} 을 쓸 수 없습니다 → ollama pull {cfg.embed_model}")
            return 1
        out = Path(args.out) if args.out else cfg.classifier_file()
        stats = train_classifier([Path(g) for g in args.gold], cfg, out, emb)
    finally:
        cache.close()
    print(f"학습 문장 {stats['n']}개 (등급별 {stats['counts']}), 임베딩 {stats['embed_model']}")
    print(f"5겹 교차검증 정확도 {stats['cv_accuracy']:.1%}, 학습 데이터 정확도 {stats['train_accuracy']:.1%}")
    print(f"저장: {stats['out']}  → 이제 cascade/fast 모드가 이 분류기를 1차에 씁니다. 'ip-finder eval <골드> --mode cascade' 로 확인하세요.")
    if stats["n"] < 100:
        print("참고: 문장 100개 미만이면 교차검증 값이 크게 흔들립니다. 보고서를 더 라벨링해 다시 학습하세요.")
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
        line = (f"  {r.get('run_id', '')}  {r.get('source_name', '')}  {s.get('mode', '')}/{s.get('model', '')}/{str(s.get('classifier', ''))[:28]}"
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
            print(f"  {t.get('time', '')}  {t.get('n', 0)}문장, 교차검증 {t.get('cv_accuracy', 0):.1%}, 골드 {len(t.get('sources', []))}개 → {t.get('out', '')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(prog="ip-finder", description="보고자료에서 특허 검토 후보 문장을 추출해 등급을 붙인 Excel을 만든다 (온디바이스)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("extract", help="PDF/PPTX(/.ppt) 또는 폴더를 처리해 <이름>_검토후보.xlsx 생성",
                       epilog="윈도우에서는 파일이나 폴더를 extract.bat 위로 끌어다 놓아도 됩니다. 결과는 원본 옆에 <이름>_검토후보.xlsx 로 생깁니다.")
    p.add_argument("paths", nargs="+")
    p.add_argument("--out-dir", help="결과를 모을 폴더 (기본: 원본 옆)")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--no-history", action="store_true", help="실행 이력(변경 추적)을 남기지 않음")
    p.add_argument("--no-title-fix", action="store_true", help="제목 기반 보정(A→C) 끔")
    p.add_argument("--no-safety-net", action="store_true", help="재현율 안전장치(X?) 끔")
    p.add_argument("-q", "--quiet", action="store_true")
    _common(p)
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("pages", help="LLM 없이 페이지 제목·관련성·가중치·제외 여부만 표시 (키워드 점검용)")
    p.add_argument("paths", nargs="+")
    _common(p)
    p.set_defaults(func=cmd_pages)

    p = sub.add_parser("ui", help="데스크톱 UI 실행 (Tkinter)")
    p.set_defaults(func=lambda a: __import__("ip_finder.ui", fromlist=["main"]).main([]))

    p = sub.add_parser("check", help="의존성, Ollama 연결, LLM·임베딩 모델 설치 여부 확인")
    _common(p)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("gold-sheet", help="골드 세트 라벨링용 엑셀 생성 (모델 초안 라벨 포함, 기본 저장 위치 data/gold)")
    p.add_argument("file")
    p.add_argument("--out", help="저장 경로 (기본: 골드 폴더 data/gold/<이름>_gold.xlsx)")
    p.add_argument("--no-cache", action="store_true")
    _common(p)
    p.set_defaults(func=cmd_gold_sheet)

    p = sub.add_parser("feedback", help="결과 Excel의 '피드백' 열(O/X/A~D)을 골드 시트로 가져오기")
    p.add_argument("result", help="<이름>_검토후보.xlsx")
    p.add_argument("--out", help="골드 시트 경로 (기본: 골드 폴더 data/gold/<이름>_gold.xlsx, 있으면 합침)")
    p.add_argument("--confirm-unmarked", action="store_true", help="검토 목록에서 피드백이 빈 행도 '맞음'으로 간주")
    _common(p)
    p.set_defaults(func=cmd_feedback)

    p = sub.add_parser("train", help="골드 시트로 분류기 학습 (임베딩 + 단서어 특성 → 소프트맥스 회귀)")
    p.add_argument("gold", nargs="+", help="정답이 채워진 골드 시트 (여러 개 가능)")
    p.add_argument("--out", help="분류기 저장 경로 (기본: 설정의 classifier_path)")
    p.add_argument("--no-cache", action="store_true")
    _common(p)
    p.set_defaults(func=cmd_train)

    p = sub.add_parser("eval", help="골드 시트로 등급 정확도와 검토 목록 정밀도 채점")
    p.add_argument("gold")
    p.add_argument("--stored", action="store_true", help="다시 돌리지 않고 시트에 저장된 모델 라벨을 채점")
    p.add_argument("--no-cache", action="store_true")
    _common(p)
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser("history", help="실행·피드백·학습 이력과 직전 실행 대비 변경 요약")
    p.add_argument("--limit", type=int, default=20)
    _common(p)
    p.set_defaults(func=cmd_history)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n중단됨 (캐시된 페이지는 다음 실행에서 재사용됩니다)")
        return 130
    except Exception as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
