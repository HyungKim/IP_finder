"""실행 이력: 실행마다 설정 지문과 문장별 (해시, 라벨, 점수)를 저장하고, 같은 파일의 직전 실행과 비교한다. 원문은 저장하지 않는다."""
from .store import History, make_run_id, file_hash, text_hash
from .diff import diff_runs, settings_diff, change_rows, CHANGE_KINDS

__all__ = ["History", "make_run_id", "file_hash", "text_hash", "diff_runs", "settings_diff", "change_rows", "CHANGE_KINDS"]
