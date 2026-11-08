"""IP Finder 데스크톱 UI (Tkinter). 추가 설치 없이 동작한다.
실행: python -m ip_finder.ui  /  ip-finder ui  /  윈도우 ui.bat
탭 1 '추출': 파일·폴더 선택 → 옵션(1차 분류기, 임베딩 모델, 점수 기준) → 스위치(읽기·전처리·후처리 규칙 하나하나) → 실행 → 진행 로그 → 결과 미리보기 → Excel 열기
탭 2 '페이지 가중치': 마지막 실행의 페이지별 제목·관련성·가중치 표, 낮음·높음 키워드와 낮음 가중치·점수 기준 편집, 설정 저장
탭 3 '정확도 관리': 골드 시트 만들기 → 결과 Excel 피드백 가져오기 → 분류기 학습 → 채점 → 분류기 비교
탭 4 '실험': 사다리 실행(스위치를 한 칸씩 켜며 비교), 결과 비교(결과 파일·폴더 둘을 문장 단위로 비교)
탭 5 '변경 추적': 실행 이력(설정 차이, 직전 대비 변경), 마지막 실행의 변경 행, 피드백·학습 이력"""
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

from . import STAGE, __version__
from .cancel import CancelToken, Cancelled
from .config import CLASSIFIER_NAMES, CONFIG_NAME, Config, app_root
from .models import LabeledLine
from .post import STATUS_CLF_OUT, STATUS_HOLD, STATUS_POST_OUT, STATUS_REVIEW, in_hold_list, in_review_list, is_stage1_out, is_stage2_out
from .readers import SUPPORTED
from .switches import GROUPS, SWITCHES, describe as describe_switches

GRADE_FILL = {"A": "#FFE0B2", "B": "#FFF9C4", "C": "#DCEDC8", "D": "#BBDEFB"}
HOLD_FILL = "#EEEEEE"
SOURCE_NAME = {"clf": "분류기", "gold": "골드"}
VIEWS = [STATUS_REVIEW, "A", "B", "C", "D", STATUS_HOLD, STATUS_CLF_OUT, STATUS_POST_OUT]
GRADE_CHOICES = [("A,B", "A·B  —  수단·효과만 (기본)"), ("A,B,C,D", "A·B·C·D  —  과제·계획까지")]
CLASSIFIER_CHOICES = [(k, f"{k}  —  {v}") for k, v in CLASSIFIER_NAMES.items()]
USER_CONFIG = app_root() / CONFIG_NAME     # 설치 폴더의 ip_finder.toml (설치본마다 따로)


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


def parse_patterns(text: str) -> list[str]:
    """제목 정규식, 한 줄에 하나. # 으로 시작하면 주석. 잘못된 정규식은 오류."""
    import re
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            re.compile(line)
        except re.error as e:
            raise ValueError(f"정규식 오류: {line} ({e})") from None
        out.append(line)
    return out


def patterns_text(patterns: list[str]) -> str:
    return "\n".join(patterns)


class App(tk.Tk):
    def __init__(self, cfg: Config | None = None):
        super().__init__()
        self.cfg = cfg or Config.load()
        self.title(f"IP Finder {__version__}  —  특허 검토 후보 추출 (온디바이스)  |  {STAGE}")
        self.geometry("1220x860")
        self.minsize(980, 680)
        self.q: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self._cancel = CancelToken()
        self.last_outputs: list[Path] = []
        self.last_labeled: list[LabeledLine] = []
        self.last_result = None
        self.gold_files: list[Path] = []
        self.last_gold: Path | None = None
        self.last_experiment: Path | None = None
        self.runs: list[dict] = []
        self.switch_vars: dict[str, tk.BooleanVar] = {s.name: tk.BooleanVar(value=bool(getattr(self.cfg, s.field))) for s in SWITCHES}
        self.baseline_var = tk.BooleanVar(value=self.cfg.baseline_classifiers)     # 기준선 분류기(cue·ngram)를 선택지·비교에 넣을지
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
        self.tab_experiment = ttk.Frame(nb)
        self.tab_history = ttk.Frame(nb)
        nb.add(self.tab_extract, text="  추출  ")
        nb.add(self.tab_weights, text="  페이지 가중치  ")
        nb.add(self.tab_quality, text="  정확도 관리  ")
        nb.add(self.tab_experiment, text="  실험  ")
        nb.add(self.tab_history, text="  변경 추적  ")
        self._build_extract(self.tab_extract)
        self._build_weights(self.tab_weights)
        self._build_quality(self.tab_quality)
        self._build_experiment(self.tab_experiment)
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
        root.rowconfigure(4, weight=1)
        root.rowconfigure(5, weight=2)

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
        ttk.Label(f_opt, text="1차 분류기").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        self.clf_var = tk.StringVar(value=next((d for k, d in CLASSIFIER_CHOICES if k == self.cfg.classifier), CLASSIFIER_CHOICES[0][1]))
        self.clf_box = ttk.Combobox(f_opt, textvariable=self.clf_var, values=self.classifier_choices(), state="readonly", width=44)
        self.clf_box.grid(row=0, column=1, columnspan=3, sticky="w", padx=4)
        ttk.Label(f_opt, text="임베딩 모델").grid(row=0, column=4, sticky="e", padx=8)
        self.embed_var = tk.StringVar(value=self.cfg.embed_model)
        self.embed_box = ttk.Combobox(f_opt, textvariable=self.embed_var, values=[self.cfg.embed_model], width=18)
        self.embed_box.grid(row=0, column=5, sticky="w", padx=4)
        ttk.Label(f_opt, text="추출 등급").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        cur = ",".join(self.cfg.targets())
        self.grades_var = tk.StringVar(value=next((d for k, d in GRADE_CHOICES if k == cur), GRADE_CHOICES[0][1]))
        ttk.Combobox(f_opt, textvariable=self.grades_var, values=[d for _, d in GRADE_CHOICES], state="readonly", width=30).grid(row=1, column=1, sticky="w", padx=4)
        ttk.Label(f_opt, text="목록 점수 기준").grid(row=1, column=2, sticky="e", padx=8)
        self.accept_var = tk.StringVar(value=str(self.cfg.accept_score))
        ttk.Entry(f_opt, textvariable=self.accept_var, width=8).grid(row=1, column=3, sticky="w", padx=4)
        ttk.Label(f_opt, text="(신뢰도×가중치, 미만은 보류)").grid(row=1, column=3, sticky="w", padx=(70, 0))
        self.cache_var = tk.BooleanVar(value=self.cfg.use_cache)
        ttk.Checkbutton(f_opt, text="임베딩 캐시 사용", variable=self.cache_var).grid(row=1, column=4, columnspan=2, sticky="w", padx=8)
        ttk.Label(f_opt, text="결과 위치").grid(row=2, column=0, sticky="w", padx=8, pady=4)
        self.out_mode = tk.StringVar(value="beside")
        ttk.Radiobutton(f_opt, text="원본 옆에 저장", variable=self.out_mode, value="beside").grid(row=2, column=1, sticky="w", padx=4)
        ttk.Radiobutton(f_opt, text="지정 폴더:", variable=self.out_mode, value="folder").grid(row=2, column=2, sticky="e", padx=8)
        self.out_dir_var = tk.StringVar(value="")
        ttk.Entry(f_opt, textvariable=self.out_dir_var, width=40).grid(row=2, column=3, columnspan=3, sticky="ew", padx=4)
        ttk.Button(f_opt, text="찾기...", command=self.pick_out_dir).grid(row=2, column=6, sticky="w", padx=4)

        f_sw = ttk.LabelFrame(root, text=" 3. 스위치  —  읽기·전처리·후처리 규칙을 하나씩 켜고 끕니다. 전부 끄면 기준선(아무 규칙도 없음) ")
        f_sw.grid(row=2, column=0, sticky="ew", padx=6, pady=4)
        for gi, group in enumerate(GROUPS):
            col = ttk.Frame(f_sw)
            col.grid(row=0, column=gi, sticky="nw", padx=10, pady=4)
            ttk.Label(col, text=group, font=("TkDefaultFont", 9, "bold")).pack(anchor="w")
            for s in SWITCHES:
                if s.group == group:
                    ttk.Checkbutton(col, text=s.label, variable=self.switch_vars[s.name]).pack(anchor="w")
        sb = ttk.Frame(f_sw)
        sb.grid(row=0, column=len(GROUPS), sticky="ne", padx=10, pady=4)
        ttk.Button(sb, text="전부 켬", command=lambda: self.set_switches(True), width=10).pack(fill="x", pady=1)
        ttk.Button(sb, text="전부 끔 (기준선)", command=lambda: self.set_switches(False), width=14).pack(fill="x", pady=1)
        self.short_var = tk.StringVar(value=str(self.cfg.short_line_chars))
        f_short = ttk.Frame(sb)
        f_short.pack(anchor="w", pady=(6, 0))
        ttk.Label(f_short, text="짧은 줄 기준").pack(side="left")
        ttk.Entry(f_short, textvariable=self.short_var, width=4).pack(side="left", padx=3)
        ttk.Label(f_short, text="자 이하").pack(side="left")
        self.pw_var = self.switch_vars["page_weight"]     # 페이지 가중치 탭과 같은 변수

        f_run = ttk.Frame(root)
        f_run.grid(row=3, column=0, sticky="ew", padx=6, pady=4)
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

        f_log = ttk.LabelFrame(root, text=" 4. 진행 ")
        f_log.grid(row=4, column=0, sticky="nsew", padx=6, pady=4)
        f_log.columnconfigure(0, weight=1)
        f_log.rowconfigure(0, weight=1)
        self.log = self._text_with_scroll(f_log, height=5)

        f_res = ttk.LabelFrame(root, text=" 5. 결과 미리보기  —  '분류기 제외'는 분류기가 대상 등급 밖으로 본 문장, '전처리 제외'는 Excel 시트에서 봅니다. 피드백은 Excel 에서 ")
        f_res.grid(row=5, column=0, sticky="nsew", padx=6, pady=(4, 8))
        f_res.columnconfigure(0, weight=1)
        f_res.rowconfigure(1, weight=1)
        top = ttk.Frame(f_res)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(6, 0))
        self.res_title = tk.StringVar(value="아직 결과가 없습니다.")
        ttk.Label(top, textvariable=self.res_title).pack(side="left")
        ttk.Label(top, text="보기").pack(side="right", padx=(8, 4))
        self.filter_var = tk.StringVar(value=STATUS_REVIEW)
        fb = ttk.Combobox(top, textvariable=self.filter_var, values=VIEWS, state="readonly", width=14)
        fb.pack(side="right")
        fb.bind("<<ComboboxSelected>>", lambda e: self.fill_results())
        cols = ("번호", "섹션", "페이지", "등급", "발췌", "점수", "가중치", "확신", "판정", "비고")
        self.tree = self._tree(f_res, cols, (46, 100, 50, 46, 420, 50, 50, 50, 60, 220), height=8, row=1, stretch=("발췌", "비고"))
        for g, color in GRADE_FILL.items():
            self.tree.tag_configure(g, background=color)
        self.tree.tag_configure("hold", background=HOLD_FILL)

    def _build_weights(self, root: ttk.Frame) -> None:
        root.columnconfigure(0, weight=3)
        root.columnconfigure(1, weight=2)
        root.rowconfigure(1, weight=1)
        ttk.Label(root, text="페이지 제목으로 관련성을 '높음' 또는 '낮음' 둘 중 하나로 정합니다(페이지 가중치 스위치를 켰을 때). 제목이 '낮음 키워드'에 걸리면 낮음(가중치 아래 값), 아니면 높음(1.0). "
                             "문장 점수 = 판정 신뢰도 × 페이지 가중치이고, 점수가 '목록 점수 기준' 미만이면 보류 시트로 갑니다. 낮음 가중치 0은 그 페이지를 판정하지 않습니다.",
                  wraplength=1100, justify="left").grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 4))

        f_pages = ttk.LabelFrame(root, text=" 마지막 실행(또는 미리 보기)의 페이지 ")
        f_pages.grid(row=1, column=0, sticky="nsew", padx=(6, 3), pady=4)
        f_pages.columnconfigure(0, weight=1)
        f_pages.rowconfigure(0, weight=1)
        cols = ("페이지", "제목", "관련성", "가중치", "근거", "상태", "목록", "보류", "분류기 제외", "후처리 제외")
        self.page_tree = self._tree(f_pages, cols, (50, 280, 55, 55, 120, 140, 45, 45, 70, 70), height=14, stretch=("제목", "상태"))
        self.page_tree.tag_configure("low", background=HOLD_FILL)
        pb = ttk.Frame(f_pages)
        pb.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 6))
        ttk.Button(pb, text="보고서 골라 미리 보기 (분류기 없음)", command=self.start_preview_pages).pack(side="left")
        ttk.Label(pb, text="  제목·관련성·가중치·제외 여부만 계산합니다. 키워드나 스위치를 고친 뒤 다시 눌러 확인하세요.").pack(side="left")

        f_rules = ttk.LabelFrame(root, text=" 규칙 ")
        f_rules.grid(row=1, column=1, sticky="nsew", padx=(3, 6), pady=4)
        f_rules.columnconfigure(0, weight=1)
        f_rules.rowconfigure(2, weight=2)
        f_rules.rowconfigure(4, weight=1)
        f_sw = ttk.Frame(f_rules)
        f_sw.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 2))
        ttk.Checkbutton(f_sw, text="페이지 가중치 적용", variable=self.pw_var).pack(side="left")
        ttk.Label(f_sw, text="    관련성 낮음 가중치").pack(side="left")
        self.low_var = tk.StringVar(value=str(self.cfg.low_relevance_weight))
        ttk.Entry(f_sw, textvariable=self.low_var, width=6).pack(side="left", padx=4)
        ttk.Label(f_sw, text="(0 = 판정 안 함)").pack(side="left")
        ttk.Label(f_rules, text="관련성 낮음 제목 키워드 (정규식, 한 줄에 하나)").grid(row=1, column=0, sticky="w", padx=8, pady=(6, 0))
        self.low_text = tk.Text(f_rules, height=6, wrap="none", font=("TkFixedFont", 10))
        self.low_text.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)
        self.low_text.insert("1.0", patterns_text(self.cfg.low_relevance_patterns))
        ttk.Label(f_rules, text="관련성 높음으로 강제할 제목 키워드 (낮음보다 우선, 비워도 됨)").grid(row=3, column=0, sticky="w", padx=8, pady=(6, 0))
        self.high_text = tk.Text(f_rules, height=3, wrap="none", font=("TkFixedFont", 10))
        self.high_text.grid(row=4, column=0, sticky="nsew", padx=8, pady=4)
        self.high_text.insert("1.0", patterns_text(self.cfg.high_relevance_patterns))
        f_apply = ttk.Frame(f_rules)
        f_apply.grid(row=5, column=0, sticky="ew", padx=8, pady=(4, 8))
        ttk.Button(f_apply, text="규칙 적용 (이번 세션)", command=self.apply_rules).pack(side="left")
        ttk.Button(f_apply, text="설정 저장...", command=self.save_config).pack(side="left", padx=6)
        ttk.Button(f_apply, text="기본값으로", command=self.reset_rules).pack(side="left")
        self.rules_status = tk.StringVar(value=f"설정 파일: {self.cfg.config_path or '없음 (기본값 사용)'}")
        ttk.Label(f_rules, textvariable=self.rules_status, wraplength=380, justify="left").grid(row=6, column=0, sticky="w", padx=8, pady=(0, 6))

    def _build_quality(self, root: ttk.Frame) -> None:
        root.columnconfigure(0, weight=1)
        root.rowconfigure(4, weight=1)
        f1 = ttk.LabelFrame(root, text=" 1. 골드 시트 만들기  —  보고서를 고르면 분류기 초안 라벨이 채워진 엑셀이 생깁니다. '정답' 열에서 틀린 것만 고치세요 ")
        f1.grid(row=0, column=0, sticky="ew", padx=6, pady=(8, 4))
        ttk.Button(f1, text="보고서 선택 → 골드 시트 생성", command=self.start_gold_sheet).pack(side="left", padx=8, pady=8)
        self.gold_open_btn = ttk.Button(f1, text="방금 만든 골드 시트 열기", command=self.open_last_gold, state="disabled")
        self.gold_open_btn.pack(side="left", padx=4)

        f1b = ttk.LabelFrame(root, text=" 2. 결과 Excel 의 피드백 가져오기  —  검토 목록·보류·제외 시트의 '피드백' 열(O / X / A~D)을 골드 시트로 합칩니다 ")
        f1b.grid(row=1, column=0, sticky="ew", padx=6, pady=4)
        ttk.Button(f1b, text="결과 Excel 선택 → 골드 시트에 반영", command=self.start_feedback).pack(side="left", padx=8, pady=8)
        self.confirm_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(f1b, text="검토 목록에서 피드백이 빈 행도 '맞음'으로 간주 (목록을 끝까지 검토했을 때만)", variable=self.confirm_var).pack(side="left", padx=4)

        f2 = ttk.LabelFrame(root, text=" 3. 분류기 학습·비교  —  골드 폴더(data\\gold)의 골드 시트는 자동으로 올라옵니다 ")
        f2.grid(row=2, column=0, sticky="ew", padx=6, pady=4)
        f2.columnconfigure(0, weight=1)
        self.gold_list = tk.Listbox(f2, height=4, selectmode="extended")
        self.gold_list.grid(row=0, column=0, sticky="ew", padx=(8, 4), pady=6)
        b2 = ttk.Frame(f2)
        b2.grid(row=0, column=1, sticky="n", padx=(0, 8), pady=6)
        ttk.Button(b2, text="골드 파일 추가...", command=self.add_gold_dialog, width=18).pack(fill="x", pady=1)
        ttk.Button(b2, text="골드 폴더 열기", command=lambda: open_path(self.cfg.gold_dir()) if self.cfg.gold_dir().exists() else messagebox.showinfo("골드 폴더", f"아직 없습니다: {self.cfg.gold_dir()}"), width=18).pack(fill="x", pady=1)
        ttk.Button(b2, text="선택 제거", command=self.remove_gold_selected, width=18).pack(fill="x", pady=1)
        f_tr = ttk.Frame(f2)
        f_tr.grid(row=1, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 6))
        ttk.Label(f_tr, text="학습할 분류기").pack(side="left")
        trainable = [(k, d) for k, d in CLASSIFIER_CHOICES if k in ("knn", "centroid", "softmax", "ovr", "ngram")]
        self.train_var = tk.StringVar(value=trainable[0][1])
        ttk.Combobox(f_tr, textvariable=self.train_var, values=[d for _, d in trainable], state="readonly", width=40).pack(side="left", padx=4)
        ttk.Button(f_tr, text="학습 실행", command=self.start_train).pack(side="left", padx=8)
        ttk.Button(f_tr, text="분류기 비교 (교차 검증) → Excel", command=self.start_compare_classifiers).pack(side="left", padx=8)
        ttk.Checkbutton(f_tr, text="기준선 분류기(단서어 규칙·글자 n-gram) 포함", variable=self.baseline_var, command=self.refresh_classifier_choices).pack(side="left", padx=8)
        self.clf_status = tk.StringVar(value="")
        ttk.Label(f2, textvariable=self.clf_status).grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 6))

        f3 = ttk.LabelFrame(root, text=" 4. 채점  —  골드 시트로 현재 설정(추출 탭의 분류기·스위치)의 등급 정확도와 검토 목록 정밀도를 잽니다 ")
        f3.grid(row=3, column=0, sticky="ew", padx=6, pady=4)
        ttk.Button(f3, text="골드 시트 선택 → 채점", command=self.start_eval).pack(side="left", padx=12, pady=8)
        self.stored_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(f3, text="다시 판정하지 않고 시트에 저장된 라벨만 채점", variable=self.stored_var).pack(side="left")

        f4 = ttk.LabelFrame(root, text=" 출력 ")
        f4.grid(row=4, column=0, sticky="nsew", padx=6, pady=(4, 8))
        f4.columnconfigure(0, weight=1)
        f4.rowconfigure(0, weight=1)
        self.qlog = self._text_with_scroll(f4, height=8, wrap="none")

    def _build_experiment(self, root: ttk.Frame) -> None:
        root.columnconfigure(0, weight=1)
        root.rowconfigure(3, weight=1)
        ttk.Label(root, text="개량 전후를 사람이 보기 쉽게 비교하는 도구입니다. 결과는 Excel 과 보고서에 붙일 Markdown 요약으로 나옵니다. 실험은 골드 정답 반영과 실행 이력 저장을 끄고 돌립니다.",
                  wraplength=1100, justify="left").grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))
        f1 = ttk.LabelFrame(root, text=" 사다리 실행  —  추출 탭의 입력 파일을, 스위치를 한 칸씩 켜 가며 반복 실행하고 칸마다 무엇이 달라졌는지 비교합니다 ")
        f1.grid(row=1, column=0, sticky="ew", padx=6, pady=4)
        r1 = ttk.Frame(f1)
        r1.pack(fill="x", padx=8, pady=6)
        ttk.Label(r1, text="방식").pack(side="left")
        self.ladder_mode = tk.StringVar(value="누적  —  직전 칸과 비교 (이 스위치를 켜니 무엇이 변했나)")
        ttk.Combobox(r1, textvariable=self.ladder_mode, state="readonly", width=52,
                     values=["누적  —  직전 칸과 비교 (이 스위치를 켜니 무엇이 변했나)", "단독  —  기준선에 한 칸만 켜고 기준선과 비교 (독립 기여)"]).pack(side="left", padx=6)
        self.ladder_gold = tk.BooleanVar(value=True)
        ttk.Checkbutton(r1, text="골드가 있으면 재현율·정밀도도 계산", variable=self.ladder_gold).pack(side="left", padx=8)
        r2 = ttk.Frame(f1)
        r2.pack(fill="x", padx=8, pady=(0, 6))
        ttk.Label(r2, text="칸 순서(스위치 영문 이름, 쉼표. 비우면 전부 기본 순서)").pack(side="left")
        self.ladder_steps = tk.StringVar(value="")
        ttk.Entry(r2, textvariable=self.ladder_steps, width=60).pack(side="left", padx=6)
        ttk.Button(r2, text="사다리 실행 → 결과 폴더 선택", command=self.start_ladder).pack(side="left", padx=8)

        f2 = ttk.LabelFrame(root, text=" 결과 비교  —  결과 Excel(또는 결과 폴더) 둘을 문장 단위로 맞춰 무엇이 진입·이탈·변경됐는지 봅니다 ")
        f2.grid(row=2, column=0, sticky="ew", padx=6, pady=4)
        r = ttk.Frame(f2)
        r.pack(fill="x", padx=8, pady=6)
        self.cmp_a = tk.StringVar(value="")
        self.cmp_b = tk.StringVar(value="")
        ttk.Label(r, text="A (이전·기준)").grid(row=0, column=0, sticky="w")
        ttk.Entry(r, textvariable=self.cmp_a, width=70).grid(row=0, column=1, padx=4)
        ttk.Button(r, text="파일...", command=lambda: self._pick_result(self.cmp_a, False)).grid(row=0, column=2)
        ttk.Button(r, text="폴더...", command=lambda: self._pick_result(self.cmp_a, True)).grid(row=0, column=3, padx=(4, 0))
        ttk.Label(r, text="B (이후·비교)").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(r, textvariable=self.cmp_b, width=70).grid(row=1, column=1, padx=4, pady=(4, 0))
        ttk.Button(r, text="파일...", command=lambda: self._pick_result(self.cmp_b, False)).grid(row=1, column=2, pady=(4, 0))
        ttk.Button(r, text="폴더...", command=lambda: self._pick_result(self.cmp_b, True)).grid(row=1, column=3, padx=(4, 0), pady=(4, 0))
        ttk.Button(r, text="비교 → Excel 저장", command=self.start_compare_runs).grid(row=0, column=4, rowspan=2, padx=12)
        self.exp_open_btn = ttk.Button(r, text="마지막 실험 결과 열기", command=self.open_last_experiment, state="disabled")
        self.exp_open_btn.grid(row=0, column=5, rowspan=2, padx=4)

        f3 = ttk.LabelFrame(root, text=" 출력 (Markdown 요약은 결과 Excel 옆 .md 파일에도 저장됩니다) ")
        f3.grid(row=3, column=0, sticky="nsew", padx=6, pady=(4, 8))
        f3.columnconfigure(0, weight=1)
        f3.rowconfigure(0, weight=1)
        self.elog = self._text_with_scroll(f3, height=10, wrap="none")

    def _build_history(self, root: ttk.Frame) -> None:
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=2)
        root.rowconfigure(1, weight=2)
        root.rowconfigure(2, weight=1)
        f_runs = ttk.LabelFrame(root, text=" 실행 이력  —  행을 고르면 아래에 직전 실행과 달라진 설정과 변경 요약이 나옵니다 ")
        f_runs.grid(row=0, column=0, sticky="nsew", padx=6, pady=(8, 4))
        f_runs.columnconfigure(0, weight=1)
        f_runs.rowconfigure(0, weight=1)
        cols = ("시각", "파일", "분류기", "임베딩", "스위치", "목록", "A", "B", "C", "D", "보류", "진입", "이탈", "등급변경", "설정 변경")
        self.run_tree = self._tree(f_runs, cols, (120, 180, 80, 90, 60, 45, 35, 35, 35, 35, 45, 45, 45, 60, 240), height=7, stretch=("파일", "설정 변경"))
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

    def _widget_for(self, where: str) -> tk.Text:
        return {"log": self.log, "q": self.qlog, "e": self.elog}.get(where, self.log)

    def _poll(self) -> None:
        try:
            while True:
                kind, *rest = self.q.get_nowait()
                if kind == "log":
                    where, msg = rest
                    self._append(self._widget_for(where), msg)
                elif kind == "status":
                    self.status_var.set(rest[0])
                elif kind == "models":
                    if rest[0]:
                        self.embed_box["values"] = rest[0]
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
        self._cancel.reset()
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
            self._append(self.log, "중지됨. 진행 중이던 임베딩 호출을 끊었고, 끝난 문장의 임베딩은 캐시에 남아 다음 실행에서 재사용됩니다.")
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
        elif kind in ("ladder", "compare", "compare_clf"):
            self.last_experiment = Path(payload["out"])
            self.exp_open_btn.configure(state="normal")

    def cancel(self) -> None:
        self._cancel.cancel()          # 진행 중인 Ollama 요청의 소켓을 끊어 즉시 멈춘다
        self._append(self.log, "중지 요청: 진행 중인 호출을 끊습니다.")

    def _check_cancel(self) -> None:
        self._cancel.check()

    def _on_close(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            if not messagebox.askyesno("종료", "작업이 진행 중입니다. 종료할까요?"):
                return
        self.destroy()

    # ------------------------------------------------------------------ 설정 조립
    def set_switches(self, on: bool) -> None:
        for v in self.switch_vars.values():
            v.set(on)

    def current_rules(self) -> tuple[list[str], list[str], float, float]:
        low = parse_patterns(self.low_text.get("1.0", "end"))
        high = parse_patterns(self.high_text.get("1.0", "end"))
        low_w = max(0.0, min(1.0, float(self.low_var.get().strip() or 0.4)))
        accept = float(self.accept_var.get().strip() or 0.5)
        return low, high, low_w, accept

    def short_chars(self) -> int:
        v = self.short_var.get().strip()
        if not v.isdigit():
            raise ValueError(f"짧은 줄 기준은 0 이상의 정수여야 합니다: {v!r}")
        return int(v)

    def classifier_key(self) -> str:
        return next((k for k, d in CLASSIFIER_CHOICES if d == self.clf_var.get()), "proto")

    def classifier_choices(self) -> list[str]:
        """추출 탭 분류기 선택지. 기준선 체크를 끄면 cue·ngram 이 빠진다 (설정 파일의 classifier 가 기준선이면 그것은 남긴다)."""
        from .classify import REGISTRY
        keep = self.baseline_var.get()
        return [d for k, d in CLASSIFIER_CHOICES if keep or not REGISTRY[k].baseline or k == self.cfg.classifier]

    def refresh_classifier_choices(self) -> None:
        values = self.classifier_choices()
        self.clf_box["values"] = values
        if self.clf_var.get() not in values:
            self.clf_var.set(values[0])

    def build_cfg(self) -> Config:
        """화면의 값으로 Config 를 만든다. Tk 변수는 메인 스레드에서만 읽는다."""
        low, high, low_w, accept = self.current_rules()
        grades = next((k for k, d in GRADE_CHOICES if d == self.grades_var.get()), "A,B")
        cfg = Config.load(self.cfg.config_path or None, classifier=self.classifier_key(), embed_model=self.embed_var.get().strip() or None,
                          use_cache=self.cache_var.get(), low_relevance_patterns=low, high_relevance_patterns=high,
                          low_relevance_weight=low_w, accept_score=accept, target_grades=grades, short_line_chars=self.short_chars(),
                          gold_paths=self.cfg.gold_paths, use_gold=self.cfg.use_gold, history_path=self.cfg.history_path,
                          cache_path=self.cfg.cache_path, classifier_dir=self.cfg.classifier_dir, baseline_classifiers=self.baseline_var.get())
        for s in SWITCHES:
            setattr(cfg, s.field, bool(self.switch_vars[s.name].get()))
        return cfg

    def apply_rules(self) -> None:
        try:
            low, high, low_w, accept = self.current_rules()
        except ValueError as e:
            messagebox.showerror("규칙 오류", str(e))
            return
        self.cfg.low_relevance_patterns, self.cfg.high_relevance_patterns = low, high
        self.cfg.low_relevance_weight, self.cfg.accept_score, self.cfg.page_weight_enabled = low_w, accept, self.pw_var.get()
        self.rules_status.set(f"적용됨: 낮음 키워드 {len(low)}개, 높음 키워드 {len(high)}개, 낮음 가중치 {low_w}, 점수 기준 {accept}, "
                              f"가중치 {'켬' if self.pw_var.get() else '끔'}. 다음 실행부터 반영됩니다 (저장하지 않으면 종료 시 사라짐).")
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
        self.rules_status.set(f"저장: {out}. 설치 폴더의 ip_finder.toml 은 UI 와 명령줄이 자동으로 읽고, 다른 위치는 ip-finder --config 로 지정합니다. 스위치 상태도 함께 저장됩니다.")

    def reset_rules(self) -> None:
        base = Config()
        self.low_text.delete("1.0", "end")
        self.low_text.insert("1.0", patterns_text(base.low_relevance_patterns))
        self.high_text.delete("1.0", "end")
        self.low_var.set(str(base.low_relevance_weight))
        self.accept_var.set(str(base.accept_score))
        self.short_var.set(str(base.short_line_chars))

    # ------------------------------------------------------------------ 환경 점검
    def check_env(self) -> None:
        try:
            cfg = self.build_cfg()
        except ValueError:
            cfg = Config.load()

        def work(cfg=cfg):
            from .classify import REGISTRY
            from .ollama import assert_local, installed_models, server_available
            parts = []
            try:
                assert_local(cfg.host)
            except Exception as e:
                self.q.put(("status", f"설정 오류: {e}"))
                return
            if server_available(cfg.host):
                names = installed_models(cfg.host)
                embeds = [n for n in names if any(k in n.lower() for k in ("embed", "bge", "e5", "kure", "minilm"))] or names
                self.q.put(("models", embeds))
                has = cfg.embed_model in names or f"{cfg.embed_model}:latest" in names
                parts.append("Ollama 연결 ✓")
                parts.append(f"임베딩 {cfg.embed_model} {'✓' if has else '✗ (ollama pull 필요)'}")
            else:
                parts.append(f"Ollama 연결 ✗ ({cfg.host})  임베딩을 쓰는 분류기는 동작하지 않습니다 (cue·ngram 은 동작)")
            cls = REGISTRY[cfg.classifier]
            if cls.trainable:
                f = cfg.classifier_file()
                parts.append(f"분류기 {cfg.classifier}: " + (f"학습 파일 있음 ({f.name})" if f.exists() else "학습 파일 없음 → 정확도 관리 탭에서 학습"))
            else:
                parts.append(f"분류기 {cfg.classifier} (학습 없음)")
            parts.append(f"스위치: {describe_switches(cfg)}")
            self.q.put(("status", "   |   ".join(parts)))
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

    def _inputs(self) -> list[Path]:
        return [Path(p) for p in self.files_list.get(0, "end")]

    def _cfg_or_error(self) -> Config | None:
        try:
            return self.build_cfg()
        except ValueError as e:
            messagebox.showerror("옵션 오류", f"점수 기준·낮음 가중치는 숫자, 키워드는 올바른 정규식이어야 합니다.\n{e}")
            return None

    def start_extract(self) -> None:
        if self._busy():
            return
        inputs = self._inputs()
        if not inputs:
            messagebox.showinfo("입력 없음", "먼저 보고서 파일이나 폴더를 추가하세요.")
            return
        cfg = self._cfg_or_error()
        if cfg is None:
            return
        out_dir = Path(self.out_dir_var.get()) if self.out_mode.get() == "folder" and self.out_dir_var.get().strip() else None
        self._start(self._extract_job, inputs, cfg, out_dir)

    def _services(self, cfg: Config, cache):
        """임베더(필요할 때)와 분류기를 한 번 만든다. 중지 토큰에 임베더를 등록한다."""
        from .classify import load_classifier, needs_embedding
        from .pipeline import make_embedder
        emb = None
        if needs_embedding(cfg.classifier):
            emb = make_embedder(cfg, cache)
            self._cancel.register(emb)
            if not emb.available():
                raise RuntimeError(f"임베딩 모델 {cfg.embed_model} 을 쓸 수 없습니다 ({cfg.host}). Ollama 실행과 'ollama pull {cfg.embed_model}' 을 확인하세요.")
        return emb, load_classifier(cfg, emb)

    def _extract_job(self, inputs: list[Path], cfg: Config, out_dir: Path | None) -> dict:
        import time
        from collections import Counter
        from .cache import LabelCache
        from .cli import _summary
        from .pipeline import extract, find_inputs, output_path
        files = find_inputs(inputs)
        if not files:
            raise RuntimeError("처리할 파일이 없습니다 (.pdf, .pptx, .ppt)")
        cache = LabelCache(cfg.cache_file() if cfg.use_cache else None)
        outputs: list[Path] = []
        labeled: list[LabeledLine] = []
        result = None
        last_name, summary = "", ""
        try:
            emb, clf = self._services(cfg, cache)
            taken = Counter(output_path(f, out_dir) for f in files)
            t_all = time.time()
            self._log(f"== {len(files)}개 파일, 분류기 {CLASSIFIER_NAMES[cfg.classifier]}, 임베딩 {cfg.embed_model}, 추출 등급 {','.join(cfg.targets())}, "
                      f"점수 기준 {cfg.accept_score}\n   스위치: {describe_switches(cfg)}")
            for f in files:
                self._check_cancel()
                t0 = time.time()
                self._log(f"\n== {f.name}")

                def status(msg, _t0=t0):
                    self._check_cancel()
                    self._log(f"  {msg}  {time.time() - _t0:5.1f}s")

                out, res = extract(f, cfg, out_dir, with_ext=taken[output_path(f, out_dir)] > 1, status=status, embedder=emb, classifier=clf, cancel=self._cancel)
                i = res.info
                summary = (f"페이지 {i.pages_total} (판정 {i.pages_labeled}, 제외 {i.pages_excluded}, 이미지 {i.pages_image}) | "
                           f"판정 {i.clf_lines}문장, 캐시 {i.cache_hits} | {i.elapsed_sec:.1f}초")
                self._log(f"  → {out}\n  {summary}\n  {_summary(res)}")
                for s in i.settings_diff:
                    self._log(f"  달라진 설정: {s}")
                for w in i.warnings:
                    self._log(f"  안내: {w}")
                outputs.append(out)
                labeled, result, last_name = res.labeled, res, f.name
            if len(files) > 1:
                self._log(f"\n총 {len(files)}개 파일, {time.time() - t_all:.0f}초")
        finally:
            cache.close()
        return {"kind": "extract", "outputs": outputs, "labeled": labeled, "result": result, "last_name": last_name, "summary": summary}

    def fill_results(self) -> None:
        self.tree.delete(*self.tree.get_children())
        want = self.filter_var.get()
        n = 0
        for ll in self.last_labeled:
            if want == STATUS_HOLD:
                if not in_hold_list(ll):
                    continue
                tag = "hold"
            elif want == STATUS_CLF_OUT:
                if not is_stage1_out(ll):
                    continue
                tag = "hold"
            elif want == STATUS_POST_OUT:
                if not is_stage2_out(ll):
                    continue
                tag = "hold"
            else:
                if not in_review_list(ll) or (want != STATUS_REVIEW and ll.label != want):
                    continue
                tag = ll.label
            n += 1
            note = ll.hold_reason if want == STATUS_HOLD and ll.hold_reason else ", ".join(ll.notes)
            conf = f"{ll.clf_conf:.2f}" if ll.clf_conf is not None else ""
            self.tree.insert("", "end", values=(n, ll.section, ll.page_no, ll.label, ll.text, f"{ll.score:.2f}", f"{ll.page_weight:.2f}",
                                                conf, SOURCE_NAME.get(ll.source, ll.source), note), tags=(tag,))

    def fill_pages(self, doc, labeled: list[LabeledLine]) -> None:
        self.page_tree.delete(*self.page_tree.get_children())
        by_page: dict[int, list[LabeledLine]] = {}
        for ll in labeled:
            by_page.setdefault(ll.page_no, []).append(ll)
        for p in doc.pages:
            rows = by_page.get(p.no, [])
            state = p.excluded_reason or ("판정" if labeled else f"판정 대상 {len(p.active_lines())}문장")
            cnt = (lambda f: sum(1 for ll in rows if f(ll))) if labeled else (lambda f: "")
            self.page_tree.insert("", "end", values=(p.no, p.title, p.relevance, f"{p.weight:.2f}", p.weight_reason, state,
                                                     cnt(in_review_list), cnt(in_hold_list), cnt(is_stage1_out), cnt(is_stage2_out)),
                                  tags=("low",) if p.relevance == "낮음" else ())

    def start_preview_pages(self, path: Path | None = None) -> None:
        if self._busy():
            return
        if path is None:
            p = filedialog.askopenfilename(title="가중치를 미리 볼 보고서", filetypes=[("보고서", "*.pdf *.pptx *.ppt")])
            if not p:
                return
            path = Path(p)
        cfg = self._cfg_or_error()
        if cfg is None:
            return
        self._start(self._preview_job, path, cfg)

    def _preview_job(self, path: Path, cfg: Config) -> dict:
        from .pipeline import prepare
        from .readers import load_document
        doc = load_document(path, layout=cfg.layout_analysis)
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
        """골드 폴더의 *_gold.xlsx 를 목록에 올린다."""
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
        cfg = self._cfg_or_error()
        if cfg is None:
            return
        self._start(self._gold_job, Path(p), cfg)

    def _gold_job(self, path: Path, cfg: Config) -> dict:
        from .cache import LabelCache
        from .eval import make_gold_sheet
        cache = LabelCache(cfg.cache_file() if cfg.use_cache else None)
        try:
            emb, clf = self._services(cfg, cache)
            self._log(f"골드 시트 생성 중: {path.name} (분류기 {cfg.classifier}, 스위치 {describe_switches(cfg)})", "q")
            out = make_gold_sheet(path, cfg, None, embedder=emb, classifier=clf)
        finally:
            cache.close()
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
        cfg = self._cfg_or_error()
        if cfg is None:
            return
        self._start(self._feedback_job, Path(p), cfg, self.confirm_var.get())

    def _feedback_job(self, result: Path, cfg: Config, confirm: bool) -> dict:
        from .eval import import_feedback
        from .history import History
        rec = import_feedback(result, None, confirm_unmarked=confirm, history=History(cfg.history_dir()), gold_dir=cfg.gold_dir())
        msg = (f"피드백 {rec['feedback_rows']}행 → 골드 시트 {rec['gold']}\n  추가 {rec['added']}, 갱신 {rec['updated']}, 건너뜀 {rec['skipped']}, 골드 총 {rec['gold_rows']}행")
        if rec["corrections"]:
            msg += "\n  내역: " + ", ".join(f"{k} {v}" for k, v in sorted(rec["corrections"].items()))
        if rec["feedback_rows"] == 0:
            msg += "\n  피드백 열이 비어 있습니다. 결과 Excel 의 '피드백' 열에 O / X / A~D 를 적고 저장한 뒤 다시 하세요."
        else:
            msg += "\n  다음 실행부터 이 문장들은 골드 정답을 그대로 씁니다. 분류기를 갱신하려면 3번에서 학습하고, 어느 분류기가 나은지는 '분류기 7종 비교'로 보세요."
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
        cfg = self._cfg_or_error()
        if cfg is None:
            return
        name = next((k for k, d in CLASSIFIER_CHOICES if d == self.train_var.get()), "knn")
        self._start(self._train_job, list(self.gold_files), cfg, name)

    def _train_job(self, golds: list[Path], cfg: Config, name: str) -> dict:
        from .cache import LabelCache
        from .classify import REGISTRY
        from .eval import train_classifier
        from .pipeline import make_embedder
        cache = LabelCache(cfg.cache_file() if cfg.use_cache else None)
        try:
            emb = None
            if REGISTRY[name].needs_embedding:
                emb = make_embedder(cfg, cache)
                self._cancel.register(emb)
                if not emb.available():
                    raise RuntimeError(f"임베딩 모델 {cfg.embed_model} 을 쓸 수 없습니다 → ollama pull {cfg.embed_model}")
            self._log(f"학습 중: {CLASSIFIER_NAMES[name]} ← {', '.join(g.name for g in golds)}", "q")
            stats = train_classifier(golds, cfg, None, emb, name=name)
        finally:
            cache.close()
        self._log(f"학습 문장 {stats['n']}개 (등급별 {stats['counts']})\n5겹 교차검증 정확도 {stats['cv_accuracy']:.1%}, 학습 데이터 정확도 {stats['train_accuracy']:.1%}\n"
                  f"저장: {stats['out']}  → 추출 탭에서 1차 분류기를 '{name}' 으로 고르면 이 파일을 씁니다." +
                  ("\n참고: 문장 100개 미만이면 교차검증 값이 크게 흔들립니다. 분류기 비교의 표준편차를 함께 보세요." if stats["n"] < 100 else ""), "q")
        return {"kind": "train"}

    def start_compare_classifiers(self) -> None:
        if self._busy():
            return
        if not self.gold_files:
            messagebox.showinfo("골드 시트 없음", "먼저 정답을 채운 골드 시트를 추가하세요.")
            return
        cfg = self._cfg_or_error()
        if cfg is None:
            return
        out = filedialog.asksaveasfilename(title="분류기 비교 결과 저장", initialfile="분류기_비교.xlsx", defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")])
        if not out:
            return
        self._start(self._compare_clf_job, list(self.gold_files), cfg, Path(out))

    def _compare_clf_job(self, golds: list[Path], cfg: Config, out: Path) -> dict:
        from .cache import LabelCache
        from .compare import classifiers_markdown, compare_classifiers, write_classifier_compare
        from .goldmap import load_gold
        from .pipeline import make_embedder
        rows = []
        for g in golds:
            rows.extend(load_gold(g))
        if not rows:
            raise RuntimeError("골드 시트에 정답이 적힌 문장이 없습니다.")
        cache = LabelCache(cfg.cache_file() if cfg.use_cache else None)
        try:
            emb = make_embedder(cfg, cache)
            self._cancel.register(emb)
            from .classify import available_names
            names = available_names(cfg)
            self._log(f"분류기 비교: 골드 {len(rows)}문장, 임베딩 {cfg.embed_model}, 대상 {', '.join(names)}", "q")
            result = compare_classifiers(rows, cfg, emb, names, status=lambda m: self._log("  " + m, "q"))
        finally:
            cache.close()
        write_classifier_compare(result, out)
        md = classifiers_markdown(result)
        out.with_suffix(".md").write_text(md, encoding="utf-8")
        self._log(md + f"\n→ {out}\n→ {out.with_suffix('.md')}", "q")
        return {"kind": "compare_clf", "out": out}

    def start_eval(self) -> None:
        if self._busy():
            return
        p = filedialog.askopenfilename(title="채점할 골드 시트", filetypes=[("Excel", "*.xlsx")])
        if not p:
            return
        cfg = self._cfg_or_error()
        if cfg is None:
            return
        self._start(self._eval_job, Path(p), cfg, self.stored_var.get())

    def _eval_job(self, gold: Path, cfg: Config, stored: bool) -> dict:
        from .cache import LabelCache
        from .eval import evaluate, print_report
        cache = LabelCache(cfg.cache_file() if cfg.use_cache else None)
        try:
            emb = clf = None
            if not stored:
                emb, clf = self._services(cfg, cache)
            self._log(f"채점 중: {gold.name} (분류기 {cfg.classifier}{', 저장된 라벨' if stored else ''}, 점수 기준 {cfg.accept_score}, 스위치 {describe_switches(cfg)})", "q")
            rep = evaluate(gold, cfg, rerun=not stored, embedder=emb, classifier=clf)
        finally:
            cache.close()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_report(rep)
        self._log(buf.getvalue(), "q")
        return {"kind": "eval"}

    # ------------------------------------------------------------------ 실험 탭 동작
    def _pick_result(self, var: tk.StringVar, folder: bool) -> None:
        if folder:
            p = filedialog.askdirectory(title="결과 폴더 선택")
        else:
            p = filedialog.askopenfilename(title="결과 Excel 선택", filetypes=[("결과 Excel", "*_검토후보.xlsx"), ("Excel", "*.xlsx")])
        if p:
            var.set(p)

    def start_ladder(self) -> None:
        if self._busy():
            return
        inputs = self._inputs()
        if not inputs:
            messagebox.showinfo("입력 없음", "추출 탭에서 먼저 보고서 파일이나 폴더를 추가하세요.")
            return
        cfg = self._cfg_or_error()
        if cfg is None:
            return
        out = filedialog.askdirectory(title="사다리 결과를 저장할 폴더 (칸마다 하위 폴더가 생깁니다)")
        if not out:
            return
        mode = "cumulative" if self.ladder_mode.get().startswith("누적") else "single"
        steps = [s.strip() for s in self.ladder_steps.get().split(",") if s.strip()] or None
        self._start(self._ladder_job, inputs, cfg, Path(out), mode, steps, self.ladder_gold.get())

    def _ladder_job(self, inputs: list[Path], cfg: Config, out: Path, mode: str, steps: list[str] | None, use_gold: bool) -> dict:
        from .compare import default_ladder, ladder_markdown, run_ladder, write_ladder
        from .goldmap import load_gold
        from .pipeline import find_inputs
        files = find_inputs(inputs)
        if not files:
            raise RuntimeError("처리할 파일이 없습니다 (.pdf, .pptx, .ppt)")
        ladder = default_ladder(steps, mode)
        gold_rows = None
        if use_gold:
            gold_rows = []
            for g in cfg.gold_files():
                gold_rows.extend(load_gold(g))
            if not gold_rows:
                self._log("골드가 없어 재현율·정밀도는 생략합니다.", "e")
                gold_rows = None
        self._log(f"사다리 ({'누적' if mode == 'cumulative' else '단독'}): 기준선 → " + " → ".join(s.label for s in ladder.steps) + f"\n파일 {len(files)}개 → {out}", "e")
        result = run_ladder(files, cfg, ladder, out, gold_rows, status=lambda m: self._log("  " + m, "e"), cancel=self._cancel)
        xlsx = write_ladder(result, out / f"사다리_{ladder.name}.xlsx")
        md = ladder_markdown(result)
        xlsx.with_suffix(".md").write_text(md, encoding="utf-8")
        self._log(md + f"\n→ {xlsx}\n→ {xlsx.with_suffix('.md')}", "e")
        return {"kind": "ladder", "out": xlsx}

    def start_compare_runs(self) -> None:
        if self._busy():
            return
        a, b = self.cmp_a.get().strip(), self.cmp_b.get().strip()
        if not a or not b:
            messagebox.showinfo("입력 없음", "A 와 B 결과(파일 또는 폴더)를 모두 고르세요.")
            return
        out = filedialog.asksaveasfilename(title="비교 결과 저장", initialfile="비교.xlsx", defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")])
        if not out:
            return
        cfg = self._cfg_or_error()
        if cfg is None:
            return
        self._start(self._compare_job, Path(a), Path(b), Path(out), cfg)

    def _compare_job(self, a: Path, b: Path, out: Path, cfg: Config) -> dict:
        from .compare import compare_records, gold_metrics, load_records, pair_records, runs_markdown, write_runs_compare
        from .goldmap import load_gold
        ra, rb = load_records(a), load_records(b)
        if not ra or not rb:
            raise RuntimeError(f"결과 파일이 없습니다 (A {len(ra)}개, B {len(rb)}개). *_검토후보.xlsx 파일이나 그 폴더를 고르세요.")
        pairs = pair_records(ra, rb)
        if not pairs:
            raise RuntimeError("이름이 같은 보고서가 없어 짝지을 수 없습니다.")
        diffs = [compare_records(x, y) for x, y in pairs]
        gold_rows = []
        for g in cfg.gold_files():
            gold_rows.extend(load_gold(g))
        gold = [(gold_metrics(x, gold_rows), gold_metrics(y, gold_rows)) for x, y in pairs] if gold_rows else None
        write_runs_compare(diffs, out, a.name, b.name, gold)
        md = runs_markdown(diffs, a.name, b.name, gold)
        out.with_suffix(".md").write_text(md, encoding="utf-8")
        self._log(md + f"\n→ {out}\n→ {out.with_suffix('.md')}", "e")
        return {"kind": "compare", "out": out}

    def open_last_experiment(self) -> None:
        if self.last_experiment:
            open_path(self.last_experiment)

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
            n_on = sum(1 for sw in SWITCHES if s.get(sw.field))
            self.run_tree.insert("", "end", iid=r.get("run_id"), values=(
                str(r.get("started_at", "")).replace("T", " ")[:16], r.get("source_name", ""), s.get("classifier", ""), s.get("embed_model", ""),
                f"{n_on}/{len(SWITCHES)} 켬", st.get("list", 0), st.get("A", 0), st.get("B", 0), st.get("C", 0), st.get("D", 0), st.get("held", 0),
                ch.get("entered", "") if has_prev else "-", ch.get("left", "") if has_prev else "-", ch.get("grade", "") if has_prev else "-",
                "; ".join(r.get("settings_diff", []))[:200] if has_prev else "(첫 실행)"))
        self.hist_status.set(f"실행 {len(runs)}건, 피드백 {len(feedback)}건, 학습 {len(train)}건  ({root})")
        lines = []
        for f in feedback[-30:]:
            lines.append(f"[피드백] {f.get('time', '')}  {Path(f.get('result', '')).name} → {Path(f.get('gold', '')).name}: {f.get('feedback_rows', 0)}행  "
                         + ", ".join(f"{k} {v}" for k, v in sorted((f.get("corrections") or {}).items())))
        for t in train[-30:]:
            lines.append(f"[학습]   {t.get('time', '')}  {t.get('classifier', '')} {t.get('n', 0)}문장, 교차검증 {t.get('cv_accuracy', 0):.1%} → {t.get('out', '')}")
        self._set_text(self.fb_log, "\n".join(sorted(lines, key=lambda s: s[9:28])) or "아직 피드백·학습 이력이 없습니다.")

    def show_run(self) -> None:
        sel = self.run_tree.selection()
        if not sel:
            return
        r = next((x for x in self.runs if x.get("run_id") == sel[0]), None)
        if r is None:
            return
        s, st = r.get("settings", {}), r.get("stats", {})
        on = [sw.label for sw in SWITCHES if s.get(sw.field)]
        parts = [f"{r.get('run_id')}  {r.get('source_name')}  —  분류기 {s.get('classifier')} ({s.get('classifier_desc', '')}) / 임베딩 {s.get('embed_model')} / "
                 f"추출 등급 {s.get('target_grades', 'A,B')} / 점수 기준 {s.get('accept_score')} / 켠 스위치: {', '.join(on) or '없음(기준선)'}",
                 f"목록 {st.get('list', 0)} (A{st.get('A', 0)} B{st.get('B', 0)} C{st.get('C', 0)} D{st.get('D', 0)}), 보류 {st.get('held', 0)}, 문장 {st.get('lines', 0)}, {r.get('elapsed_sec', 0)}초"]
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
