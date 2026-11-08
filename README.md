# IP Finder (rebuild 1.0 계열)

보고자료(PDF/PPTX)에서 특허 검토 후보 문장을 골라 **등급(A/B/C/D/X)과 점수**를 붙인 Excel 을 만드는 온디바이스 도구입니다. 모든 처리는 PC 안에서만 일어나며, 외부로는 아무것도 보내지 않습니다(Ollama 는 127.0.0.1 임베딩만).

**이 브랜치(`rebuild`)는 판정 파이프라인을 처음부터 단계별로 다시 쌓는 중입니다.** 0.6.2(`main`)는 "분류기 1차 → LLM 2차 + 전처리·후처리 일체"를 한 번에 돌렸지만, 어느 요소가 결과를 얼마나 바꿨는지 분리해 보여 주지 못했습니다. 1.0 은 요소를 하나씩 붙이며 **붙일 때마다 결과물의 전후 차이를 사람이 읽는 표로** 남깁니다.

| 단계 | 상태 | 내용 |
|---|---|---|
| 0 | **지금 (1.0.0.dev1)** | 기준선: 읽기 → 1차 분류기 → 점수 → Excel. 전처리·후처리는 모두 스위치, 기본 끔. LLM 없음 |
| 1 | 도구 준비됨 | 1차 분류기 7종을 골드 교차 검증으로 비교해 하나 고르기 (`compare-classifiers`) |
| 2 | 도구 준비됨 | 레이아웃 분석·전처리·후처리 스위치를 한 칸씩 켜며 기여 측정 (`ladder`) |
| 3 | 예정 | LLM 2차 판정 부착 |

단계별 가설·측정 방법·결과표는 [docs/stages/](docs/stages/README.md) 에 있습니다. 0.6.2 의 설명서는 태그 `v0.6.2` 의 README 를 보세요.

## 단서 등급

| 등급 | 뜻 | 예 |
|---|---|---|
| A | 구체적 수단(구조·방법·알고리즘)이 적힌 문장 | "접착제를 저탄성 실리콘계로 변경하여 응력 저감" |
| B | 수치 효과·결과 | "조립 수율 92.1% → 97.8%" |
| C | 과제·원인·현상 | "열팽창계수 차이로 다이에 응력 발생" |
| D | 계획·검토 중 | "차기 모델에 신규 방식 적용 예정" |
| X | 기술 내용 없음 (일정·비용·담당·영업) | "설비 투자 비용 2억 원" |

기본 추출 대상은 A·B 입니다(`target_grades`). 사람이 읽는 판정 기준은 [ip_finder/eval/rubric.md](ip_finder/eval/rubric.md).

## 다운로드와 설치

- 저장소: https://github.com/HyungKim/IP_finder — 브랜치 `rebuild` (0.6.2 는 `main`)
- 릴리스: https://github.com/HyungKim/IP_finder/releases — 1.0.0.dev* 는 **사전 릴리스**로 표시됩니다. 소스 ZIP 과 윈도우 오프라인 설치용 wheel 번들 `ip_finder_wheels_win_amd64_py312.zip`(0.5.x 부터 같음).

**윈도우 간편 설치**: Python 3.12 64비트(PATH 추가 체크), Ollama 설치 → 소스 ZIP 을 풀고 `install.bat` 더블클릭. 가상환경·패키지 설치, Ollama 확인, 임베딩 모델 `bge-m3`(약 1.2GB) 내려받기, 환경 점검까지 자동입니다. 캐시·분류기·이력·골드·설정은 **그 폴더의 `data\` 와 `ip_finder.toml`** 에만 생깁니다.
인터넷이 막힌 PC 는 wheel 번들을 풀어 `wheels` 폴더를 `install.bat` 옆에 두고, 모델은 다른 PC 에서 `ollama pull bge-m3` 후 `%USERPROFILE%\.ollama\models` 를 복사합니다.

**0.6.x 위에 올리기**: Source code (zip) 안의 내용물을 설치 폴더(`ui.bat` 가 있는 곳) 위에 덮어씁니다. `.venv`, `data\`, `ip_finder.toml` 은 그대로 남고 새 패키지는 없습니다. LLM 모델은 쓰지 않습니다. 옛 설정의 `mode`·`model` 은 무시됩니다. 0.6.x 의 `data\classifier.npz` 는 형식이 달라 쓰지 않으니 필요하면 `ip-finder train --classifier softmax` 로 다시 만듭니다. **기본값이 '스위치 전부 끔'이므로 0.6.2 와 비슷한 결과를 보려면 `--on all`(UI: 전부 켬)을 쓰세요.**

명령줄 설치(공통): `python -m venv .venv && .venv/bin/pip install -e ".[dev]"`, 그리고 `ollama pull bge-m3`.

## 쓰는 법

### 일상 실행

```bat
ui.bat                                   (창. 추출 / 페이지 가중치 / 정확도 관리 / 실험 / 변경 추적 탭)
extract.bat 보고서.pptx                   (파일·폴더를 extract.bat 위로 끌어다 놓아도 됨. 결과는 원본 옆 <이름>_검토후보.xlsx)
ip-finder extract 보고서.pdf --on all     (스위치 전부 켬)
ip-finder extract 보고서.pdf --on layout --on short_line --classifier knn
ip-finder switches                        (스위치 목록과 현재 상태)
ip-finder check                           (의존성·Ollama·임베딩 모델·분류기 파일·스위치 확인)
ip-finder pages 보고서.pdf --on page_exclude   (페이지 제목·관련성·제외 여부만)
ip-finder layout 보고서.pdf --pages 3-5        (레이아웃 분석 진단)
```

공통 옵션: `--config 파일`, `--classifier 이름`, `--embed-model 이름`, `--grades A,B,C,D`, `--accept-score 0.5`, `--on 스위치`(반복, `all`), `--off 스위치`, `--gold 경로`, `--no-gold`, `--no-cache`.

### 스위치

| 묶음 | 이름 | 설정 필드 | 켰을 때 |
|---|---|---|---|
| 읽기 | `layout` 레이아웃 분석 | `layout_analysis` | 다단 읽기 순서, 문단 묶기, 제목·표·도형 구분, ▪·│ 항목 나누기. 끄면 PDF 는 PyMuPDF 줄 그대로, PPTX 는 도형 순서대로 |
| 줄 규칙 | `short_line` 짧은 줄 제외 | `rule_short_line` | 공백 제외 `short_line_chars`(10)자 이하 제외 |
| 줄 규칙 | `korean` 한글 없음 제외 | `rule_require_korean` | 한글이 없는 줄 제외 |
| 줄 규칙 | `split_long` 긴 줄 분할 | `rule_split_long` | `split_len`(80)자 넘으면 문장으로 나눔 |
| 줄 규칙 | `repeated` 반복·고정 문구 | `rule_repeated_line` | `repeated_line_min_pages`(3)쪽 이상 반복 줄과 `stoplist` 제외 |
| 줄 규칙 | `pattern` 패턴 줄 | `rule_pattern_lines` | 숫자만, '담당:' 줄, 30자 이하 일정·금액 줄 제외 |
| 페이지 규칙 | `page_exclude` 페이지 제외 | `rule_page_exclude` | 제목이 `page_exclude_patterns` 에 걸리는 쪽 제외 |
| 페이지 규칙 | `cover` 표지 | `rule_cover` | 1쪽에 `cover_max_lines`(4)줄 이하면 표지로 제외 |
| 페이지 규칙 | `page_weight` 페이지 가중치 | `page_weight_enabled` | 관련성 낮음 쪽 가중치 `low_relevance_weight`(0.4) |
| 후처리 | `title_fix` 제목 보정 | `title_fix` | 원인·문제 쪽의 변경 동사 없는 A → C |
| 후처리 | `safety_net` 안전망 | `safety_net` | 단서어 있는 X → X? (보류 시트) |

글이 전혀 없는 쪽(이미지 페이지)은 스위치와 무관하게 판정할 것이 없어 늘 제외됩니다.

### 1차 분류기

| 이름 | 학습 | 임베딩 | 설명 |
|---|---|---|---|
| `proto` (기본) | X | O | 등급별 원형 문장([prototypes.json](ip_finder/classify/prototypes.json))과의 코사인 유사도. 신뢰도 = min(0.9, 0.65 + 1위−2위) |
| `knn` | O | O | 가장 가까운 골드 문장 `knn_k`(5)개의 유사도 가중 다수결. 신뢰도 = 1위 등급 투표 비율 |
| `centroid` | O | O | 등급별 골드 임베딩 평균 벡터와의 코사인. 신뢰도 = 코사인에 소프트맥스 |
| `softmax` | O | O | 소프트맥스 회귀 (임베딩 + 단서 특성 13개, 표준화, 경사하강법). 신뢰도 = 1위 확률 |
| `ovr` | O | O | 일대다 로지스틱 (등급마다 독립 시그모이드). 모두 낮으면 '모름'에 가까움 |
| `cue` | X | X | 단서어 정규식 규칙. 기계학습 없는 비교 기준 |
| `ngram` | O | X | 글자 2·3-gram 해시(4096차원) + 소프트맥스. 임베딩 모델 없이 동작 |

학습형은 골드로 먼저 만듭니다: `ip-finder train --classifier knn` → `data\classifiers\knn.npz` (임베딩 모델이 설정과 다르면 거부). 신뢰도(0~1)는 모두 "1위 등급이 맞을 확률의 추정"으로 통일되어 점수 = 신뢰도 × 페이지 가중치가 분류기 종류와 무관하게 같은 뜻입니다.

### 결과 Excel 의 시트

| 시트 | 내용 |
|---|---|
| 검토 목록 | 대상 등급으로 통과하고 점수 ≥ `accept_score` 인 문장. 번호·섹션·페이지·줄·등급·발췌·논의 포인트·점수·가중치·**확신**(분류기 신뢰도)·판정(분류기/골드)·비고·피드백·메모 |
| 보류 | 점수 미달, X?(안전망), 판정 실패. '보류 사유' 열 |
| 분류기 제외 (참고) | 분류기가 대상 등급 밖(C·D·X)으로 본 문장 |
| 후처리 제외 | 분류기는 통과시켰지만 보정·골드가 대상 등급 밖으로 바꾼 문장 |
| 전처리 제외 | 줄 규칙에 걸린 줄(사유 = 규칙 이름)과 제외된 쪽의 줄(사유 = 쪽 제외 사유). **스위치가 무엇을 뺐는지 여기서 본다** |
| 페이지 | 쪽마다 제목·관련성·가중치·상태·상태별 문장 수·제목 출처 |
| 변경 사항 | 같은 파일의 직전 실행과 비교(이력 기준): 진입·이탈·등급·점수·문장 변경, 달라진 설정 |
| 제외 페이지 / 이미지 페이지 | 쪽 단위 제외 목록 |
| 실행 정보 | 버전·단계·읽기 방식·스위치 표·분류기·시간·등급 분포, 그리고 `설정 <이름>` 행(비교 명령이 읽음) |

피드백: 검토 목록·보류·제외 시트의 '피드백' 열에 `O`(맞음) / `X`(틀림) / `A~D`(올바른 등급)를 적고 `ip-finder feedback <결과.xlsx>` → `data\gold\<이름>_gold.xlsx`. 골드 폴더의 문장은 다음 실행부터 분류기 판정 대신 골드 정답을 씁니다(`use_gold`; 실험 명령은 자동으로 끕니다).

### 실험: 개량 전후를 비교하기

실제 보고서는 회사 PC 에만 있으므로 비교 도구는 모두 프로그램 안에 있고, 결과는 Excel 과 **보고서에 붙일 Markdown 요약**(숫자만, 문장 없음)으로 나옵니다.

```bat
rem 0) 기준선 결과 폴더
run_all.bat results\s0-baseline D:\reports

rem 1) 분류기 고르기: 골드(data\gold)로 7종 교차 검증 → 분류기_비교.xlsx + .md
compare_classifiers.bat --out results\classifiers.xlsx
rem    실제 보고서 위에서 후보 수·시간 비교 (학습형은 train 먼저)
ladder.bat results\ladder_classifiers D:\reports --ladder ladders\classifiers.toml

rem 2) 스위치 사다리: 기준선 → +레이아웃 → +짧은 줄 → ... 칸마다 직전 칸과 비교
ladder.bat results\ladder_switches D:\reports
ladder.bat results\ladder_single   D:\reports --mode single     (기준선에 한 칸만: 독립 기여)

rem 3) 아무 결과 둘을 직접 비교 (파일 또는 폴더)
compare_runs.bat results\s0-baseline results\ladder_switches\step-02-short_line
```

- **사다리**(`ladder`): 칸마다 모든 파일을 다시 실행해 `step-XX-이름\` 폴더에 결과를 두고, `사다리_*.xlsx` 의 '사다리 요약'(칸마다 문장 단위·상태별 수·검토 목록 증감·골드 재현율·정밀도·시간), '칸별 변화'(들어오고 나간 문장을 이전·현재 나란히), '변경 종류별', '파일별', '칸 설정' 시트를 만듭니다. 칸 순서와 내용은 `ladders\*.toml` 로 바꿉니다(스위치뿐 아니라 `set = { classifier = "knn" }` 처럼 어떤 설정이든).
- **결과 비교**(`compare-runs`): 두 결과를 문장 단위로 맞춥니다 — 동일(공백 무시) → 포함(여러 줄이 한 문단으로 합쳐짐 / 한 문장이 여러 줄로 나뉨) → 유사(글자 일치 0.6 이상). 변경 종류: 검토 목록 진입·이탈, 등급 변경, 점수 변경, 상태 변경, 문장 합쳐짐·나뉨·변경, 새 문장, 사라진 문장. 결과 파일의 '설정 ' 행으로 설정 차이도 적습니다.
- **분류기 비교**(`compare-classifiers`): 학습형은 층화 5겹 교차 검증을 seed 를 바꿔 2회(표준편차), 학습 없는 것은 전체 골드 채점. 요약·등급별·혼동 행렬·문장별(어느 분류기가 어느 문장을 틀렸나)·불일치 시트. 골드가 100문장 미만이면 표준편차보다 작은 차이는 잡음입니다.
- 모든 지표는 단계가 바뀌어도 같습니다: A·B 재현율(놓침), A·B 정밀도(검토 부담), 등급 정확도·거시 F1, 검토 목록 수, 처리 시간. 골드 채점도 같은 문장 맞추기 규칙을 씁니다(`gold_metrics`).

UI 의 **실험 탭**에서도 사다리 실행과 결과 비교를 할 수 있습니다.

### 설정 파일 `ip_finder.toml`

[ip_finder.example.toml](ip_finder.example.toml) 을 복사해 설치 폴더에 두면 자동으로 읽습니다(UI '설정 저장'으로도 만듦). 스위치는 `rule_short_line = true` 처럼 Config 필드 이름으로 적습니다.

## 처리 흐름과 코드 구조

```
읽기 readers/ (layout_analysis 스위치: 레이아웃 분석 | 원시)        → Document(pages → lines)
전처리 prep/ (줄 규칙 5개, 페이지 규칙 3개: 스위치)                  → removed_by / excluded_reason
임베딩 classify/embed.py (필요한 분류기만, SQLite 캐시 해시→벡터)
1차 분류기 classify/ (7종, 같은 fit/predict 인터페이스)               → LabeledLine(label, clf_conf)
후처리 post/ (title_fix, safety_net: 스위치) → 골드 반영 → 단계 확정 → 점수 post/scoring.py
이력 history/ (문장 해시만) → Excel report/xlsx.py
비교 compare/ (records·matching·classifiers·ladder·xlsx·markdown)
```

| 폴더/파일 | 역할 |
|---|---|
| `ip_finder/config.py`, `switches.py` | 설정(스위치 기본 끔)과 스위치 목록(이름·필드·설명) |
| `ip_finder/pipeline.py` | 한 파일의 처리 흐름 `run_file`/`extract`. CLI·UI·실험이 공유 |
| `ip_finder/readers/` | PDF(PyMuPDF)·PPTX(python-pptx) 리더. `layout=False` 가 원시 읽기 |
| `ip_finder/prep/` | 줄 규칙(`line_rules.py`), 분할(`splitter.py`), 페이지 규칙·유형·가중치 |
| `ip_finder/classify/` | `base.py`(Prediction·Batch·Classifier), `proto/neighbors/linear/cue_rules/features/cv.py`, `embed.py` |
| `ip_finder/post/` | 보정·안전망·섹션·점수(`scoring.py`: 상태 네 가지) |
| `ip_finder/compare/` | 비교 도구 (위 '실험') |
| `ip_finder/eval/` | 골드 시트·피드백·학습·채점, `rubric.md` |
| `ip_finder/report/xlsx.py` | 결과 Excel |
| `ip_finder/history/` | 실행 스냅샷(원문 미저장)과 직전 실행 비교 |
| `ip_finder/cli.py`, `ui.py` | 명령줄, Tkinter UI |
| `ip_finder/samples.py`, `layout_samples.py` | 테스트·데모용 가짜 보고서 생성 (실제 자료는 저장소에 없음) |
| `ladders/`, `docs/stages/` | 사다리 설정 예시, 단계별 기록 |
| `tools/walkthrough/` | 코드 리뷰 페이지(줄마다 설명) 빌더 — 개발용, 프로그램 의존성 아님 |

## 보안

- 네트워크는 127.0.0.1 Ollama 의 `/api/embed`·`/api/tags` 뿐이며 다른 호스트는 생성 단계에서 거부(`ollama.assert_local`).
- 캐시(`data/cache.sqlite`)와 이력(`data/history`)에는 원문이 없습니다(해시·벡터·라벨만). 결과 Excel·골드 시트·실험 결과 폴더에는 문장이 있으므로 회사 PC 밖으로 내보내지 않습니다.
- Markdown 요약(`.md`)은 숫자만 담으므로 보고서에 붙여도 됩니다.
- 저장소에는 가짜 샘플만 있습니다. `data/`, `*_gold.xlsx`, `*_검토후보.xlsx`, `*.npz` 는 `.gitignore` 로 막혀 있습니다.

## 테스트

```bash
.venv/bin/python -m pytest -q      # 84건, Ollama 없이 (가짜 임베더·가짜 보고서)
```

## 요구 사항

Python 3.11+, PyMuPDF, python-pptx, openpyxl, numpy (추가 의존성 없음). 윈도우 선택: pywin32(.ppt 변환). Ollama + `bge-m3`(임베딩을 쓰는 분류기만). GPU 불필요(CPU 16GB 에서 동작).
