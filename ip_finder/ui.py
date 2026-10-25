"""IP Finder 데스크톱 UI (Tkinter). 추가 설치 없이 동작한다.
실행: python -m ip_finder.ui  /  ip-finder ui  /  윈도우 ui.bat
탭 1 '추출': 파일·폴더 선택 → 옵션 → 실행 → 진행 로그 → 결과 미리보기 → Excel 열기
탭 2 '정확도 관리': 골드 시트 만들기 → 분류기 학습 → 채점"""
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
from .config import Config
from .models import LabeledLine
from .post.templates import discussion_point
from .readers import SUPPORTED

GRADE_FILL = {"A": "#FFE0B2", "B": "#FFF9C4", "C": "#DCEDC8", "D": "#BBDEFB"}
MODES = [("hybrid", "hybrid  —  분류기 확신분 채택, 애매한 문장만 LLM (기본)"),
         ("fast", "fast  —  분류기만, 가장 빠름"),
         ("llm", "llm  —  전부 LLM, 가장 정확하고 느림")]


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


class App(tk.Tk):
    def __init__(self, cfg: Config | None = None):
        super().__init__()
        self.cfg = cfg or Config.load()
        self.title(f"IP Finder {__version__}  —  특허 검토 후보 추출 (온디바이스)")
        self.geometry("1120x780")
        self.minsize(900, 620)
        self.q: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self._cancel = threading.Event()
        self.last_outputs: list[Path] = []
        self.last_labeled: list[LabeledLine] = []
        self.gold_files: list[Path] = []
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names() and sys.platform != "darwin":
            style.theme_use("clam")
        self._build()
        self.after(100, self._poll)
        self.after(400, self.check_env)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ 화면 구성
    def _build(self) -> None:
        nb = self.nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        self.tab_extract = ttk.Frame(nb)
        self.tab_quality = ttk.Frame(nb)
        nb.add(self.tab_extract, text="  추출  ")
        nb.add(self.tab_quality, text="  정확도 관리  ")
        self._build_extract(self.tab_extract)
        self._build_quality(self.tab_quality)
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=8, pady=6)
        self.status_var = tk.StringVar(value="환경 점검 중...")
        ttk.Label(bar, textvariable=self.status_var).pack(side="left")
        ttk.Button(bar, text="환경 점검", command=self.check_env).pack(side="right")

    def _build_extract(self, root: ttk.Frame) -> None:
        root.columnconfigure(0, weight=1)
        root.rowconfigure(3, weight=1)
        root.rowconfigure(4, weight=2)

        # 입력 파일
        f_in = ttk.LabelFrame(root, text=" 1. 입력 파일  (PDF, PPTX, PPT. 폴더는 하위 폴더까지) ")
        f_in.grid(row=0, column=0, sticky="ew", padx=6, pady=(8, 4))
        f_in.columnconfigure(0, weight=1)
        self.files_list = tk.Listbox(f_in, height=5, selectmode="extended")
        self.files_list.grid(row=0, column=0, sticky="ew", padx=(8, 4), pady=6)
        btns = ttk.Frame(f_in)
        btns.grid(row=0, column=1, sticky="n", padx=(0, 8), pady=6)
        ttk.Button(btns, text="파일 추가...", command=self.add_files_dialog, width=14).pack(fill="x", pady=1)
        ttk.Button(btns, text="폴더 추가...", command=self.add_folder_dialog, width=14).pack(fill="x", pady=1)
        ttk.Button(btns, text="선택 제거", command=self.remove_selected, width=14).pack(fill="x", pady=1)
        ttk.Button(btns, text="모두 지우기", command=lambda: self.files_list.delete(0, "end"), width=14).pack(fill="x", pady=1)

        # 옵션
        f_opt = ttk.LabelFrame(root, text=" 2. 옵션 ")
        f_opt.grid(row=1, column=0, sticky="ew", padx=6, pady=4)
        for c in (1, 3, 5):
            f_opt.columnconfigure(c, weight=1)
        ttk.Label(f_opt, text="판정 모드").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        self.mode_var = tk.StringVar(value=next(d for k, d in MODES if k == self.cfg.mode))
        ttk.Combobox(f_opt, textvariable=self.mode_var, values=[d for _, d in MODES], state="readonly", width=48).grid(row=0, column=1, columnspan=3, sticky="w", padx=4)
        ttk.Label(f_opt, text="확신 임계값").grid(row=0, column=4, sticky="e", padx=8)
        self.thr_var = tk.StringVar(value="" if self.cfg.confidence_threshold is None else str(self.cfg.confidence_threshold))
        ttk.Entry(f_opt, textvariable=self.thr_var, width=8).grid(row=0, column=5, sticky="w")
        ttk.Label(f_opt, text="(비우면 기본값: 제로샷 0.05 / 학습 분류기 0.25)").grid(row=0, column=6, sticky="w", padx=4)

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

        ttk.Label(f_opt, text="결과 위치").grid(row=2, column=0, sticky="w", padx=8, pady=4)
        self.out_mode = tk.StringVar(value="beside")
        ttk.Radiobutton(f_opt, text="원본 옆에 저장", variable=self.out_mode, value="beside").grid(row=2, column=1, sticky="w", padx=4)
        ttk.Radiobutton(f_opt, text="지정 폴더:", variable=self.out_mode, value="folder").grid(row=2, column=2, sticky="e", padx=8)
        self.out_dir_var = tk.StringVar(value="")
        ttk.Entry(f_opt, textvariable=self.out_dir_var, width=40).grid(row=2, column=3, columnspan=3, sticky="ew", padx=4)
        ttk.Button(f_opt, text="찾기...", command=self.pick_out_dir).grid(row=2, column=6, sticky="w", padx=4)

        # 실행
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

        # 로그
        f_log = ttk.LabelFrame(root, text=" 3. 진행 ")
        f_log.grid(row=3, column=0, sticky="nsew", padx=6, pady=4)
        f_log.columnconfigure(0, weight=1)
        f_log.rowconfigure(0, weight=1)
        self.log = tk.Text(f_log, height=7, wrap="word", state="disabled", font=("TkFixedFont", 10))
        self.log.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=6)
        sb = ttk.Scrollbar(f_log, command=self.log.yview)
        sb.grid(row=0, column=1, sticky="ns", pady=6)
        self.log.configure(yscrollcommand=sb.set)

        # 결과 미리보기
        f_res = ttk.LabelFrame(root, text=" 4. 결과 미리보기  (검토 목록. 전체 내용은 Excel) ")
        f_res.grid(row=4, column=0, sticky="nsew", padx=6, pady=(4, 8))
        f_res.columnconfigure(0, weight=1)
        f_res.rowconfigure(1, weight=1)
        top = ttk.Frame(f_res)
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 0))
        self.res_title = tk.StringVar(value="아직 결과가 없습니다.")
        ttk.Label(top, textvariable=self.res_title).pack(side="left")
        ttk.Label(top, text="등급 필터").pack(side="right", padx=(8, 4))
        self.filter_var = tk.StringVar(value="전체")
        fb = ttk.Combobox(top, textvariable=self.filter_var, values=["전체", "A", "B", "C", "D"], state="readonly", width=6)
        fb.pack(side="right")
        fb.bind("<<ComboboxSelected>>", lambda e: self.fill_results())
        cols = ("번호", "섹션", "페이지", "등급", "발췌", "논의 포인트", "판정")
        self.tree = ttk.Treeview(f_res, columns=cols, show="headings", height=9)
        widths = (50, 110, 55, 50, 480, 220, 60)
        for c, w in zip(cols, widths):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w, anchor="w", stretch=(c in ("발췌", "논의 포인트")))
        for g, color in GRADE_FILL.items():
            self.tree.tag_configure(g, background=color)
        self.tree.grid(row=1, column=0, sticky="nsew", padx=(8, 0), pady=6)
        sb2 = ttk.Scrollbar(f_res, command=self.tree.yview)
        sb2.grid(row=1, column=1, sticky="ns", pady=6)
        self.tree.configure(yscrollcommand=sb2.set)

    def _build_quality(self, root: ttk.Frame) -> None:
        root.columnconfigure(0, weight=1)
        root.rowconfigure(3, weight=1)
        f1 = ttk.LabelFrame(root, text=" 1. 골드 시트 만들기  —  보고서를 고르면 모델 초안 라벨이 채워진 엑셀이 생깁니다. '정답' 열에서 틀린 것만 고치세요 ")
        f1.grid(row=0, column=0, sticky="ew", padx=6, pady=(8, 4))
        ttk.Button(f1, text="보고서 선택 → 골드 시트 생성", command=self.start_gold_sheet).pack(side="left", padx=8, pady=8)
        self.gold_open_btn = ttk.Button(f1, text="방금 만든 골드 시트 열기", command=self.open_last_gold, state="disabled")
        self.gold_open_btn.pack(side="left", padx=4)
        self.last_gold: Path | None = None

        f2 = ttk.LabelFrame(root, text=" 2. 분류기 학습  —  정답을 채운 골드 시트(여러 개 가능)로 학습합니다. 학습 후 hybrid/fast 모드가 자동으로 사용 ")
        f2.grid(row=1, column=0, sticky="ew", padx=6, pady=4)
        f2.columnconfigure(0, weight=1)
        self.gold_list = tk.Listbox(f2, height=4, selectmode="extended")
        self.gold_list.grid(row=0, column=0, sticky="ew", padx=(8, 4), pady=6)
        b2 = ttk.Frame(f2)
        b2.grid(row=0, column=1, sticky="n", padx=(0, 8), pady=6)
        ttk.Button(b2, text="골드 파일 추가...", command=self.add_gold_dialog, width=16).pack(fill="x", pady=1)
        ttk.Button(b2, text="선택 제거", command=self.remove_gold_selected, width=16).pack(fill="x", pady=1)
        ttk.Button(b2, text="학습 실행", command=self.start_train, width=16).pack(fill="x", pady=(6, 1))
        self.clf_var = tk.StringVar(value="")
        ttk.Label(f2, textvariable=self.clf_var).grid(row=1, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 6))

        f3 = ttk.LabelFrame(root, text=" 3. 채점  —  골드 시트로 현재 설정의 정확도를 잽니다 ")
        f3.grid(row=2, column=0, sticky="ew", padx=6, pady=4)
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
        f4.grid(row=3, column=0, sticky="nsew", padx=6, pady=(4, 8))
        f4.columnconfigure(0, weight=1)
        f4.rowconfigure(0, weight=1)
        self.qlog = tk.Text(f4, wrap="none", state="disabled", font=("TkFixedFont", 10))
        self.qlog.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=6)
        sb = ttk.Scrollbar(f4, command=self.qlog.yview)
        sb.grid(row=0, column=1, sticky="ns", pady=6)
        self.qlog.configure(yscrollcommand=sb.set)

    # ------------------------------------------------------------------ 공통
    def _log(self, msg: str, where: str = "log") -> None:
        self.q.put(("log", where, msg))

    def _append(self, widget: tk.Text, msg: str) -> None:
        widget.configure(state="normal")
        widget.insert("end", msg + "\n")
        widget.see("end")
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
        if payload and isinstance(payload, dict) and payload.get("kind") == "extract":
            self.last_outputs = payload["outputs"]
            self.last_labeled = payload["labeled"]
            self.res_title.set(f"최근 결과: {payload['last_name']}  ({payload['summary']})")
            self.fill_results()
            self.open_xlsx_btn.configure(state="normal" if self.last_outputs else "disabled")
            self.open_dir_btn.configure(state="normal" if self.last_outputs else "disabled")
        elif payload and isinstance(payload, dict) and payload.get("kind") == "gold":
            self.last_gold = payload["path"]
            self.gold_open_btn.configure(state="normal")
            if self.last_gold not in self.gold_files:
                self.gold_files.append(self.last_gold)
                self.gold_list.insert("end", str(self.last_gold))
        elif payload and isinstance(payload, dict) and payload.get("kind") == "train":
            self.check_env()

    def cancel(self) -> None:
        self._cancel.set()
        self._append(self.log, "중지 요청... 현재 페이지가 끝나면 멈춥니다.")

    def _check_cancel(self) -> None:
        if self._cancel.is_set():
            raise Cancelled()

    def _on_close(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            if not messagebox.askyesno("종료", "작업이 진행 중입니다. 종료할까요?"):
                return
        self.destroy()

    # ------------------------------------------------------------------ 설정 조립
    def build_cfg(self, mode: str | None = None, threshold: str | None = None) -> Config:
        mode = mode or next(k for k, d in MODES if d == self.mode_var.get())
        thr_text = (self.thr_var.get() if threshold is None else threshold).strip()
        thr = float(thr_text) if thr_text else None
        return Config.load(mode=mode, model=self.model_var.get().strip() or None, embed_model=self.embed_var.get().strip() or None,
                           confidence_threshold=thr, use_cache=self.cache_var.get())

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
                llms = [n for n in names if "embed" not in n and "bge" not in n and "e5" not in n]
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
        except ValueError:
            messagebox.showerror("옵션 오류", "확신 임계값은 숫자여야 합니다 (예: 0.1). 비우면 기본값을 씁니다.")
            return
        out_dir = Path(self.out_dir_var.get()) if self.out_mode.get() == "folder" and self.out_dir_var.get().strip() else None
        self._start(self._extract_job, inputs, cfg, out_dir)

    def _extract_job(self, inputs: list[Path], cfg: Config, out_dir: Path | None) -> dict:
        import time
        from collections import Counter
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
        last_name, summary = "", ""
        t_all = time.time()
        self._log(f"== {len(files)}개 파일, 모드 {cfg.mode}, LLM {cfg.model}, 임베딩 {cfg.embed_model}")
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
            grades = {g: sum(1 for ll in res.labeled if ll.label == g) for g in ("A", "B", "C", "D", "X?")}
            summary = (f"{i.mode} | 페이지 {i.pages_total} (판정 {i.pages_labeled}, 제외 {i.pages_excluded}, 이미지 {i.pages_image}) | "
                       f"분류기 {i.clf_lines} LLM {i.llm_lines} 호출 {i.llm_calls} 캐시 {i.cache_hits} | {i.elapsed_sec:.0f}초 | "
                       + ", ".join(f"{g} {c}" for g, c in grades.items()))
            self._log(f"  → {out}\n  {summary}")
            for w in i.warnings:
                self._log(f"  경고: {w}")
            outputs.append(out)
            labeled = res.labeled
            last_name = f.name
        if len(files) > 1:
            self._log(f"\n총 {len(files)}개 파일, {time.time() - t_all:.0f}초")
        return {"kind": "extract", "outputs": outputs, "labeled": labeled, "last_name": last_name, "summary": summary}

    def fill_results(self) -> None:
        self.tree.delete(*self.tree.get_children())
        want = self.filter_var.get()
        n = 0
        for ll in self.last_labeled:
            if ll.label not in GRADE_FILL or (want != "전체" and ll.label != want):
                continue
            n += 1
            self.tree.insert("", "end", values=(n, ll.section, ll.page_no, ll.label, ll.text, discussion_point(ll.label),
                                                {"clf": "분류기", "llm": "LLM"}.get(ll.source, ll.source)), tags=(ll.label,))

    def open_last_output(self) -> None:
        if self.last_outputs:
            open_path(self.last_outputs[-1])

    def open_last_folder(self) -> None:
        if self.last_outputs:
            open_path(self.last_outputs[-1].parent)

    # ------------------------------------------------------------------ 정확도 관리 탭 동작
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
        self._log(f"생성: {out}\n'라벨링' 시트의 '정답' 열에서 틀린 등급만 고친 뒤 저장하세요. 이 파일은 실제 문장을 담으므로 저장소 밖에 두세요.", "q")
        return {"kind": "gold", "path": out}

    def open_last_gold(self) -> None:
        if self.last_gold:
            open_path(self.last_gold)

    def add_gold_dialog(self) -> None:
        for p in filedialog.askopenfilenames(title="골드 시트 선택", filetypes=[("Excel", "*.xlsx")]):
            if Path(p) not in self.gold_files:
                self.gold_files.append(Path(p))
                self.gold_list.insert("end", p)

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
                  f"저장: {stats['out']}  → 이제 hybrid/fast 모드가 이 분류기를 씁니다. 아래 3번에서 채점해 확인하세요." +
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
        self._log(f"채점 중: {gold.name} (모드 {cfg.mode}{', 저장된 라벨' if stored else ''})", "q")
        rep = evaluate(gold, cfg, rerun=not stored, client=client)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_report(rep)
        self._log(buf.getvalue(), "q")
        return {"kind": "eval"}


def main(argv: list[str] | None = None) -> int:
    app = App()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
