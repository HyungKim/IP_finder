# demo: 추출 파이프라인 시연과 속도 실험

가짜 12장 보고서(`sample.json`)를 로컬 Ollama 모델로 처리한 기록입니다.
Python 표준 라이브러리만 사용하고 `127.0.0.1:11434`만 호출합니다. 외부 통신 없음.

## 파일

| 파일 | 내용 |
|---|---|
| `sample.json` | 설명용 가짜 보고서. 실제 사내 자료 아님 |
| `sample_report.pptx`, `sample_report.pdf` | 위 JSON으로 만든 가짜 보고서 파일. `python -m ip_finder.samples demo` 로 재생성 |
| `layout/layout_01~05_*.pdf` | 레이아웃 시험용 가짜 보고서 5건(단일 단 불릿, 2단·3단 문서, 블록도·차트·사진, 표 중심, 영문 혼용·회전 페이지). `python -m ip_finder.layout_samples demo/layout` 로 재생성. 모든 회사·제품·수치는 지어낸 것 |
| `sample_report_pptx_검토후보.xlsx`, `sample_report_pdf_검토후보.xlsx` | `ip-finder extract` 가 만든 결과 예시 (qwen3:4b-instruct) |
| `run_demo.py` | v2 초안 방식 시연: 규칙 필터 → LLM 제목 필터 → 페이지별 추출(주제명·질문 생성) → LLM 병합. 기록용 |
| `results_4b.json` | run_demo, qwen3:4b-instruct (M4, 총 100초) |
| `results_8b_nothink.json` | run_demo, qwen3:8b, thinking 끔 (M4, 총 200초) |
| `results_8b_think_on.json` | run_demo, qwen3:8b, thinking 켠 상태. 필터·병합이 빈 결과로 끝난 실패 사례 |
| `speed_test.py` | v3 방향 실험 1: 라벨만 출력(id 칸 있음) + bge-m3 임베딩 사전 필터 측정 |
| `speed_test2.py` | **v3 방식 기준 스크립트**: 길이 고정 라벨 배열 스키마, 프롬프트 v1/v2, 4B vs 8B 비교 |
| `speed_results.json` | speed_test2 결과 요약 |
| `prep_experiment.py` | 전처리 변형 비교: 페이지 유형 힌트, 묶음 호출, 압축 프롬프트 (EXAMPLE.md 6절) |
| `hybrid_experiment.py` | 분류기 선별 후 LLM 구조 비교: X 제거 / 애매한 문장만 유형별 묶음 호출 (EXAMPLE.md 6절) |

채점과 시사점은 상위 폴더 `EXAMPLE.md` 4~5절에 있습니다. 구현 브리프는 `PROPOSAL.md`.

## 실행

```bash
ip-finder extract demo/sample_report.pptx     # 본 도구로 샘플 처리
python3 speed_test2.py                        # 모델별 라벨 속도·정확도 비교
```

`speed_test2.py`는 `speed_test.py`의 앞부분(프롬프트, 정답 세트, 호출 함수)을 읽어 쓰므로 두 파일이 같은 폴더에 있어야 합니다. `prep_experiment.py`와 `hybrid_experiment.py`는 저장소 루트의 패키지를 쓰므로 저장소 안에서 실행합니다(`bge-m3` 필요).
모델 이름은 스크립트 안의 `run(...)` 호출에서 바꿉니다. qwen3 thinking 계열은 `think=false`로 호출합니다.

## 회사 PC에서 쓸 때

- 목적은 환경 점검과 모델별 페이지당 시간 실측입니다. 실제 보고서를 `sample.json` 형식으로 넣지 마세요.
- Ollama 설치 후 `ollama pull qwen3:4b-instruct` (약 2.5GB). 8B 비교가 필요하면 `ollama pull qwen3:8b` (약 5.2GB).
- KURE-v1 임베딩 비교는 `tools\import_kure.bat` 로 들여온 뒤 `ip-finder extract ... --mode fast --embed-model kure-v1` 과 `bge-m3` 를 골드 시트로 `eval` 해 비교합니다.
- v0.4.0 의 세 모드·두 임베딩 실측(M4)은 상위 README '성능 참고' 절에 있습니다.
- CPU 전용이면 M4 대비 5~8배 느릴 것으로 추정합니다. 4B 라벨만 출력 기준 7페이지에 1~2분이면 정상 범위입니다.
