# IP Finder v0.2.0

판정 방식을 **hybrid**로 바꿨습니다. 임베딩 분류기(bge-m3)가 모든 문장을 먼저 판정하고, 확신이 낮은 문장만 페이지 유형별로 묶어 LLM에 보냅니다. 샘플에서 LLM 호출이 7회에서 3회로 줄고 정확도는 25/27에서 26/27로 올랐습니다. 시스템 프롬프트를 절반으로 압축했고, 페이지 제목에서 계산한 유형 힌트를 LLM 입력에 넣습니다. 골드 세트로 분류기를 학습하는 `ip-finder train` 명령과 `--mode`, `--threshold` 옵션이 추가됐습니다. 설치 스크립트가 `bge-m3`도 함께 내려받습니다. numpy 의존성이 추가되어 wheel 번들을 갱신했습니다.

v0.1.1에서는 한글 Windows의 cmd.exe가 UTF-8 배치 파일을 잘못 해석하던 문제를 고쳤습니다(배치 파일 ASCII 전용, 한글 안내는 tools/setup_windows.py).

보고자료(PDF/PPTX)에서 특허 검토 후보 문장을 온디바이스 LLM(Ollama qwen3 4B)으로 추출해 단서 등급(A/B/C/D)을 붙인 Excel 목록을 만드는 도구의 첫 릴리스입니다.

## 윈도우 설치
1. Python 3.12 64비트와 Ollama를 설치합니다.
2. **Source code (zip)** 을 받아 풀고 `install.bat`를 실행합니다.
3. `extract.bat` 위로 보고서 파일이나 폴더를 끌어다 놓습니다.

## 인터넷이 막힌 PC
`ip_finder_wheels_win_amd64_py312.zip`(Python 3.12 64비트용 패키지 묶음)을 받아 풀고, 생긴 `wheels` 폴더를 `install.bat` 옆에 둔 뒤 실행하면 PyPI에 접속하지 않습니다.
모델은 다른 PC에서 `ollama pull qwen3:4b-instruct` 와 `ollama pull bge-m3` 후 `%USERPROFILE%\.ollama\models` 폴더를 복사합니다.

## 포함
- PDF/PPTX 읽기(발표자 노트 제외), 규칙 전처리, hybrid 판정(임베딩 분류기 + 애매한 문장만 LLM), 페이지 유형 힌트, 제목 기반 보정, 재현율 안전장치, 섹션 묶기
- Excel 리포트: 검토 목록 / 보류 / 제외 페이지 / 이미지 페이지 / 실행 정보
- 캐시(해시+라벨+벡터, 원문 미저장), 골드 세트 생성·채점·분류기 학습(`gold-sheet`, `eval`, `train`), 환경 점검(`check`)
- 오프라인 테스트 23건, 가짜 샘플과 결과 예시, 제안서(PROPOSAL.md)와 출력 예시(EXAMPLE.md)

릴리스 만들기(저장소 소유자): `gh release create v0.2.0 dist/ip_finder_wheels_win_amd64_py312.zip --title "IP Finder v0.2.0" --notes-file RELEASE_NOTES.md`
