# IP Finder

보고자료(PDF / PPTX)를 읽어 **특허팀과 논의할 만한 기술 문장을 빠짐없이 뽑고, 단서 등급(A/B/C/D)을 붙인 Excel 목록**을 만드는 도구입니다.
판정은 PC 안의 로컬 LLM(Ollama)이 하고, 외부로는 아무것도 보내지 않습니다. GPU 없는 윈도우 PC(RAM 16GB)에서 돌아가도록 설계했습니다.

- 원본 파일은 읽기만 하고 수정하지 않습니다. 결과는 원본 옆에 `<이름>_검토후보.xlsx` 로 생깁니다.
- 이 단계에서 신규성·진보성은 판단하지 않습니다. 구체적 수단이 없어도 효과, 과제, 변경 의도만 있으면 후보로 올립니다. 최종 판단은 사람이 합니다.
- 설계 배경과 결정 사항은 [PROPOSAL.md](PROPOSAL.md), 입력과 출력 예시는 [EXAMPLE.md](EXAMPLE.md), 모델 실험 기록은 [demo/](demo/README.md)에 있습니다.

## 단서 등급

| 등급 | 의미 | 특허팀 논의 포인트 (자동 기입) |
|---|---|---|
| A 수단 명시 | 구조, 재료, 공정 조건, 알고리즘, 파라미터 등이 문장 안에 직접 적힘 | 기존 방식과 무엇이 다른가. 변형 가능한 범위는. |
| B 효과 기재 | 개선, 저감, 수치 비교, 기존 대비. 수단은 없음 | 이 효과를 얻은 구체적 수단은 무엇인가. |
| C 과제 제기 | 현상, 불량 원인, 메커니즘, 기존 방식의 한계 | 이 문제의 해결 수단이 있는가, 시도 중인가. |
| D 변경 시사 | 적용 예정, 검토 중, 도입 계획 | 변경 내용의 구체적 구성은 무엇인가. |
| X 제외 | 일정, 비용, 인력, 고객 대응, 표준 개정, 단순 현황 | 리포트에 싣지 않음. 기술 단서어가 있으면 `X?`로 보류 시트에 |

기준 전문은 [ip_finder/label/prompts/rubric.md](ip_finder/label/prompts/rubric.md), LLM에 들어가는 압축판은 [system.md](ip_finder/label/prompts/system.md)입니다. 회사 보고서에 맞게 고쳐 쓰면 됩니다.

## 다운로드

- 저장소: https://github.com/HyungKim/IP_finder
- 소스 ZIP: https://github.com/HyungKim/IP_finder/archive/refs/heads/main.zip (저장소 페이지의 **Code → Download ZIP** 과 같음)
- 릴리스: https://github.com/HyungKim/IP_finder/releases/latest — 소스 ZIP과 **윈도우 오프라인 설치용 wheel 번들** `ip_finder_wheels_win_amd64_py312.zip`(Python 3.12 64비트용, 38MB). 다른 Python 버전용 번들은 `tools\download_wheels.bat`로 만듭니다.

저장소는 공개이므로 로그인 없이 받을 수 있습니다. 실제 보고서, 골드 세트, 결과 파일은 절대 이 저장소에 올리지 마세요.

## 윈도우 간편 설치 (install.bat)

1. Python 3.12 64비트를 설치합니다 (https://www.python.org/downloads/windows/ , "Add python.exe to PATH" 체크).
2. Ollama를 설치합니다 (https://ollama.com/download/windows).
3. 소스 ZIP을 풀고 `install.bat`를 더블클릭합니다. 가상환경 생성, 패키지 설치, 모델 내려받기(`qwen3:4b-instruct`, 약 2.5GB), 환경 확인까지 자동으로 진행됩니다.
4. `extract.bat` 위로 보고서 파일이나 폴더를 끌어다 놓으면 원본 옆에 `이름_검토후보.xlsx`가 생깁니다. 명령줄에서는 `extract.bat 보고서.pptx`.

인터넷이 막힌 PC라면:
- 패키지: 릴리스의 wheel 번들을 받아 압축을 풀고, 생긴 `wheels` 폴더를 `install.bat` 옆에 둔 뒤 실행합니다. `wheels` 폴더가 있으면 PyPI에 접속하지 않습니다. 다른 Python 버전이면 인터넷이 되는 윈도우 PC에서 `tools\download_wheels.bat 3.13` 처럼 실행해 번들을 직접 만듭니다.
- 모델: 다른 PC에서 `ollama pull qwen3:4b-instruct` 후 `%USERPROFILE%\.ollama\models` 폴더를 복사합니다.

배치 파일은 Python을 찾아 가상환경을 만드는 일만 하고, 패키지 설치, Ollama와 모델 확인, 환경 점검은 `tools/setup_windows.py`가 합니다. 그래서 Python을 찾기 전까지의 메시지는 영어이고 그 뒤부터 한글입니다. 패키지를 설치하지 않고 저장소 폴더에서 `python -m ip_finder.cli`로 실행하므로 아래의 `pip install -e .` 없이도 동작합니다.

문제 해결
- `'...'은(는) 내부 또는 외부 명령, 실행할 수 있는 프로그램, 또는 배치 파일이 아닙니다.` — v0.1.0의 배치 파일에 한글이 들어 있어 생기던 문제입니다. 한글 Windows의 cmd.exe는 UTF-8 모드에서 다중 바이트 문자가 있는 줄의 위치를 잘못 계산해 줄의 나머지를 명령으로 실행합니다. v0.1.1부터 배치 파일은 ASCII만 쓰므로 최신 ZIP을 다시 받으세요.
- 콘솔에서 한글이 네모로 보이면 창 속성에서 글꼴을 '맑은 고딕'이나 'Consolas'로 바꾸세요.
- `py` 런처도 `python`도 없다고 나오면 Python 설치 시 "Add python.exe to PATH"를 체크하지 않은 것입니다. 재설치하거나 PATH에 추가하세요.

## 요구 사항

- Windows 10/11 또는 macOS. Python 3.11 이상 (3.12 권장).
- [Ollama](https://ollama.com) 와 모델 `qwen3:4b-instruct` (약 2.5GB). 메모리 약 3GB 사용.
- 선택: 구형 `.ppt` 입력은 PowerPoint가 설치된 윈도우에서 `pywin32`로 자동 변환합니다.

## 설치 (명령줄, macOS/Linux/윈도우 공통)

```bash
git clone https://github.com/HyungKim/IP_finder.git
cd IP_finder
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -e .                # 윈도우에서 .ppt 변환까지: pip install -e ".[windows]"
ollama pull qwen3:4b-instruct
ip-finder check
```

`ip-finder check`가 의존성, Ollama 연결, 모델 설치 여부를 확인합니다. 윈도우 콘솔에서 한글이 깨지면 환경변수 `PYTHONUTF8=1`을 설정하세요.

모델을 직접 내려받을 수 없는 PC라면 다른 PC에서 `ollama pull` 한 뒤 Ollama 모델 폴더(윈도우 `%USERPROFILE%\.ollama\models`)를 통째로 복사하면 됩니다.

## 사용

```bash
ip-finder extract 보고서.pptx                 # 결과: 보고서_검토후보.xlsx (원본 옆)
ip-finder extract 보고서.pdf 다른보고서.pptx    # 여러 파일
ip-finder extract 보고서폴더/ --out-dir 결과/   # 폴더 전체(하위 폴더 포함), 결과를 한곳에
ip-finder extract 보고서.pptx --model qwen3:8b  # 모델 교체 (think 계열도 자동으로 think=false)
```

진행률이 페이지마다 찍히고, 중간에 끊어도 이미 처리한 페이지는 캐시에 남아 다음 실행에서 바로 재사용됩니다. 캐시에는 페이지 텍스트의 해시와 라벨만 저장되며 원문은 저장되지 않습니다 (`~/.ip_finder/cache.sqlite`, `--no-cache`로 끔).

### 결과 Excel의 시트

| 시트 | 내용 |
|---|---|
| 검토 목록 | A/B/C/D 문장을 페이지 순서로. 번호, 섹션, 페이지, 등급, 발췌(원문 그대로), 논의 포인트, 비고 |
| 보류 | 모델은 제외(X)로 보았지만 기술 단서어가 있어 남긴 문장 (`X?`). 판정 실패(`?`)도 여기에 |
| 제외 페이지 | 표지, 목차, 일정, 비용, 조직, 감사 등 제목 규칙으로 건너뛴 페이지와 사유 |
| 이미지 페이지 | 텍스트가 없는 페이지. 도면이면 직접 확인 |
| 실행 정보 | 모델, 프롬프트 버전, 소요 시간, 등급 분포, 전처리로 제거된 줄 수, 경고 |

비고 열의 `보정(A→C)`는 제목이 원인·문제·배경인 페이지에서 변경 동사가 없는 A를 C로 내린 행입니다. `분할`은 긴 줄을 문장으로 나눈 행, `표`는 표에서 나온 행입니다.

### 처리 흐름

1. **읽기**: PDF는 PyMuPDF, PPTX는 python-pptx. 제목, 본문 줄(불릿 계층), 표를 읽습니다. 발표자 노트는 읽지 않습니다.
2. **전처리(규칙, LLM 없음)**: 제목 규칙으로 페이지 제외 → 세 페이지 이상 반복되는 줄(머리말·바닥글) 제거 → 날짜·금액·담당자·짧은 조각 제거(보수적, 기술 단서어가 있으면 유지) → 줄 번호 부여, 80자 초과는 문장 분할.
3. **라벨링**: 페이지마다 LLM을 한 번 불러 줄 수와 같은 길이의 라벨 배열만 받습니다. 주제명이나 질문은 생성하지 않습니다. 출력이 20토큰 안팎이라 CPU에서도 빠릅니다.
4. **후처리(규칙)**: 제목 기반 보정, 재현율 안전장치(`X?`), 섹션 묶기, 논의 포인트 템플릿.
5. **출력**: Excel.

### 설정 파일 `ip_finder.toml` (선택)

현재 폴더에 두면 자동으로 읽습니다. `--config 경로`로 지정할 수도 있습니다.

```toml
model = "qwen3:4b-instruct"
host = "http://127.0.0.1:11434"      # 로컬 주소만 허용. 외부 주소는 실행이 거부됩니다
num_ctx = 2048
split_len = 80
repeated_line_min_pages = 3
stoplist = ["대외비", "Confidential", "○○전자 품질혁신팀"]   # 회사 템플릿의 고정 문구
page_exclude_patterns = ["목\\s*차", "일정", "비용", "예산", "조직", "감사합니다", "Q\\s*&\\s*A", "참고\\s*문헌", "부록"]
title_fix = true
safety_net = true
use_cache = true
cache_path = "~/.ip_finder/cache.sqlite"
```

## 정확도 관리: 골드 세트

프롬프트, 규칙, 모델을 바꿀 때 좋아졌는지 숫자로 확인하려면 정답 세트가 필요합니다.

```bash
ip-finder gold-sheet 실제보고서.pptx            # 실제보고서_gold.xlsx 생성 (모델 초안 라벨 포함)
# '라벨링' 시트의 '정답' 열에서 틀린 등급만 고친다 (A/B/C/D/X)
ip-finder eval 실제보고서_gold.xlsx            # 현재 모델·프롬프트로 다시 라벨링해 채점
ip-finder eval 실제보고서_gold.xlsx --stored   # 시트에 저장된 라벨을 채점 (LLM 불필요)
```

정확도, 등급별 정밀도·재현율·F1, 혼동 행렬이 출력됩니다. 실제 보고서 2~3건에서 100~200문장이면 충분합니다.
**골드 파일에는 실제 문장이 들어 있으므로 저장소 바깥에 두세요.** (`.gitignore`가 `gold/`와 `*_gold.xlsx`를 제외합니다.)

## 보안

- 모든 LLM 호출은 `127.0.0.1`의 Ollama로만 갑니다. 설정에 외부 주소를 넣으면 실행 자체가 거부됩니다 (`tests/test_llm.py`).
- 외부 서비스 SDK, 텔레메트리, 자동 업데이트가 없습니다. 의존성은 PyMuPDF, python-pptx, openpyxl 뿐입니다.
- 캐시와 로그에 원문을 남기지 않습니다.
- 실제 보고서와 골드 세트는 저장소 바깥 폴더에 두고, 코드 작성에 AI 도구를 쓸 때 그 폴더를 열지 마세요.
- 오프라인 확인: 윈도우 방화벽에서 `python.exe`와 `ollama.exe`의 아웃바운드를 차단해도 정상 동작해야 합니다. 윈도우 방화벽은 루프백(127.0.0.1)을 막지 않으므로 Ollama 연결은 유지됩니다.

  ```bat
  netsh advfirewall firewall add rule name="ip-finder python block" dir=out program="C:\경로\.venv\Scripts\python.exe" action=block
  netsh advfirewall firewall add rule name="ollama block" dir=out program="C:\Users\<이름>\AppData\Local\Programs\Ollama\ollama.exe" action=block
  ```

## 테스트

```bash
pip install -e ".[dev]"
pytest
```

테스트는 가짜 LLM 클라이언트를 써서 Ollama 없이 오프라인으로 돕니다. 설명용 가짜 보고서(`demo/sample.json`)로 PPTX와 PDF를 만들어 읽기, 전처리, 후처리, 리포트, 캐시, 골드 세트 채점을 검증합니다.

## 성능 참고

같은 12장 샘플 기준, GPU 가속이 되는 Apple M4에서 4B 모델로 8~9초였습니다. CPU 전용 PC에서는 5~8배 느릴 것으로 추정하며, `demo/speed_test2.py`를 돌리면 그 PC의 페이지당 시간을 2분 안에 잴 수 있습니다. 50장 보고서면 4B 기준 3~8분이 목표입니다.

## 폴더 구조

```
ip_finder/
  readers/   pdf_reader.py, pptx_reader.py, ppt_convert.py   입력 → Document
  prep/      page_rules.py, line_rules.py, splitter.py        전처리 규칙
  label/     labeler.py, prompts/system.md, prompts/rubric.md 라벨링
  post/      title_fix.py, safety_net.py, sections.py, templates.py
  report/    xlsx.py
  llm/       ollama_client.py   localhost 전용
  cache/     store.py           SQLite, 해시 + 라벨만
  eval/      gold.py, score.py  골드 세트
  cues.py, config.py, models.py, pipeline.py, cli.py, samples.py
install.bat, extract.bat, tools/download_wheels.bat   윈도우 설치·실행·오프라인 번들 스크립트
requirements.txt, requirements-windows.txt
tests/       오프라인 테스트
demo/        가짜 샘플, 시연·속도 실험 스크립트와 결과
archive/     이전 제안서(v1 마킹, v2 추출 초안)
```

## 로드맵

- 2단계: A·B 문장만 8B로 재확인하는 혼합 모드(일치 여부 = 신뢰도), Word 회의 자료 + 페이지 썸네일, 저자 강조(기존 하이라이트·볼드) 신호, 임베딩 기반 '관련 항목' 열
- 3단계: 보고서 여러 건 통합 워크북, 이전에 논의한 주제와의 유사 표시, 발표자 노트 포함 옵션, GPU 확보 시 그림 페이지 처리
