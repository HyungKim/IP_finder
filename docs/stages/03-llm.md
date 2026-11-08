# 3단계 — LLM 2차 판정 부착 (예정)

0단계에서 뺀 LLM 2차 판정(0.6.2 의 cascade: 분류기가 A·B 로 본 후보 전부를 LLM 이 다시 판정)을 스위치 하나로 다시 붙인다.
코드는 `git show v0.6.2:ip_finder/label/labeler.py`, `git show v0.6.2:ip_finder/llm/ollama_client.py` 에 있다.

측정은 2단계와 같은 사다리 틀을 쓴다: 2단계에서 고른 설정을 기준선으로 두고 `llm_second_pass` 한 칸을 켠 결과를 비교한다.
프롬프트 판(compact/full), 묶음 방식(page/type), 모델(qwen3 4B/8B)은 `set = { ... }` 칸으로 같은 사다리에 넣는다.

| 칸 | 검토 목록 | A·B 재현율 | A·B 정밀도 | LLM 호출 | 시간 |
|---|---|---|---|---|---|
| 2단계 최종 설정 | | | | 0 | |
| + LLM 2차 (compact, 4B) | | | | | |
| … | | | | | |
