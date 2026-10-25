# IP Finder v0.1.0 (MVP)

보고자료(PDF/PPTX)에서 특허 검토 후보 문장을 온디바이스 LLM(Ollama qwen3 4B)으로 추출해 단서 등급(A/B/C/D)을 붙인 Excel 목록을 만드는 도구의 첫 릴리스입니다.

## 윈도우 설치
1. Python 3.12 64비트와 Ollama를 설치합니다.
2. **Source code (zip)** 을 받아 풀고 `install.bat`를 실행합니다.
3. `extract.bat` 위로 보고서 파일이나 폴더를 끌어다 놓습니다.

## 인터넷이 막힌 PC
`ip_finder_wheels_win_amd64_py312.zip`(Python 3.12 64비트용 패키지 묶음)을 받아 풀고, 생긴 `wheels` 폴더를 `install.bat` 옆에 둔 뒤 실행하면 PyPI에 접속하지 않습니다.
모델은 다른 PC에서 `ollama pull qwen3:4b-instruct` 후 `%USERPROFILE%\.ollama\models` 폴더를 복사합니다.

## 포함
- PDF/PPTX 읽기(발표자 노트 제외), 규칙 전처리, 페이지당 1회 LLM 라벨링(라벨 배열만), 제목 기반 보정, 재현율 안전장치, 섹션 묶기
- Excel 리포트: 검토 목록 / 보류 / 제외 페이지 / 이미지 페이지 / 실행 정보
- 캐시(해시+라벨만), 골드 세트 생성·채점(`gold-sheet`, `eval`), 환경 점검(`check`)
- 오프라인 테스트 23건, 가짜 샘플과 결과 예시, 제안서(PROPOSAL.md)와 출력 예시(EXAMPLE.md)

릴리스 만들기(저장소 소유자): `gh release create v0.1.0 dist/ip_finder_wheels_win_amd64_py312.zip --title "IP Finder v0.1.0 (MVP)" --notes-file RELEASE_NOTES.md`
