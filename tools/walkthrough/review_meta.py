"""변경 리뷰 페이지의 파일별 머리말: 왜 바꿨나 / 어떻게 확인하나. 작업 단위마다 여기를 고쳐 쓴다."""
SUMMARY = {
    "title": "변경 리뷰: 0.6.2 → 1.0.0.dev3 (rebuild 0단계)",
    "lead": "판정 파이프라인을 처음부터 단계별로 다시 쌓기 위한 첫 작업. LLM 2차 판정을 빼고, 모든 규칙을 스위치(기본 끔)로 바꾸고, 1차 분류기 7종과 개량 전후 비교 도구를 넣었다.",
    "points": [
        "읽기(원시/레이아웃) → 전처리(스위치) → 1차 분류기 → 후처리(스위치) → 점수 → Excel. 기준선 = 스위치 전부 끔.",
        "분류기 7종(proto·knn·centroid·softmax·ovr·cue·ngram)이 같은 fit/predict 인터페이스. 설정 classifier 로 고른다.",
        "비교 도구: run-all(한 설정으로 전부), compare-runs(결과 둘을 문장 단위로), ladder(스위치 사다리), compare-classifiers(골드 교차 검증). Excel + Markdown 요약.",
        "결과 Excel 에 '전처리 제외' 시트와 '설정 …' 행이 생겨 결과 파일만으로 전후 비교가 된다.",
        "테스트 84건(가짜 샘플·가짜 임베더, Ollama 없이).",
        "추가(넷째 커밋, dev3): 임베딩 모델 오류에 원인 설명(ollama.explain_missing_model), 다른 꼬리표(bge-m3:567m) 자동 해석(resolve_model).",
        "추가(셋째 커밋): 파싱 점검 HTML(ip-finder parse / parse.bat / UI 단추): 쪽 그림 옆에 읽어 낸 줄(레이아웃·원시), 규칙이 뺄 줄, 점검 표시 ⚠.",
        "추가(둘째 커밋): 기준선 분류기(cue·ngram)를 비교 대상·UI 선택지에서 넣고 빼는 설정 baseline_classifiers(--baseline on|off, UI 체크). docs/classifiers.md(분류기 동작 원리), docs/REFERENCES.md(학술 출처).",
    ],
    "deleted_why": "LLM 2차 판정과 프롬프트. 3단계에서 스위치로 다시 붙인다(코드는 v0.6.2 태그에 있다).",
    "full_url": "https://claude.ai/artifact/DYZAsAgovyUwN6YVVNNra2",
}
GROUPS = ["조립과 모델", "진입점", "읽기", "전처리", "1차 분류기", "후처리", "골드·이력·정확도", "비교 도구", "출력", "문서·설정·배치", "테스트", "개발 도구"]
META = {
    "ip_finder/__init__.py": {"why": "버전을 1.0.0.dev1 로 올리고 단계 이름 상수를 두었다. 프롬프트 버전은 LLM 이 없어 삭제.", "check": "ip-finder check 첫 줄에 버전과 단계가 찍힌다."},
    "pyproject.toml": {"why": "버전·설명 갱신, 패키지 데이터에서 프롬프트 폴더 대신 eval/rubric.md.", "check": "pip install -e . 뒤 ip_finder.eval 폴더에 rubric.md 가 있다."},
    "ip_finder/models.py": {"why": "LabeledLine 에서 LLM 라벨을 빼고 분류기 신뢰도(clf_conf)·차이(clf_margin)를 두었다. RunInfo 는 버전·읽기 방식·스위치 상태를 기록한다.", "check": "Excel '확신' 열과 '실행 정보'의 읽기 방식·스위치 행."},
    "ip_finder/config.py": {"why": "LLM 설정을 없애고 모든 규칙을 bool 스위치(기본 False)로. 분류기 선택(classifier)과 학습 파일 폴더(classifier_dir). 지문(fingerprint)에 스위치 전부.", "check": "ip-finder switches, 그리고 tests/test_prep.py::test_switches_registry_and_config_fields."},
    "ip_finder/switches.py": {"why": "새 파일. 스위치 11개의 이름·필드·한글 이름·설명을 한 곳에 등록해 CLI·UI·사다리·Excel 이 같은 목록을 쓴다.", "check": "ip-finder switches 출력이 이 목록과 같다."},
    "ip_finder/ollama.py": {"why": "새 파일. 옛 llm/ollama_client.py 에서 HTTP 와 로컬 검사만 떼어 왔다(LLM 호출 함수 없음). dev3: 모델 이름 해석(resolve_model)과 오류 원인 설명(explain_missing_model).", "check": "ip-finder check 의 임베딩 줄. 모델이 없을 때 오류 문구에 설치 목록과 조치가 나온다."},
    "ip_finder/cli.py": {"why": "LLM 관련 인자 삭제, --classifier/--on/--off 추가, 실험 명령 4개(compare-classifiers, run-all, compare-runs, ladder)와 switches 명령 추가.", "check": "tests/test_cli.py 가 cue 분류기로 모든 실험 명령을 끝까지 돈다."},
    "ip_finder/pipeline.py": {"why": "cascade/fast/llm 모드를 없애고 분류기 하나로 판정(classify_lines). 읽기에 레이아웃 스위치, 점수에 trained 구분 없음.", "check": "tests/test_pipeline.py 기준선·전부 켬·스위치 하나씩."},
    "ip_finder/ui.py": {"why": "LLM 모델·모드 UI 삭제, 분류기 콤보와 스위치 체크박스, '실험' 탭(사다리·결과 비교), 분류기 7종 비교 단추.", "check": "ui.bat 실행 → 추출 탭 3번 스위치 묶음, 실험 탭. tests/test_ui.py."},
    "ip_finder/readers/__init__.py": {"why": "load_document 에 layout 인자. 원시 모드에서는 ▪| 항목 나누기도 하지 않는다.", "check": "tests/test_readers.py::test_raw_reading_mode_pdf_and_pptx."},
    "ip_finder/readers/pdf_reader.py": {"why": "read_pdf(layout) 분기와 원시 읽기 _read_raw 추가(PyMuPDF 기본 추출 줄 그대로).", "check": "ip-finder extract 보고서.pdf (레이아웃 끔) 결과의 '실행 정보' 읽기 방식 = 원시 읽기."},
    "ip_finder/readers/pptx_reader.py": {"why": "read_pptx(layout) 분기와 원시 읽기 _read_raw 추가(도형 XML 순서 그대로, SmartArt 없음).", "check": "같은 PPTX 를 레이아웃 켬/끔으로 돌려 compare-runs 로 비교."},
    "ip_finder/prep/line_rules.py": {"why": "규칙마다 스위치를 본다(rule_repeated_line, rule_pattern_lines, rule_require_korean, rule_short_line).", "check": "tests/test_prep.py 의 스위치별 테스트."},
    "ip_finder/prep/splitter.py": {"why": "rule_split_long 스위치가 켜질 때만 긴 줄을 나눈다.", "check": "tests/test_prep.py::test_split_long_switch."},
    "ip_finder/prep/page_rules.py": {"why": "rule_page_exclude·rule_cover 스위치. 글 없는 쪽은 늘 제외.", "check": "tests/test_prep.py::test_page_exclude_and_cover_switches."},
    "ip_finder/prep/page_type.py": {"why": "설명 문구에서 LLM 언급 삭제.", "check": "동작 변화 없음."},
    "ip_finder/classify/__init__.py": {"why": "등록부(REGISTRY)와 로더(load_classifier). 이름으로 분류기를 고르고 학습 파일·임베딩 모델을 검사한다.", "check": "tests/test_classify.py::test_registry_has_seven_classifiers, test_load_classifier_checks_embed_model."},
    "ip_finder/classify/base.py": {"why": "새 파일. Prediction·Batch·Classifier 공통 틀과 npz 저장·복원. 신뢰도의 뜻을 통일.", "check": "학습형 다섯이 저장→복원 뒤 같은 판정(test_trainable_classifiers_fit_predict_roundtrip)."},
    "ip_finder/classify/embed.py": {"why": "HTTP 모듈을 ollama.py 로 바꿨다. 동작은 같다.", "check": "ip-finder check 의 임베딩 모델 확인."},
    "ip_finder/classify/features.py": {"why": "새 파일. 단서 행렬과 글자 n-gram 해시.", "check": "tests/test_classify.py::test_feature_builders."},
    "ip_finder/classify/proto.py": {"why": "옛 ZeroShotClassifier 를 새 틀로. 신뢰도 공식을 분류기 안으로 옮겼다(점수 모듈에서 제거).", "check": "test_zero_shot_with_fake_embedder: 신뢰도 0.65~0.9."},
    "ip_finder/classify/neighbors.py": {"why": "새 파일. k-NN 과 등급 평균 벡터.", "check": "합성 데이터 정확도 90% 이상(test_trainable_classifiers_fit_predict_roundtrip)."},
    "ip_finder/classify/linear.py": {"why": "옛 TrainedClassifier(소프트맥스)를 공통 부모로 일반화하고 일대다 로지스틱·n-gram 소프트맥스 추가.", "check": "같은 테스트. compare-classifiers 요약 시트."},
    "ip_finder/classify/cue_rules.py": {"why": "새 파일. 정규식만 쓰는 기준선 분류기.", "check": "tests/test_classify.py::test_cue_rules."},
    "ip_finder/classify/cv.py": {"why": "새 파일. 층화 k 겹과 교차 검증 밖 판정(학습·비교가 공유).", "check": "test_cross_validation_helpers: 겹마다 등급 다섯."},
    "ip_finder/post/__init__.py": {"why": "상태 상수와 status_of 공개.", "check": "import 확인."},
    "ip_finder/post/scoring.py": {"why": "신뢰도는 분류기 신뢰도 그대로(LLM 분기 삭제). 상태 이름 상수와 status_of 추가.", "check": "tests/test_post.py::test_apply_scores_and_statuses."},
    "ip_finder/history/diff.py": {"why": "설정 이름표에 스위치를 등록부에서 자동으로 넣는다. 판정 주체는 분류기/골드.", "check": "두 번 실행한 결과의 '변경 사항' 시트 설정 행에 '스위치 …: 끔 → 켬'."},
    "ip_finder/eval/__init__.py": {"why": "후보 지표(candidate_metrics)와 gold_batch 공개.", "check": "import 확인."},
    "ip_finder/eval/gold.py": {"why": "골드 시트가 분류기 판정으로 초안을 채우고 메타에 분류기·스위치를 적는다. rubric.md 경로 이동.", "check": "tests/test_eval.py::test_gold_sheet_and_scoring."},
    "ip_finder/eval/feedback.py": {"why": "새 시트 이름(분류기 제외·후처리 제외)을 읽고 옛 이름도 호환.", "check": "tests/test_eval.py::test_feedback_import_builds_and_merges_gold."},
    "ip_finder/eval/train.py": {"why": "어떤 학습형 분류기든 이름으로 학습해 classifier_dir/<이름>.npz 로 저장.", "check": "tests/test_eval.py::test_train_each_classifier_and_use_it (5종)."},
    "ip_finder/eval/score.py": {"why": "LLM 없는 재실행 채점, 거시 F1 과 후보 재현율·정밀도 추가.", "check": "ip-finder eval <골드> 출력."},
    "ip_finder/eval/rubric.md": {"why": "label/prompts 에서 옮겨 왔다(내용 동일).", "check": "골드 시트 '안내' 시트에 들어간다."},
    "ip_finder/compare/__init__.py": {"why": "새 패키지. 비교 도구 묶음.", "check": "tests/test_compare.py 전체."},
    "ip_finder/compare/matching.py": {"why": "새 파일. 문장 맞추기 동일→포함→유사.", "check": "test_match_texts_three_levels."},
    "ip_finder/compare/records.py": {"why": "새 파일. 결과를 Excel 에서 읽어 비교·골드 채점.", "check": "test_record_roundtrip_through_excel, test_compare_records_kinds, test_gold_metrics_with_matching."},
    "ip_finder/compare/classifiers.py": {"why": "새 파일. 7종 교차 검증 비교.", "check": "test_compare_classifiers_on_fake_gold; 회사 PC: compare_classifiers.bat."},
    "ip_finder/compare/ladder.py": {"why": "새 파일. 스위치 사다리(누적/단독).", "check": "test_ladder_cumulative_and_single; 회사 PC: ladder.bat."},
    "ip_finder/compare/xlsx.py": {"why": "새 파일. 비교 Excel 세 가지.", "check": "시트 이름 검사 테스트들."},
    "ip_finder/compare/markdown.py": {"why": "새 파일. 보고서용 Markdown 요약(숫자만).", "check": "각 명령 출력 끝의 .md 파일."},
    "ip_finder/report/parse_view.py": {"why": "새 파일. 리더가 무엇을 읽어 냈는지 사람이 눈으로 점검하는 HTML(쪽 그림 + 레이아웃/원시 줄 + 규칙이 뺄 줄 + ⚠ 표시).", "check": "ip-finder parse demo/sample_report.pdf --open; tests/test_parse_view.py."},
    "ip_finder/report/xlsx.py": {"why": "시트 재구성(2차 제외 → 후처리 제외, 전처리 제외 추가), 확신 열, 실행 정보의 스위치 표·설정 행.", "check": "tests/test_pipeline.py::test_baseline_runs_classifier_on_every_line 의 시트·열 검사."},
    "tools/setup_windows.py": {"why": "LLM 모델 내려받기 삭제, 임베딩 모델만 필수.", "check": "install.bat 재실행 시 bge-m3 만 확인."},
    "ip_finder.example.toml": {"why": "새 설정 체계(분류기·스위치) 예시.", "check": "복사해 ip_finder.toml 로 쓰면 Config.load 가 읽는다."},
    "README.md": {"why": "1.0 계열 설명서로 다시 썼다(0.6.2 설명은 태그).", "check": "—"},
    "RELEASE_NOTES.md": {"why": "1.0.0.dev1 항목(설치 방법 포함) 추가.", "check": "—"},
    "tests/conftest.py": {"why": "가짜 LLM 삭제, 기준선/전부 켬 설정 픽스처.", "check": "pytest -q 84 passed."},
}
for p in ("tests/test_parse_view.py", "tests/test_pipeline.py", "tests/test_compare.py", "tests/test_classify.py", "tests/test_prep.py", "tests/test_post.py", "tests/test_eval.py", "tests/test_cli.py", "tests/test_ui.py", "tests/test_readers.py"):
    META.setdefault(p, {"why": "새 구조에 맞춰 다시 쓴 테스트(Ollama 없이 가짜 임베더·가짜 보고서로 돈다).", "check": ".venv/bin/python -m pytest -q"})
for p in ("docs/stages/README.md", "docs/stages/00-baseline.md", "docs/stages/01-classifier.md", "docs/stages/02-preprocessing.md", "docs/stages/03-llm.md"):
    META.setdefault(p, {"group": "문서·설정·배치", "why": "단계별 가설·측정 방법·결과표(회사 PC 에서 채움).", "check": "—"})
for p in ("ladders/switches.toml", "ladders/classifiers.toml"):
    META.setdefault(p, {"group": "문서·설정·배치", "why": "사다리 설정 예시.", "check": "ip-finder ladder … --ladder 이 파일"})
for p in ("parse.bat", "run_all.bat", "ladder.bat", "compare_runs.bat", "compare_classifiers.bat"):
    META.setdefault(p, {"group": "문서·설정·배치", "why": "회사 PC 에서 더블클릭·명령줄로 실험 명령을 부르는 ASCII 배치 파일.", "check": "인자 없이 실행하면 사용법."})
META.setdefault("tools/setup_windows.py", {"group": "문서·설정·배치", "why": "LLM 모델 내려받기 삭제.", "check": "install.bat"})
META.setdefault("ip_finder.example.toml", {"group": "문서·설정·배치", "why": "새 설정 예시.", "check": "—"})
META.setdefault("README.md", {"group": "문서·설정·배치", "why": "1.0 설명서.", "check": "—"})
META.setdefault("RELEASE_NOTES.md", {"group": "문서·설정·배치", "why": "릴리스 노트.", "check": "—"})
for p in ("tools/walkthrough/lib.py", "tools/walkthrough/build_full.py", "tools/walkthrough/build_review.py", "tools/walkthrough/files.py", "tools/walkthrough/review_meta.py", "tools/walkthrough/migrate_notes.py"):
    META.setdefault(p, {"group": "개발 도구", "why": "코드 리뷰 페이지 빌더(줄마다 설명). 프로그램 의존성 아님.", "check": "python tools/walkthrough/build_full.py → 설명 없는 줄 0"})
