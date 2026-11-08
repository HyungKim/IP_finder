"""개량 전후를 사람이 보기 쉽게 비교하는 도구 묶음.
- records / matching : 결과(Excel 또는 메모리)를 문장 단위로 맞춰 비교 (compare-runs)
- classifiers        : 골드 교차 검증으로 1차 분류기 후보 비교 (compare-classifiers)
- ladder             : 스위치를 한 칸씩 켜며 반복 실행·비교 (ladder)
- xlsx / markdown    : 비교 결과를 Excel 과 Markdown 요약으로"""
from .classifiers import ClassifierReport, compare_classifiers
from .ladder import Ladder, LadderResult, Step, default_ladder, load_ladder, run_ladder, step_config
from .markdown import classifiers_markdown, ladder_markdown, runs_markdown
from .matching import Matches, match_texts, norm_key
from .records import (KIND_ORDER, RunDiff, RunRecord, Unit, aggregate_gold, compare_records, find_result_files, gold_metrics, load_record,
                      load_records, pair_records, record_from_result)
from .xlsx import write_classifier_compare, write_ladder, write_runs_compare

__all__ = ["KIND_ORDER", "ClassifierReport", "compare_classifiers", "Ladder", "LadderResult", "Step", "default_ladder", "load_ladder", "run_ladder",
           "step_config", "classifiers_markdown", "ladder_markdown", "runs_markdown", "Matches", "match_texts", "norm_key",
           "RunDiff", "RunRecord", "Unit", "aggregate_gold", "compare_records", "find_result_files", "gold_metrics", "load_record",
           "load_records", "pair_records", "record_from_result", "write_classifier_compare", "write_ladder", "write_runs_compare"]
