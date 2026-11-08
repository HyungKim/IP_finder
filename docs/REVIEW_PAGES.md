# 코드 리뷰 페이지

작업 단위마다 두 페이지를 만들어 발행한다(비공개 아티팩트, 계정 소유자만 열람).

| 페이지 | 내용 | 빌드 |
|---|---|---|
| 전체 코드 주석 | 소스 파일 전부를 한 번의 실행 순서대로, 줄마다 번호·코드·설명 | `python tools/walkthrough/build_full.py` |
| 변경 리뷰 | 기준 커밋 대비 바뀐 파일만: 파일마다 '왜 바꿨나 / 어떻게 확인하나' 카드 + 바뀐 영역(앞뒤 3줄)의 줄 설명 | `python tools/walkthrough/build_review.py v0.6.2` |

줄 설명은 `tools/walkthrough/notes/<경로>.tsv` 에 `줄의 글<TAB>설명` 으로 저장한다. 줄 번호가 아니라 글로 묶여 있어 코드가 위아래로 밀려도 설명이 따라간다.
설명이 없는 줄은 빌드가 `tools/walkthrough/todo/` 에 적어 주고 개수를 출력한다(0 이어야 한다).
파일별 머리말은 `tools/walkthrough/review_meta.py` 에 적는다. 빌더는 개발용이며 프로그램 의존성이 아니다(pygments 가 있으면 구문 강조).

| 판 | 전체 코드 주석 | 변경 리뷰 |
|---|---|---|
| 0.6.2 (main) | https://claude.ai/artifact/36EwwFZwJM4szGhGDPgjiK | (구조 워크스루) https://claude.ai/artifact/MQS6u24L9q34ur65QZ4ENk |
| 1.0.0.dev1~dev2 (rebuild 0단계) | https://claude.ai/artifact/DYZAsAgovyUwN6YVVNNra2 | https://claude.ai/artifact/VbT6xdu2si77vEHkegnPfE |
