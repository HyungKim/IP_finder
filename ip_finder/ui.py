"""IP Finder 데스크톱 UI (Tkinter). 추가 설치 없이 동작한다.
실행: python -m ip_finder.ui  /  ip-finder ui  /  윈도우 ui.bat
탭 1 '추출': 파일·폴더 선택 → 옵션 → 실행 → 진행 로그 → 결과 미리보기(검토 목록·보류) → Excel 열기
탭 2 '페이지 가중치': 마지막 실행의 페이지별 제목·유형·가중치 표, 키워드 규칙·유형별 가중치·점수 기준 편집, 설정 저장
탭 3 '정확도 관리': 골드 시트 만들기 → 결과 Excel 피드백 가져오기 → 분류기 학습 → 채점
탭 4 '변경 추적': 실행 이력(설정 차이, 직전 대비 변경), 마지막 실행의 변경 행, 피드백·학습 이력"""
from __future__ import annotations

import contextlib
import io
import os
import queue
import subprocess
import sys
import threading
import traceback
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError as e:  # pragma: no cover
    raise SystemExit("tkinter 를 찾을 수 없습니다. 윈도우 python.org 설치본에는 기본 포함되며, macOS Homebrew 는 'brew install python-tk' 가 필요합니다.") from e

from . import __version__
from .config import CONFIG_NAME, Config, app_root
from .models import LabeledLine
from .post import in_hold_list, in_review_list
from .post.templates import discussion_point
from .prep.page_weight import DEFAULT_TYPE_WEIGHTS
from .readers import SUPPORTED

GRADE_FILL = {"A": "#FFE0B2", "B": "#FFF9C4", "C": "#DCEDC8", "D": "#BBDEFB"}
HOLD_FILL = "#EEEEEE"
MODES = [("hybrid", "hybrid  —  분류기 확신분 채택, 애매한 문장만 LLM (기본)"),
         ("fast", "fast  —  분류기만, 가장 빠름"),
         ("llm", "llm  —  전부 LLM, 가장 느림")]
SOURCE_NAME = {"clf": "분류기", "llm": "LLM", "verified": "분류기+LLM", "gold": "골드"}
TYPE_LABEL = {"means": "수단(개선안·설계)", "result": "결과(검증·효과)", "problem": "과제(원인·문제)", "plan": "계획(향후)",
              "status": "현황(실적·요약)", "general": "기타(유형 모름)"}
USER_CONFIG = app_root() / CONFIG_NAME     # 설치 폴더의 ip_finder.toml (설치본마다 따로)


class Cancelled(Exception):
    pass


def open_path(path: Path) -> None:
    """기본 프로그램으로 파일이나 폴더 열기."""
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as e:
        messagebox.showerror("열기 실패", f"{path}\n{e}")


def parse_rules(text: str) -> list[list]:
    """'패턴 = 가중치' 한 줄에 하나. # 으로 시작하면 주석."""
    rules = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"'패턴 = 가중치' 형식이 아닙니다: {line}")
        pattern, _, w = line.rpartition("=")
        pattern = pattern.strip()
        try:
            weight = float(w.strip())
        except ValueError:
            raise ValueError(f"가중치는 0~1 숫자여야 합니다: {line}") from None
        if not pattern:
            raise ValueError(f"패턴이 비어 있습니다: {line}")
        rules.append([pattern, max(0.0, min(1.0, weight))])
    return rules


def rules_text(rules: list[list]) -> str:
    return "\n".join(f"{p} = {w}" for p, w in rules)


class App(tk.Tk):
    def __init__(self, cfg: Config | None = None):
        super().__init__()
        self.cfg = cfg or Config.load()
        self.title(f"IP Finder {__version__}  —  특허 검토 후보 추출 (온디바이스)")
        self.geometry("1180x820")
        self.minsize(960, 640)
        self.q: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self._cancel = threading.Event()
        self.last_outputs: list[Path] = []
        self.last_labeled: list[LabeledLine] = []
        self.last_result = None
        self.gold_files: list[Path] = []
        self.last_gold: Path | None = None
        self.runs: list[dict] = []
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names() and sys.platform != "darwin":
            style.theme_use("clam")
        self._build()
        self.after(100, self._poll)
        self.after(400, self.check_env)
        self.after(600, self.refresh_history)
        self.after(700, self.load_gold_folder)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ 화면 구성
    def _build(self) -> None:
        nb = self.nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        self.tab_extract = ttk.Frame(nb)
        self.tab_weights = ttk.Frame(nb)
        self.tab_quality = ttk.Frame(nb)
        self.tab_history = ttk.Frame(nb)
        nb.add(self.tab_extract, text="  추출  ")
        nb.add(self.tab_weights, text="  페이지 가중치  ")
        nb.add(self.tab_quality, text="  정확도 관리  ")
        nb.add(self.tab_history, text="  변경 추적  ")
        self._build_extract(self.tab_extract)
        self._build_weights(self.tab_weights)
        self._build_quality(self.tab_quality)
        self._build_history(self.tab_history)
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=8, pady=6)
        self.status_var = tk.StringVar(value="환경 점검 중...")
        ttk.Label(bar, textvariable=self.status_var).pack(side="left")
        ttk.Button(bar, text="환경 점검", command=self.check_env).pack(side="right")

    def _text_with_scroll(self, parent, height=7, wrap="word", row=0, col=0):
        t = tk.Text(parent, height=height, wrap=wrap, state="disabled", font=("TkFixedFont", 10))
        t.grid(row=row, column=col, sticky="nsew", padx=(8, 0), pady=6)
        sb = ttk.Scrollbar(parent, command=t.yview)
        sb.grid(row=row, column=col + 1, sticky="ns", pady=6)
        t.configure(yscrollcommand=sb.set)
        return t

    def _tree(self, parent, cols, widths, height=8, row=0, col=0, stretch=()):
        tree = ttk.Treeview(parent, columns=cols, show="headings", height=height)
        for c, w in zip(cols, widths):
            tree.heading(c, text=c)
            tree.column(c, width=w, anchor="w", stretch=(c in stretch))
        tree.grid(row=row, column=col, sticky="nsew", padx=(8, 0), pady=6)
        sb = ttk.Scrollbar(parent, command=tree.yview)
        sb.grid(row=row, column=col + 1, sticky="ns", pady=6)
        tree.configure(yscrollcommand=sb.set)
        return tree

    def _build_extract(self, root: ttk.Frame) -> None:
        root.columnconfigure(0, weight=1)
        root.rowconfigure(3, weight=1)
        root.rowconfigure(4, weight=2)

        f_in = ttk.LabelFrame(root, text=" 1. 입력 파일  (PDF, PPTX, PPT. 폴더는 하위 폴더까지) ")
        f_in.grid(row=0, column=0, sticky="ew", padx=6, pady=(8, 4))
        f_in.columnconfigure(0, weight=1)
        self.files_list = tk.Listbox(f_in, height=4, selectmode="extended")
        self.files_list.grid(row=0, column=0, sticky="ew", padx=(8, 4), pady=6)
        btns = ttk.Frame(f_in)
        btns.grid(row=0, column=1, sticky="n", padx=(0, 8), pady=6)
        ttk.Button(btns, text="파일 추가...", command=self.add_files_dialog, width=14).pack(fill="x", pady=1)
        ttk.Button(btns, text="폴더 추가...", command=self.add_folder_dialog, width=14).pack(fill="x", pady=1)
        ttk.Button(btns, text="선택 제거", command=self.remove_selected, width=14).pack(fill="x", pady=1)
        ttk.Button(btns, text="모두 지우기", command=lambda: self.files_list.delete(0, "end"), width=14).pack(fill="x", pady=1)

        f_opt = ttk.LabelFrame(root, text=" 2. 옵션 ")
        f_opt.grid(row=1, column=0, sticky="ew", padx=6, pady=4)
        for c in (1, 3, 5):
            f_opt.columnconfigure(c, weight=1)
        ttk.Label(f_opt, text="판정 모드").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        self.mode_var = tk.StringVar(value=next((d for k, d in MODES if k == self.cfg.mode), MODES[0][1]))
        ttk.Combobox(f_opt, textvariable=self.mode_var, values=[d for _, d in MODES], state="readonly", width=48).grid(row=0, column=1, columnspan=3, sticky="w", padx=4)
        ttk.Label(f_opt, text="확신 임계값").grid(row=0, column=4, sticky="e", padx=8)
        self.thr_var = tk.StringVar(value="" if self.cfg.confidence_threshold is None else str(self.cfg.confidence_threshold))
        ttk.Entry(f_opt, textvariable=self.thr_var, width=8).grid(row=0, column=5, sticky="w")
        ttk.Label(f_opt, text="(비우면 제로샷 0.05 / 학습 분류기 0.25)").grid(row=0, column=6, sticky="w", padx=4)

        ttk.Label(f_opt, text="LLM 모델").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        self.model_var = tk.StringVar(value=self.cfg.model)
        self.model_box = ttk.Combobox(f_opt, textvariable=self.model_var, values=[self.cfg.model], width=24)
        self.model_box.grid(row=1, column=1, sticky="w", padx=4)
        ttk.Label(f_opt, text="임베딩 모델").grid(row=1, column=2, sticky="e", padx=8)
        self.embed_var = tk.StringVar(value=self.cfg.embed_model)
        self.embed_box = ttk.Combobox(f_opt, textvariable=self.embed_var, values=[self.cfg.embed_model], width=18)
        self.embed_box.grid(row=1, column=3, sticky="w", padx=4)
        self.cache_var = tk.BooleanVar(value=self.cfg.use_cache)
        ttk.Checkbutton(f_opt, text="캐시 사용 (같은 페이지는 다시 판정하지 않음)", variable=self.cache_var).grid(row=1, column=4, columnspan=3, sticky="w", padx=8)

        ttk.Label(f_opt, text="목록 점수 기준").grid(row=2, column=0, sticky="w", padx=8, pady=4)
        self.accept_var = tk.StringVar(value=str(self.cfg.accept_score))
        ttk.Entry(f_opt, textvariable=self.accept_var, width=8).grid(row=2, column=1, sticky="w", padx=4)
        ttk.Label(f_opt, text="(신뢰도×페이지 가중치. 미만은 보류 시트)").grid(row=2, column=1, sticky="w", padx=(70, 0))
        self.verify_var = tk.BooleanVar(value="A" in self.cfg.verify_set())
        ttk.Checkbutton(f_opt, text="A등급 LLM 재확인 (느려지지만 정밀도 상승)", variable=self.verify_var).grid(row=2, column=2, columnspan=2, sticky="w", padx=8)
        self.verify_b_var = tk.BooleanVar(value="B" in self.cfg.verify_set())
        ttk.Checkbutton(f_opt, text="B등급도 재확인", variable=self.verify_b_var).grid(row=2, column=4, columnspan=3, sticky="w", padx=8)

        ttk.Label(f_opt, text="결과 위치").grid(row=3, column=0, sticky="w", padx=8, pady=4)
        self.out_mode = tk.StringVar(value="beside")
        ttk.Radiobutton(f_opt, text="원본 옆에 저장", variable=self.out_mode, value="beside").grid(row=3, column=1, sticky="w", padx=4)
        ttk.Radiobutton(f_opt, text="지정 폴더:", variable=self.out_mode, value="folder").grid(row=3, column=2, sticky="e", padx=8)
        self.out_dir_var = tk.StringVar(value="")
        ttk.Entry(f_opt, textvariable=self.out_dir_var, width=40).grid(row=3, column=3, columnspan=3, sticky="ew", padx=4)
        ttk.Button(f_opt, text="찾기...", command=self.pick_out_dir).grid(row=3, column=6, sticky="w", padx=4)

        f_run = ttk.Frame(root)
        f_run.grid(row=2, column=0, sticky="ew", padx=6, pady=4)
        self.run_btn = ttk.Button(f_run, text="▶  실행", command=self.start_extract, width=14)
        self.run_btn.pack(side="left", padx=(8, 4))
        self.stop_btn = ttk.Button(f_run, text="중지", command=self.cancel, width=8, state="disabled")
        self.stop_btn.pack(side="left", padx=4)
        self.prog = ttk.Progressbar(f_run, mode="indeterminate", length=220)
        self.prog.pack(side="left", padx=12)
        self.open_xlsx_btn = ttk.Button(f_run, text="결과 Excel 열기", command=self.open_last_output, state="disabled")
        self.open_xlsx_btn.pack(side="right", padx=(4, 8))
        self.open_dir_btn = ttk.Button(f_run, text="결과 폴더 열기", command=self.open_last_folder, state="disabled")
        self.open_dir_btn.pack(side="right", padx=4)

        f_log = ttk.LabelFrame(root, text=" 3. 진행 ")
        f_log.grid(row=3, column=0, sticky="nsew", padx=6, pady=4)
        f_log.columnconfigure(0, weight=1)
        f_log.rowconfigure(0, weight=1)
        self.log = self._text_with_scroll(f_log, height=6)

        f_res = ttk.LabelFrame(root, text=" 4. 결과 미리보기  (검토 목록·보류. 전체 내용과 피드백 열은 Excel) ")
        f_res.grid(row=4, column=0, sticky="nsew", padx=6, pady=(4, 8))
        f_res.columnconfigure(0, weight=1)
        f_res.rowconfigure(1, weight=1)
        top = ttk.Frame(f_res)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(6, 0))
        self.res_title = tk.StringVar(value="아직 결과가 없습니다.")
        ttk.Label(top, textvariable=self.res_title).pack(side="left")
        ttk.Label(top, text="보기").pack(side="right", padx=(8, 4))
        self.filter_var = tk.StringVar(value="검토 목록")
        fb = ttk.Combobox(top, textvariable=self.filter_var, values=["검토 목록", "A", "B", "C", "D", "보류"], state="readonly", width=9)
        fb.pack(side="right")
        fb.bind("<<ComboboxSelected>>", lambda e: self.fill_results())
        cols = ("번호", "섹션", "페이지", "등급", "발췌", "점수", "가중치", "판정", "비고")
        self.tree = self._tree(f_res, cols, (46, 100, 50, 46, 440, 50, 50, 80, 200), height=8, row=1, stretch=("발췌", "비고"))
        for g, color in GRADE_FILL.items():
            self.tree.tag_configure(g, background=color)
        self.tree.tag_configure("hold", background=HOLD_FILL)

    def _build_weights(self, root: ttk.Frame) -> None:
        root.columnconfigure(0, weight=3)
        root.columnconfigure(1, weight=2)
        root.rowconfigure(1, weight=1)
        ttk.Label(root, text="페이지 제목으로 가중치를 정합니다. 문장 점수 = 판정 신뢰도 × 페이지 가중치이고, 점수가 '목록 점수 기준' 미만이면 보류 시트로 갑니다. "
                             "가중치 0은 페이지를 판정하지 않습니다. 규칙은 위에서부터 먼저 맞는 것이 적용되고, 없으면 유형별 기본값을 씁니다.",
                  wraplength=1100, justify="left").grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 4))

        f_pages = ttk.LabelFrame(root, text=" 마지막 실행(또는 미리 보기)의 페이지 ")
        f_pages.grid(row=1, column=0, sticky="nsew", padx=(6, 3), pady=4)
        f_pages.columnconfigure(0, weight=1)
        f_pages.rowconfigure(0, weight=1)
        cols = ("페이지", "제목", "유형", "가중치", "근거", "상태", "목록", "보류")
        self.page_tree = self._tree(f_pages, cols, (50, 300, 70, 55, 120, 150, 45, 45), height=14, stretch=("제목", "상태"))
        pb = ttk.Frame(f_pages)
        pb.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 6))
        ttk.Button(pb, text="보고서 골라 미리 보기 (LLM 없음)", command=self.start_preview_pages).pack(side="left")
        ttk.Label(pb, text="  제목·유형·가중치만 계산합니다. 규칙을 고친 뒤 다시 눌러 확인하세요.").pack(side="left")

        f_rules = ttk.LabelFrame(root, text=" 규칙 ")
        f_rules.grid(row=1, column=1, sticky="nsew", padx=(3, 6), pady=4)
        f_rules.columnconfigure(0, weight=1)
        f_rules.rowconfigure(1, weight=1)
        ttk.Label(f_rules, text="키워드 규칙 (정규식 = 가중치, 한 줄에 하나. 먼저 맞는 것이 적용)").grid(row=0, column=0, sticky="w", padx=8, pady=(6, 0))
        self.rules_text = tk.Text(f_rules, height=8, wrap="none", font=("TkFixedFont", 10))
        self.rules_text.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
        self.rules_text.insert("1.0", rules_text(self.cfg.page_weights))
        f_types = ttk.Frame(f_rules)
        f_types.grid(row=2, column=0, sticky="ew", padx=8, pady=4)
        ttk.Label(f_types, text="유형별 기본 가중치").grid(row=0, column=0, columnspan=4, sticky="w")
        self.type_vars: dict[str, tk.StringVar] = {}
        merged = {**DEFAULT_TYPE_WEIGHTS, **self.cfg.page_type_weights}
        for i, key in enumerate(("means", "result", "problem", "plan", "status", "general")):
            r, c = 1 + i // 2, (i % 2) * 2
            ttk.Label(f_types, text=TYPE_LABEL[key]).grid(row=r, column=c, sticky="w", padx=(0, 4), pady=2)
            var = tk.StringVar(value=str(merged.get(key, 0.8)))
            self.type_vars[key] = var
            ttk.Entry(f_types, textvariable=var, width=6).grid(row=r, column=c + 1, sticky="w", padx=(0, 16))
        f_apply = ttk.Frame(f_rules)
        f_apply.grid(row=3, column=0, sticky="ew", padx=8, pady=(4, 8))
        ttk.Button(f_apply, text="규칙 적용 (이번 세션)", command=self.apply_rules).pack(side="left")
        ttk.Button(f_apply, text="설정 저장...", command=self.save_config).pack(side="left", padx=6)
        ttk.Button(f_apply, text="기본값으로", command=self.reset_rules).pack(side="left")
        self.rules_status = tk.StringVar(value=f"설정 파일: {self.cfg.config_path or '없음 (기본값 사용)'}")
        ttk.Label(f_rules, textvariable=self.rules_status, wraplength=380, justify="left").grid(row=4, column=0, sticky="w", padx=8, pady=(0, 6))

    def _build_quality(self, root: ttk.Frame) -> None:
        root.columnconfigure(0, weight=1)
        root.rowconfigure(4, weight=1)
        f1 = ttk.LabelFrame(root, text=" 1. 골드 시트 만들기  —  보고서를 고르면 모델 초안 라벨이 채워진 엑셀이 생깁니다. '정답' 열에서 틀린 것만 고치세요 ")
        f1.grid(row=0, column=0, sticky="ew", padx=6, pady=(8, 4))
        ttk.Button(f1, text="보고서 선택 → 골드 시트 생성", command=self.start_gold_sheet).pack(side="left", padx=8, pady=8)
        self.gold_open_btn = ttk.Button(f1, text="방금 만든 골드 시트 열기", command=self.open_last_gold, state="disabled")
        self.gold_open_btn.pack(side="left", padx=4)

        f1b = ttk.LabelFrame(root, text=" 2. 결과 Excel의 피드백 가져오기  —  검토 목록·보류·제외 문장 시트의 '피드백' 열(O / X / A~D)을 골드 시트로 합칩니다 ")
        f1b.grid(row=1, column=0, sticky="ew", padx=6, pady=4)
        ttk.Button(f1b, text="결과 Excel 선택 → 골드 시트에 반영", command=self.start_feedback).pack(side="left", padx=8, pady=8)
        self.confirm_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(f1b, text="검토 목록에서 피드백이 빈 행도 '맞음'으로 간주 (목록을 끝까지 검토했을 때만)", variable=self.confirm_var).pack(side="left", padx=4)

        f2 = ttk.LabelFrame(root, text=" 3. 분류기 학습  —  골드 폴더(data\\gold)의 골드 시트는 자동으로 올라옵니다. 골드에 있는 문장은 학습과 별개로 다음 실행부터 정답이 그대로 반영됩니다 ")
        f2.grid(row=2, column=0, sticky="ew", padx=6, pady=4)
        f2.columnconfigure(0, weight=1)
        self.gold_list = tk.Listbox(f2, height=4, selectmode="extended")
        self.gold_list.grid(row=0, column=0, sticky="ew", padx=(8, 4), pady=6)
        b2 = ttk.Frame(f2)
        b2.grid(row=0, column=1, sticky="n", padx=(0, 8), pady=6)
        ttk.Button(b2, text="골드 파일 추가...", command=self.add_gold_dialog, width=16).pack(fill="x", pady=1)
        ttk.Button(b2, text="골드 폴더 열기", command=lambda: open_path(self.cfg.gold_dir()) if self.cfg.gold_dir().exists() else messagebox.showinfo("골드 폴더", f"아직 없습니다: {self.cfg.gold_dir()}"), width=16).pack(fill="x", pady=1)
        ttk.Button(b2, text="선택 제거", command=self.remove_gold_selected, width=16).pack(fill="x", pady=1)
        ttk.Button(b2, text="학습 실행", command=self.start_train, width=16).pack(fill="x", pady=(6, 1))
        self.clf_var = tk.StringVar(value="")
        ttk.Label(f2, textvariable=self.clf_var).grid(row=1, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 6))

        f3 = ttk.LabelFrame(root, text=" 4. 채점  —  골드 시트로 현재 설정의 등급 정확도와 검토 목록 정밀도를 잽니다 ")
        f3.grid(row=3, column=0, sticky="ew", padx=6, pady=4)
        ttk.Label(f3, text="판정 모드").pack(side="left", padx=(8, 4), pady=8)
        self.eval_mode = tk.StringVar(value="hybrid")
        ttk.Combobox(f3, textvariable=self.eval_mode, values=["hybrid", "fast", "llm"], state="readonly", width=8).pack(side="left")
        ttk.Label(f3, text="임계값").pack(side="left", padx=(12, 4))
        self.eval_thr = tk.StringVar(value="")
        ttk.Entry(f3, textvariable=self.eval_thr, width=8).pack(side="left")
        ttk.Button(f3, text="골드 시트 선택 → 채점", command=self.start_eval).pack(side="left", padx=12)
        self.stored_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(f3, text="다시 판정하지 않고 시트에 저장된 라벨만 채점", variable=self.stored_var).pack(side="left")

        f4 = ttk.LabelFrame(root, text=" 출력 ")
        f4.grid(row=4, column=0, sticky="nsew", padx=6, pady=(4, 8))
        f4.columnconfigure(0, weight=1)
        f4.rowconfigure(0, weight=1)
        self.qlog = self._text_with_scroll(f4, height=8, wrap="none")

    def _build_history(self, root: ttk.Frame) -> None:
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=2)
        root.rowconfigure(1, weight=2)
        root.rowconfigure(2, weight=1)
        f_runs = ttk.LabelFrame(root, text=" 실행 이력  —  행을 고르면 아래에 직전 실행과 달라진 설정과 변경 요약이 나옵니다 ")
        f_runs.grid(row=0, column=0, sticky="nsew", padx=6, pady=(8, 4))
        f_runs.columnconfigure(0, weight=1)
        f_runs.rowconfigure(0, weight=1)
        cols = ("시각", "파일", "모드", "LLM", "분류기", "목록", "A", "B", "C", "D", "보류", "진입", "이탈", "등급변경", "설정 변경")
        self.run_tree = self._tree(f_runs, cols, (120, 180, 55, 110, 160, 45, 35, 35, 35, 35, 45, 45, 45, 60, 220), height=7, stretch=("파일", "분류기", "설정 변경"))
        self.run_tree.bind("<<TreeviewSelect>>", lambda e: self.show_run())
        rb = ttk.Frame(f_runs)
        rb.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 6))
        ttk.Button(rb, text="새로 고침", command=self.refresh_history).pack(side="left")
        ttk.Button(rb, text="이력 폴더 열기", command=lambda: self.cfg.history_dir() and open_path(self.cfg.history_dir())).pack(side="left", padx=6)
        self.hist_status = tk.StringVar(value="")
        ttk.Label(rb, textvariable=self.hist_status).pack(side="left", padx=8)

        f_detail = ttk.LabelFrame(root, text=" 선택한 실행의 상세  /  마지막 실행의 변경된 문장 (전체는 결과 Excel '변경 사항' 시트) ")
        f_detail.grid(row=1, column=0, sticky="nsew", padx=6, pady=4)
        f_detail.columnconfigure(0, weight=1)
        f_detail.rowconfigure(1, weight=1)
        self.detail_var = tk.StringVar(value="")
        ttk.Label(f_detail, textvariable=self.detail_var, wraplength=1100, justify="left").grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(6, 0))
        cols = ("변경", "페이지", "줄", "발췌", "이전", "현재", "판정", "설명")
        self.change_tree = self._tree(f_detail, cols, (80, 50, 40, 400, 50, 50, 80, 300), height=6, row=1, stretch=("발췌", "설명"))

        f_fb = ttk.LabelFrame(root, text=" 피드백·학습 이력 ")
        f_fb.grid(row=2, column=0, sticky="nsew", padx=6, pady=(4, 8))
        f_fb.columnconfigure(0, weight=1)
        f_fb.rowconfigure(0, weight=1)
        self.fb_log = self._text_with_scroll(f_fb, height=5, wrap="none")

    # ------------------------------------------------------------------ 공통
    def _log(self, msg: str, where: str = "log") -> None:
        self.q.put(("log", where, msg))

    def _append(self, widget: tk.Text, msg: str) -> None:
        widget.configure(state="normal")
        widget.insert("end", msg + "\n")
        widget.see("end")
        widget.configure(state="disabled")

    def _set_text(self, widget: tk.Text, msg: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("end", msg)
        widget.configure(state="disabled")

    def _poll(self) -> None:
        try:
            while True:
                kind, *rest = self.q.get_nowait()
                if kind == "log":
                    where, msg = rest
                    self._append(self.log if where == "log" else self.qlog, msg)
                elif kind == "status":
                    self.status_var.set(rest[0])
                elif kind == "models":
                    llms, embeds = rest
                    if llms:
                        self.model_box["values"] = llms
                    if embeds:
                        self.embed_box["values"] = embeds
                elif kind == "history":
                    self._fill_history(*rest)
                elif kind == "done":
                    self._finish(*rest)
        except queue.Empty:
            pass
        self.after(120, self._poll)

    def _busy(self) -> bool:
        if self.worker is not None and self.worker.is_alive():
            messagebox.showinfo("실행 중", "작업이 끝난 뒤 다시 시도하세요.")
            return True
        return False

    def _start(self, target, *args) -> None:
        self._cancel.clear()
        self.run_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.prog.start(12)
        self.worker = threading.Thread(target=self._guard, args=(target, *args), daemon=True)
        self.worker.start()

    def _guard(self, target, *args) -> None:
        try:
            result = target(*args)
            self.q.put(("done", "ok", result))
        except Cancelled:
            self.q.put(("done", "cancelled", None))
        except Exception as e:
            self.q.put(("done", "error", f"{e}\n\n{traceback.format_exc()}"))

    def _finish(self, state: str, payload) -> None:
        self.prog.stop()
        self.run_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        if state == "error":
            self._append(self.log, f"[오류] {payload.splitlines()[0]}")
            messagebox.showerror("오류", payload.split("\n\n")[0])
        elif state == "cancelled":
            self._append(self.log, "중지됨. 처리한 페이지는 캐시에 남아 다음 실행에서 재사용됩니다.")
        if not (payload and isinstance(payload, dict)):
            return
        kind = payload.get("kind")
        if kind == "extract":
            self.last_outputs = payload["outputs"]
            self.last_labeled = payload["labeled"]
            self.last_result = payload["result"]
            self.res_title.set(f"최근 결과: {payload['last_name']}  ({payload['summary']})")
            self.fill_results()
            self.fill_pages(payload["result"].doc, payload["labeled"])
            self.fill_changes(payload["result"])
            self.open_xlsx_btn.configure(state="normal" if self.last_outputs else "disabled")
            self.open_dir_btn.configure(state="normal" if self.last_outputs else "disabled")
            self.refresh_history()
        elif kind == "preview":
            self.fill_pages(payload["doc"], [])
            self.nb.select(self.tab_weights)
        elif kind == "gold":
            self.last_gold = payload["path"]
            self.gold_open_btn.configure(state="normal")
            self._add_gold(self.last_gold)
        elif kind == "feedback":
            self._add_gold(Path(payload["gold"]))
            self.refresh_history()
        elif kind == "train":
            self.check_env()
            self.refresh_history()

    def cancel(self) -> None:
        self._cancel.set()
        self._append(self.log, "중지 요청... 현재 단계가 끝나면 멈춥니다.")

    def _check_cancel(self) -> None:
        if self._cancel.is_set():
            raise Cancelled()

    def _on_close(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            if not messagebox.askyesno("종료", "작업이 진행 중입니다. 종료할까요?"):
                return
        self.destroy()

    # ------------------------------------------------------------------ 설정 조립
    def current_rules(self) -> tuple[list[list], dict, float]:
        rules = parse_rules(self.rules_text.get("1.0", "end"))
        types = {}
        for k, var in self.type_vars.items():
            v = float(var.get().strip() or DEFAULT_TYPE_WEIGHTS[k])
            types[k] = max(0.0, min(1.0, v))
        accept = float(self.accept_var.get().strip() or 0.5)
        return rules, types, accept

    def build_cfg(self, mode: str | None = None, threshold: str | None = None) -> Config:
        mode = mode or next(k for k, d in MODES if d == self.mode_var.get())
        thr_text = (self.thr_var.get() if threshold is None else threshold).strip()
        thr = float(thr_text) if thr_text else None
        rules, types, accept = self.current_rules()
        verify = ",".join(g for g, v in (("A", self.verify_var.get()), ("B", self.verify_b_var.get())) if v)
        return Config.load(self.cfg.config_path or None, mode=mode, model=self.model_var.get().strip() or None,
                           embed_model=self.embed_var.get().strip() or None, confidence_threshold=thr, use_cache=self.cache_var.get(),
                           page_weights=rules, page_type_weights=types, accept_score=accept, verify_grades=verify,
                           gold_paths=self.cfg.gold_paths, use_gold=self.cfg.use_gold, history_path=self.cfg.history_path,
                           cache_path=self.cfg.cache_path, classifier_path=self.cfg.classifier_path)

    def apply_rules(self) -> None:
        try:
            rules, types, accept = self.current_rules()
        except ValueError as e:
            messagebox.showerror("규칙 오류", str(e))
            return
        self.cfg.page_weights, self.cfg.page_type_weights, self.cfg.accept_score = rules, types, accept
        self.rules_status.set(f"적용됨: 규칙 {len(rules)}개, 점수 기준 {accept}. 다음 실행부터 반영됩니다 (저장하지 않으면 종료 시 사라짐).")
        if self.last_result is not None:
            self.start_preview_pages(Path(self.last_result.info.source))

    def save_config(self) -> None:
        try:
            cfg = self.build_cfg()
        except ValueError as e:
            messagebox.showerror("규칙 오류", str(e))
            return
        target = Path(self.cfg.config_path) if self.cfg.config_path else USER_CONFIG
        p = filedialog.asksaveasfilename(title="설정 저장", initialdir=str(target.parent), initialfile=target.name,
                                         defaultextension=".toml", filetypes=[("TOML", "*.toml")])
        if not p:
            return
        cfg.config_path = ""
        out = cfg.save(p)
        self.cfg = Config.load(out)
        self.rules_status.set(f"저장: {out}. 설치 폴더의 ip_finder.toml 은 UI와 명령줄이 자동으로 읽고, 다른 위치는 ip-finder --config 로 지정합니다.")

    def reset_rules(self) -> None:
        base = Config()
        self.rules_text.delete("1.0", "end")
        self.rules_text.insert("1.0", rules_text(base.page_weights))
        for k, var in self.type_vars.items():
            var.set(str(DEFAULT_TYPE_WEIGHTS[k]))
        self.accept_var.set(str(base.accept_score))

    # ------------------------------------------------------------------ 환경 점검
    def check_env(self) -> None:
        try:
            cfg = self.build_cfg()          # Tk 변수는 메인 스레드에서만 읽는다
        except ValueError:
            cfg = Config.load()

        def work(cfg=cfg):
            from .classify import OllamaEmbedder
            from .llm import OllamaClient
            parts = []
            try:
                client = OllamaClient(cfg.host, cfg.model, timeout_sec=10)
            except Exception as e:
                self.q.put(("status", f"설정 오류: {e}"))
                return
            if client.available():
                names = client.installed_models()
                llms = [n for n in names if not any(k in n.lower() for k in ("embed", "bge", "e5", "kure", "minilm"))]
                embeds = [n for n in names if n not in llms]
                self.q.put(("models", llms, embeds))
                parts.append("Ollama 연결 ✓")
                parts.append(f"LLM {cfg.model} {'✓' if client.has_model() else '✗ (ollama pull 필요)'}")
                emb = OllamaEmbedder(cfg.host, cfg.embed_model, timeout_sec=10)
                parts.append(f"임베딩 {cfg.embed_model} {'✓' if emb.available() else '✗ (없으면 llm 모드로 동작)'}")
            else:
                parts.append(f"Ollama 연결 ✗ ({cfg.host})  Ollama 를 실행하세요")
            clf = cfg.classifier_file()
            parts.append("분류기: " + (f"학습됨 ({clf.name})" if clf.exists() else "제로샷(원형 문장)"))
            self.q.put(("status", "   |   ".join(parts)))
            self.q.put(("log", "q", f"현재 분류기: {clf if clf.exists() else '제로샷(원형 문장). 골드 시트로 학습하면 바뀝니다.'}"))
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------------ 추출 탭 동작
    def add_files(self, paths) -> None:
        existing = set(self.files_list.get(0, "end"))
        for p in paths:
            p = str(p)
            if p and p not in existing and Path(p).suffix.lower() in SUPPORTED:
                self.files_list.insert("end", p)
                existing.add(p)

    def add_files_dialog(self) -> None:
        paths = filedialog.askopenfilenames(title="보고서 선택", filetypes=[("보고서", "*.pdf *.pptx *.ppt"), ("PDF", "*.pdf"), ("PowerPoint", "*.pptx *.ppt"), ("모든 파일", "*.*")])
        self.add_files(paths)

    def add_folder_dialog(self) -> None:
        d = filedialog.askdirectory(title="보고서 폴더 선택")
        if d:
            existing = set(self.files_list.get(0, "end"))
            if d not in existing:
                self.files_list.insert("end", d)

    def remove_selected(self) -> None:
        for i in reversed(self.files_list.curselection()):
            self.files_list.delete(i)

    def pick_out_dir(self) -> None:
        d = filedialog.askdirectory(title="결과 폴더 선택")
        if d:
            self.out_dir_var.set(d)
            self.out_mode.set("folder")

    def start_extract(self) -> None:
        if self._busy():
            return
        inputs = [Path(p) for p in self.files_list.get(0, "end")]
        if not inputs:
            messagebox.showinfo("입력 없음", "먼저 보고서 파일이나 폴더를 추가하세요.")
            return
        try:
            cfg = self.build_cfg()
        except ValueError as e:
            messagebox.showerror("옵션 오류", f"임계값·점수 기준은 숫자, 가중치 규칙은 '패턴 = 가중치' 형식이어야 합니다.\n{e}")
            return
        out_dir = Path(self.out_dir_var.get()) if self.out_mode.get() == "folder" and self.out_dir_var.get().strip() else None
        self._start(self._extract_job, inputs, cfg, out_dir)

    def _extract_job(self, inputs: list[Path], cfg: Config, out_dir: Path | None) -> dict:
        import time
        from collections import Counter
        from .cli import _summary
        from .pipeline import extract, find_inputs, make_client, output_path
        files = find_inputs(inputs)
        if not files:
            raise RuntimeError("처리할 파일이 없습니다 (.pdf, .pptx, .ppt)")
        client = make_client(cfg)
        if not client.available():
            raise RuntimeError(f"Ollama 에 연결할 수 없습니다 ({cfg.host}). Ollama 를 실행한 뒤 다시 시도하세요.")
        taken = Counter(output_path(f, out_dir) for f in files)
        outputs: list[Path] = []
        labeled: list[LabeledLine] = []
        result = None
        last_name, summary = "", ""
        t_all = time.time()
        self._log(f"== {len(files)}개 파일, 모드 {cfg.mode}, LLM {cfg.model}, 임베딩 {cfg.embed_model}, 점수 기준 {cfg.accept_score}"
                  + (f", 재확인 {cfg.verify_grades}" if cfg.verify_grades else ""))
        for f in files:
            self._check_cancel()
            t0 = time.time()
            self._log(f"\n== {f.name}")

            def progress(k, n, page, _t0=t0):
                self._check_cancel()
                self._log(f"  [{k:>2}/{n}] p{page.no:<3} {page.title[:40]:<40} {time.time() - _t0:5.0f}s")

            def status(msg, _t0=t0):
                self._check_cancel()
                self._log(f"  {msg}  {time.time() - _t0:5.0f}s")

            out, res = extract(f, cfg, out_dir, client, progress, with_ext=taken[output_path(f, out_dir)] > 1, status=status)
            i = res.info
            summary = (f"{i.mode} | 페이지 {i.pages_total} (판정 {i.pages_labeled}, 제외 {i.pages_excluded}, 이미지 {i.pages_image}) | "
                       f"분류기 {i.clf_lines} LLM {i.llm_lines} 호출 {i.llm_calls} 캐시 {i.cache_hits} | {i.elapsed_sec:.0f}초")
            self._log(f"  → {out}\n  {summary}\n  {_summary(res)}")
            for s in i.settings_diff:
                self._log(f"  달라진 설정: {s}")
            for w in i.warnings:
                self._log(f"  경고: {w}")
            outputs.append(out)
            labeled, result, last_name = res.labeled, res, f.name
        if len(files) > 1:
            self._log(f"\n총 {len(files)}개 파일, {time.time() - t_all:.0f}초")
        return {"kind": "extract", "outputs": outputs, "labeled": labeled, "result": result, "last_name": last_name, "summary": summary}

    def fill_results(self) -> None:
        self.tree.delete(*self.tree.get_children())
        want = self.filter_var.get()
        n = 0
        for ll in self.last_labeled:
            if want == "보류":
                if not in_hold_list(ll):
                    continue
                tag = "hold"
            else:
                if not in_review_list(ll) or (want != "검토 목록" and ll.label != want):
                    continue
                tag = ll.label
            n += 1
            note = ll.hold_reason if want == "보류" and ll.hold_reason else ", ".join(ll.notes)
            self.tree.insert("", "end", values=(n, ll.section, ll.page_no, ll.label, ll.text, f"{ll.score:.2f}", f"{ll.page_weight:.2f}",
                                                SOURCE_NAME.get(ll.source, ll.source), note), tags=(tag,))

    def fill_pages(self, doc, labeled: list[LabeledLine]) -> None:
        from .prep.page_type import page_type
        self.page_tree.delete(*self.page_tree.get_children())
        by_page: dict[int, list[LabeledLine]] = {}
        for ll in labeled:
            by_page.setdefault(ll.page_no, []).append(ll)
        for p in doc.pages:
            rows = by_page.get(p.no, [])
            state = p.excluded_reason or ("판정" if labeled else f"판정 대상 {len(p.active_lines())}문장")
            self.page_tree.insert("", "end", values=(p.no, p.title, page_type(p.title)[0], f"{p.weight:.2f}", p.weight_reason, state,
                                                     sum(1 for ll in rows if in_review_list(ll)) if labeled else "",
                                                     sum(1 for ll in rows if in_hold_list(ll)) if labeled else ""))

    def start_preview_pages(self, path: Path | None = None) -> None:
        if self._busy():
            return
        if path is None:
            p = filedialog.askopenfilename(title="가중치를 미리 볼 보고서", filetypes=[("보고서", "*.pdf *.pptx *.ppt")])
            if not p:
                return
            path = Path(p)
        try:
            cfg = self.build_cfg()
        except ValueError as e:
            messagebox.showerror("규칙 오류", str(e))
            return
        self._start(self._preview_job, path, cfg)

    def _preview_job(self, path: Path, cfg: Config) -> dict:
        from .pipeline import prepare
        from .readers import load_document
        doc = load_document(path)
        prepare(doc, cfg)
        return {"kind": "preview", "doc": doc}

    def open_last_output(self) -> None:
        if self.last_outputs:
            open_path(self.last_outputs[-1])

    def open_last_folder(self) -> None:
        if self.last_outputs:
            open_path(self.last_outputs[-1].parent)

    # ------------------------------------------------------------------ 정확도 관리 탭 동작
    def _add_gold(self, path: Path) -> None:
        if path not in self.gold_files:
            self.gold_files.append(path)
            self.gold_list.insert("end", str(path))

    def load_gold_folder(self) -> None:
        """골드 폴더의 *_gold.xlsx 를 학습 목록에 올린다."""
        try:
            for p in self.cfg.gold_files():
                self._add_gold(p)
        except Exception:
            pass

    def start_gold_sheet(self) -> None:
        if self._busy():
            return
        p = filedialog.askopenfilename(title="골드 시트를 만들 보고서", filetypes=[("보고서", "*.pdf *.pptx *.ppt")])
        if not p:
            return
        cfg = self.build_cfg()
        self._start(self._gold_job, Path(p), cfg)

    def _gold_job(self, path: Path, cfg: Config) -> dict:
        from .eval import make_gold_sheet
        from .pipeline import make_client
        client = make_client(cfg)
        if not client.available():
            raise RuntimeError(f"Ollama 에 연결할 수 없습니다 ({cfg.host}).")
        self._log(f"골드 시트 생성 중: {path.name} (모드 {cfg.mode})", "q")
        out = make_gold_sheet(path, cfg, None, client)
        self._log(f"생성: {out}\n'라벨링' 시트의 '정답' 열에서 틀린 등급만 고친 뒤 저장하세요. 골드 폴더 안의 골드는 다음 실행부터 자동 반영됩니다 (같은 문장은 정답 그대로).", "q")
        return {"kind": "gold", "path": out}

    def open_last_gold(self) -> None:
        if self.last_gold:
            open_path(self.last_gold)

    def start_feedback(self) -> None:
        if self._busy():
            return
        p = filedialog.askopenfilename(title="피드백을 적은 결과 Excel", filetypes=[("결과 Excel", "*_검토후보.xlsx"), ("Excel", "*.xlsx")])
        if not p:
            return
        cfg = self.build_cfg()
        self._start(self._feedback_job, Path(p), cfg, self.confirm_var.get())

    def _feedback_job(self, result: Path, cfg: Config, confirm: bool) -> dict:
        from .eval import import_feedback
        from .history import History
        rec = import_feedback(result, None, confirm_unmarked=confirm, history=History(cfg.history_dir()), gold_dir=cfg.gold_dir())
        msg = (f"피드백 {rec['feedback_rows']}행 → 골드 시트 {rec['gold']}\n  추가 {rec['added']}, 갱신 {rec['updated']}, 건너뜀 {rec['skipped']}, 골드 총 {rec['gold_rows']}행")
        if rec["corrections"]:
            msg += "\n  내역: " + ", ".join(f"{k} {v}" for k, v in sorted(rec["corrections"].items()))
        if rec["feedback_rows"] == 0:
            msg += "\n  피드백 열이 비어 있습니다. 결과 Excel의 '피드백' 열에 O / X / A~D 를 적고 저장한 뒤 다시 하세요."
        else:
            msg += "\n  다음 실행부터 이 문장들은 골드 정답을 그대로 씁니다. 분류기까지 갱신하려면 3번에서 학습하세요. 같은 보고서를 다시 추출하면 '변경 사항' 시트에 달라진 행이 나옵니다."
        self._log(msg, "q")
        return {"kind": "feedback", "gold": rec["gold"]}

    def add_gold_dialog(self) -> None:
        for p in filedialog.askopenfilenames(title="골드 시트 선택", filetypes=[("Excel", "*.xlsx")]):
            self._add_gold(Path(p))

    def remove_gold_selected(self) -> None:
        for i in reversed(self.gold_list.curselection()):
            self.gold_files.pop(i)
            self.gold_list.delete(i)

    def start_train(self) -> None:
        if self._busy():
            return
        if not self.gold_files:
            messagebox.showinfo("골드 시트 없음", "먼저 정답을 채운 골드 시트를 추가하세요.")
            return
        cfg = self.build_cfg()
        self._start(self._train_job, list(self.gold_files), cfg)

    def _train_job(self, golds: list[Path], cfg: Config) -> dict:
        from .cache import LabelCache
        from .eval import train_classifier
        from .pipeline import make_embedder
        cache = LabelCache(cfg.cache_file() if cfg.use_cache else None)
        try:
            emb = make_embedder(cfg, cache)
            if not emb.available():
                raise RuntimeError(f"임베딩 모델 {cfg.embed_model} 을 쓸 수 없습니다 → ollama pull {cfg.embed_model}")
            self._log(f"학습 중: {', '.join(g.name for g in golds)}", "q")
            stats = train_classifier(golds, cfg, cfg.classifier_file(), emb)
        finally:
            cache.close()
        self._log(f"학습 문장 {stats['n']}개 (등급별 {stats['counts']})\n5겹 교차검증 정확도 {stats['cv_accuracy']:.1%}, 학습 데이터 정확도 {stats['train_accuracy']:.1%}\n"
                  f"저장: {stats['out']}  → 이제 hybrid/fast 모드가 이 분류기를 씁니다. 아래 4번에서 채점해 확인하세요." +
                  ("\n참고: 문장 100개 미만이면 교차검증 값이 크게 흔들립니다. 보고서를 더 라벨링해 다시 학습하세요." if stats["n"] < 100 else ""), "q")
        return {"kind": "train"}

    def start_eval(self) -> None:
        if self._busy():
            return
        p = filedialog.askopenfilename(title="채점할 골드 시트", filetypes=[("Excel", "*.xlsx")])
        if not p:
            return
        try:
            cfg = self.build_cfg(mode=self.eval_mode.get(), threshold=self.eval_thr.get())
        except ValueError:
            messagebox.showerror("옵션 오류", "임계값은 숫자여야 합니다.")
            return
        self._start(self._eval_job, Path(p), cfg, self.stored_var.get())

    def _eval_job(self, gold: Path, cfg: Config, stored: bool) -> dict:
        from .eval import evaluate, print_report
        from .pipeline import make_client
        client = None
        if not stored:
            client = make_client(cfg)
            if not client.available():
                raise RuntimeError(f"Ollama 에 연결할 수 없습니다 ({cfg.host}).")
        self._log(f"채점 중: {gold.name} (모드 {cfg.mode}{', 저장된 라벨' if stored else ''}, 점수 기준 {cfg.accept_score})", "q")
        rep = evaluate(gold, cfg, rerun=not stored, client=client)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_report(rep)
        self._log(buf.getvalue(), "q")
        return {"kind": "eval"}

    # ------------------------------------------------------------------ 변경 추적 탭 동작
    def refresh_history(self) -> None:
        cfg = self.cfg

        def work():
            from .history import History
            h = History(cfg.history_dir())
            self.q.put(("history", h.list_runs(limit=100), h.feedback_log(), h.train_log(), str(h.root or "")))
        threading.Thread(target=work, daemon=True).start()

    def _fill_history(self, runs: list[dict], feedback: list[dict], train: list[dict], root: str) -> None:
        self.runs = runs
        self.run_tree.delete(*self.run_tree.get_children())
        for r in runs:
            st, s, ch = r.get("stats", {}), r.get("settings", {}), r.get("changes") or {}
            has_prev = bool(r.get("prev_run_id"))
            self.run_tree.insert("", "end", iid=r.get("run_id"), values=(
                str(r.get("started_at", "")).replace("T", " ")[:16], r.get("source_name", ""), s.get("mode", ""), s.get("model", ""),
                str(s.get("classifier", ""))[:40], st.get("list", 0), st.get("A", 0), st.get("B", 0), st.get("C", 0), st.get("D", 0), st.get("held", 0),
                ch.get("entered", "") if has_prev else "-", ch.get("left", "") if has_prev else "-", ch.get("grade", "") if has_prev else "-",
                "; ".join(r.get("settings_diff", []))[:200] if has_prev else "(첫 실행)"))
        self.hist_status.set(f"실행 {len(runs)}건, 피드백 {len(feedback)}건, 학습 {len(train)}건  ({root})")
        lines = []
        for f in feedback[-30:]:
            lines.append(f"[피드백] {f.get('time', '')}  {Path(f.get('result', '')).name} → {Path(f.get('gold', '')).name}: {f.get('feedback_rows', 0)}행  "
                         + ", ".join(f"{k} {v}" for k, v in sorted((f.get("corrections") or {}).items())))
        for t in train[-30:]:
            lines.append(f"[학습]   {t.get('time', '')}  {t.get('n', 0)}문장, 교차검증 {t.get('cv_accuracy', 0):.1%}, 골드 {len(t.get('sources', []))}개 → {t.get('out', '')}")
        self._set_text(self.fb_log, "\n".join(sorted(lines, key=lambda s: s[9:28])) or "아직 피드백·학습 이력이 없습니다.")

    def show_run(self) -> None:
        sel = self.run_tree.selection()
        if not sel:
            return
        r = next((x for x in self.runs if x.get("run_id") == sel[0]), None)
        if r is None:
            return
        s, st = r.get("settings", {}), r.get("stats", {})
        parts = [f"{r.get('run_id')}  {r.get('source_name')}  —  {s.get('mode')} / LLM {s.get('model')} / 임베딩 {s.get('embed_model')} / 분류기 {s.get('classifier')} / "
                 f"프롬프트 {s.get('prompt_version')} / 점수 기준 {s.get('accept_score')} / 재확인 {s.get('verify_grades') or '없음'} / 가중치 규칙 {len(s.get('page_weights') or [])}개",
                 f"목록 {st.get('list', 0)} (A{st.get('A', 0)} B{st.get('B', 0)} C{st.get('C', 0)} D{st.get('D', 0)}), 보류 {st.get('held', 0)}, 문장 {st.get('lines', 0)}, LLM 호출 {st.get('llm_calls', 0)}, {r.get('elapsed_sec', 0)}초"]
        if r.get("prev_run_id"):
            ch = r.get("changes") or {}
            parts.append(f"직전 실행 {r['prev_run_id']} 대비: 목록 진입 {ch.get('entered', 0)}, 이탈 {ch.get('left', 0)}, 등급 변경 {ch.get('grade', 0)}, 점수 변경 {ch.get('score', 0)}, 문장 변경 {ch.get('text', 0)}")
            parts.append("달라진 설정: " + ("; ".join(r.get("settings_diff", [])) or "없음"))
        else:
            parts.append("이 파일의 첫 실행이라 비교 대상이 없습니다.")
        self.detail_var.set("\n".join(parts))

    def fill_changes(self, result) -> None:
        self.change_tree.delete(*self.change_tree.get_children())
        for c in getattr(result, "changes", []) or []:
            self.change_tree.insert("", "end", values=(c["kind"], c["page"], c["line"], c["text"], c["old"], c["new"], c["source"], c["desc"]))
        if result is not None and result.info.prev_run_id and not result.changes:
            self.change_tree.insert("", "end", values=("", "", "", "직전 실행과 달라진 문장이 없습니다.", "", "", "", ""))


def main(argv: list[str] | None = None) -> int:
    app = App()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
