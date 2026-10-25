"""ip-finder 명령: extract / check / gold-sheet / eval"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import PROMPT_VERSION, __version__
from .config import Config


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--config", help="ip_finder.toml 경로 (기본: 현재 폴더의 ip_finder.toml)")
    p.add_argument("--model", help="Ollama LLM 모델 (기본 qwen3:4b-instruct)")
    p.add_argument("--host", help="Ollama 주소. 로컬(127.0.0.1)만 허용")
    p.add_argument("--mode", choices=["hybrid", "fast", "llm"], help="hybrid: 분류기 확신분 채택 + 애매한 문장만 LLM (기본) / fast: 분류기만 / llm: 전부 LLM")
    p.add_argument("--embed-model", help="Ollama 임베딩 모델 (기본 bge-m3)")
    p.add_argument("--threshold", type=float, help="이 확신 미만의 문장만 LLM으로 (기본: 제로샷 0.05, 학습 분류기 0.25)")
    p.add_argument("--prompt", choices=["compact", "full"], help="시스템 프롬프트 판 (기본 compact)")
    p.add_argument("--classifier", help="학습된 분류기 파일(.npz) 경로 (기본: ~/.ip_finder/classifier.npz)")


def _cfg(args) -> Config:
    return Config.load(args.config, model=args.model, host=args.host, mode=getattr(args, "mode", None),
                       embed_model=getattr(args, "embed_model", None), confidence_threshold=getattr(args, "threshold", None),
                       prompt_variant=getattr(args, "prompt", None), classifier_path=getattr(args, "classifier", None),
                       use_cache=False if getattr(args, "no_cache", False) else None,
                       title_fix=False if getattr(args, "no_title_fix", False) else None,
                       safety_net=False if getattr(args, "no_safety_net", False) else None)


def cmd_check(args) -> int:
    from .llm import OllamaClient, assert_local
    cfg = _cfg(args)
    ok = True
    print(f"ip-finder {__version__} / 프롬프트 {PROMPT_VERSION} / Python {sys.version.split()[0]}")
    for mod, name in (("pymupdf", "PyMuPDF"), ("pptx", "python-pptx"), ("openpyxl", "openpyxl")):
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
    else:
        print(f"  [X ] Ollama에 연결할 수 없음 ({cfg.host}). Ollama를 실행하세요.")
        ok = False
        from .classify import OllamaEmbedder
        emb = OllamaEmbedder(cfg.host, cfg.embed_model, timeout_sec=10)
        if emb.available():
            print(f"  [OK] 임베딩 모델 {cfg.embed_model} 준비됨 (hybrid/fast 모드)")
        else:
            print(f"  [- ] 임베딩 모델 {cfg.embed_model} 없음 → ollama pull {cfg.embed_model}  (없으면 llm 모드로 동작)")
    clf = cfg.classifier_file()
    print(f"  분류기: {'학습된 분류기 ' + str(clf) if clf.exists() else '제로샷(원형 문장). 골드 세트로 ip-finder train 하면 학습 분류기 사용'}")
    print(f"  판정 모드 기본값: {cfg.mode}, 프롬프트: {cfg.prompt_variant}")
    print(f"  캐시: {cfg.cache_file()} (원문 미저장, 해시+라벨+벡터)")
    if sys.platform == "win32":
        try:
            import win32com.client  # noqa: F401
            print("  [OK] pywin32 (구형 .ppt 변환 가능)")
        except ImportError:
            print("  [- ] pywin32 없음. 구형 .ppt는 PowerPoint에서 .pptx로 저장 후 입력")
    print("오프라인 확인: 방화벽에서 python.exe / ollama.exe 아웃바운드를 차단한 상태로 extract 가 정상 동작해야 합니다.")
    return 0 if ok else 1


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
        grades = {g: sum(1 for ll in res.labeled if ll.label == g) for g in ("A", "B", "C", "D", "X?", "?")}
        print(f"  → {out}")
        print(f"  모드 {info.mode} | 페이지 {info.pages_total} (판정 {info.pages_labeled}, 제외 {info.pages_excluded}, 이미지 {info.pages_image}) "
              f"| 분류기 {info.clf_lines}문장, LLM {info.llm_lines}문장, LLM 호출 {info.llm_calls}, 캐시 {info.cache_hits} | {info.elapsed_sec:.0f}초")
        print("  등급: " + ", ".join(f"{g} {c}" for g, c in grades.items()))
        for w in info.warnings:
            print(f"  경고: {w}")
    if len(files) > 1:
        print(f"\n총 {len(files)}개 파일, {time.time() - t_all:.0f}초")
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
    print(f"골드 시트 생성: {out}\n'정답' 열에서 틀린 등급만 고친 뒤 'ip-finder eval {out}' 로 채점하고, 'ip-finder train {out}' 으로 분류기를 학습하세요.")
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
    print(f"저장: {stats['out']}  → 이제 hybrid/fast 모드가 이 분류기를 씁니다. 'ip-finder eval <골드> --mode hybrid' 로 확인하세요.")
    if stats["n"] < 100:
        print("참고: 문장 100개 미만이면 교차검증 값이 크게 흔들립니다. 보고서를 더 라벨링해 다시 학습하세요.")
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
    p.add_argument("--no-title-fix", action="store_true", help="제목 기반 보정(A→C) 끔")
    p.add_argument("--no-safety-net", action="store_true", help="재현율 안전장치(X?) 끔")
    p.add_argument("-q", "--quiet", action="store_true")
    _common(p)
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("check", help="의존성, Ollama 연결, LLM·임베딩 모델 설치 여부 확인")
    _common(p)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("gold-sheet", help="골드 세트 라벨링용 엑셀 생성 (모델 초안 라벨 포함)")
    p.add_argument("file")
    p.add_argument("--out")
    p.add_argument("--no-cache", action="store_true")
    _common(p)
    p.set_defaults(func=cmd_gold_sheet)

    p = sub.add_parser("train", help="골드 시트로 분류기 학습 (임베딩 + 단서어 특성 → 소프트맥스 회귀)")
    p.add_argument("gold", nargs="+", help="정답이 채워진 골드 시트 (여러 개 가능)")
    p.add_argument("--out", help="분류기 저장 경로 (기본: 설정의 classifier_path)")
    p.add_argument("--no-cache", action="store_true")
    _common(p)
    p.set_defaults(func=cmd_train)

    p = sub.add_parser("eval", help="골드 시트로 정확도 채점")
    p.add_argument("gold")
    p.add_argument("--stored", action="store_true", help="다시 돌리지 않고 시트에 저장된 모델 라벨을 채점")
    p.add_argument("--no-cache", action="store_true")
    _common(p)
    p.set_defaults(func=cmd_eval)

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
