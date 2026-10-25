"""IP Finder 추출 파이프라인 시연: 규칙 필터 → LLM 제목 필터 → 페이지별 추출 → 주제 병합.
로컬 Ollama(127.0.0.1)만 호출. 사용: python3 run_demo.py sample.json <model> results.json
"""
import json, re, sys, time, urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:11434"
sample_path, MODEL, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
sample = json.loads(Path(sample_path).read_text(encoding="utf-8"))

def chat(system, user, schema, num_predict=900):
    body = {"model": MODEL, "stream": False, "format": schema, "keep_alive": "10m", "think": False,
            "options": {"temperature": 0, "num_ctx": 4096, "num_predict": num_predict},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    req = urllib.request.Request(BASE + "/api/chat", data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    t = time.time()
    with urllib.request.urlopen(req, timeout=900) as r:
        res = json.loads(r.read())
    dt = time.time() - t
    content = res["message"]["content"]
    try:
        parsed = json.loads(content)
    except Exception:
        parsed = {"_raw": content}
    return parsed, dt, res.get("prompt_eval_count"), res.get("eval_count")

FILTER_SCHEMA = {"type": "object", "properties": {"keep": {"type": "boolean"}, "reason": {"type": "string"}},
                 "required": ["keep", "reason"]}
EXTRACT_SCHEMA = {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {
    "sent": {"type": "array", "items": {"type": "string"}},
    "grade": {"type": "string", "enum": ["A", "B", "C", "D"]},
    "topic": {"type": "string"}, "question": {"type": "string"}},
    "required": ["sent", "grade", "topic", "question"]}}}, "required": ["items"]}
MERGE_SCHEMA = {"type": "object", "properties": {"topics": {"type": "array", "items": {"type": "object", "properties": {
    "topic": {"type": "string"}, "grade": {"type": "string", "enum": ["A", "B", "C", "D"]},
    "item_ids": {"type": "array", "items": {"type": "integer"}}, "question": {"type": "string"}},
    "required": ["topic", "grade", "item_ids", "question"]}}}, "required": ["topics"]}

FILTER_SYS = (
    "당신은 사내 기술 보고서의 슬라이드를 선별하는 조수입니다. 슬라이드 제목과 본문 앞부분을 보고, "
    "이 슬라이드에 기술적 내용(기술적 수단, 효과·성능, 문제점·원인, 기술 변경 계획)이 있을 가능성이 조금이라도 있으면 keep=true로 답하세요. "
    "목차, 일정, 비용·예산, 조직·인력, 인사말처럼 명백히 비기술적인 경우에만 keep=false로 답하세요. "
    "특허성(신규성·진보성)은 판단하지 마세요. reason은 한국어 한 문장."
)
EXTRACT_SYS = (
    "당신은 사내 기술 보고서에서 특허팀과 논의할 만한 기술 주제를 빠짐없이 찾아내는 조수입니다.\n"
    "규칙:\n"
    "- 신규성·진보성 등 특허성은 판단하지 마세요. 기술적 내용이면 일단 포함하고, 확신이 없으면 포함합니다.\n"
    "- 각 항목에 단서 등급을 붙입니다. A=구체적 수단(구조, 재료, 공정 조건, 알고리즘, 파라미터, 절차)이 기재됨. "
    "B=효과·성능 개선·수치 비교가 기재됨. C=문제점·불량 원인·한계 등 과제가 기재됨. D=적용 예정, 검토 중, 신규 도입 등 변경 의도만 기재됨.\n"
    "- 제외: 일정, 비용·예산, 인력·조직, 영업·고객 대응, 단순 진행 현황.\n"
    "- 문장은 번호([1], [N1] 등)로만 가리킵니다. 원문을 다시 쓰지 마세요. 서로 밀접한 문장은 한 항목으로 묶습니다.\n"
    "- topic은 한국어 한 줄 주제명(30자 이내), question은 특허팀이 확인할 질문 한 문장.\n"
    "- 해당 항목이 없으면 items를 빈 배열로 출력합니다."
)
MERGE_SYS = (
    "아래는 한 보고서에서 페이지별로 추출한 항목 목록입니다. 같은 기술 주제를 다루는 항목을 하나로 묶어 주제 목록을 만드세요. "
    "각 주제에 포함되는 item_ids, 대표 등급(가장 높은 등급 하나: A>B>C>D), 한국어 주제명(30자 이내), 특허팀이 확인할 질문 한 문장을 출력하세요. "
    "서로 다른 기술 주제는 합치지 마세요. 모든 항목은 정확히 하나의 주제에 속해야 합니다."
)
EXCL = re.compile(r"(목차|일정|비용|예산|조직|인력|감사|Q&A|참고문헌|부록)")

def rule_filter(p):
    if p["no"] == 1:
        return "표지"
    m = EXCL.search(p["title"])
    if m:
        return f"제목 규칙: '{m.group(1)}'"
    return None

def numbered(p):
    out = [f"[슬라이드 {p['no']}] 제목: {p['title']}"]
    for i, l in enumerate(p["lines"], 1):
        out.append(f"[{i}] {l}")
    for i, n in enumerate(p["notes"], 1):
        out.append(f"[N{i}] (발표자 노트) {n}")
    return "\n".join(out)

def resolve(p, ref):
    ref = str(ref).strip("[]")
    if ref.upper().startswith("N"):
        try: return "(노트) " + p["notes"][int(ref[1:]) - 1]
        except Exception: return f"(미해결 {ref})"
    try: return p["lines"][int(ref) - 1]
    except Exception: return f"(미해결 {ref})"

log = {"model": MODEL, "pages": [], "items": [], "merge": None, "timing": {}}
items = []
t_all = time.time()
for p in sample["pages"]:
    rec = {"no": p["no"], "title": p["title"]}
    if not p["lines"] and not p["notes"]:
        rec["status"] = "이미지 페이지"; log["pages"].append(rec); print(f"p{p['no']:>2} {p['title']!r:40} → 이미지 페이지"); continue
    r = rule_filter(p)
    if r:
        rec["status"] = "제외(규칙)"; rec["reason"] = r; log["pages"].append(rec); print(f"p{p['no']:>2} {p['title']!r:40} → 제외(규칙) {r}"); continue
    user = f"제목: {p['title']}\n본문 앞부분:\n" + "\n".join(p["lines"][:3])
    f, dt, pe, ev = chat(FILTER_SYS, user, FILTER_SCHEMA, num_predict=120)
    rec["filter"] = {**f, "sec": round(dt, 1)}
    if not f.get("keep", True):
        rec["status"] = "제외(1차 LLM)"; log["pages"].append(rec); print(f"p{p['no']:>2} {p['title']!r:40} → 제외(1차 LLM) {f.get('reason')} [{dt:.1f}s]"); continue
    print(f"p{p['no']:>2} {p['title']!r:40} → 통과(1차 LLM) {f.get('reason')} [{dt:.1f}s]")
    ex, dt2, pe2, ev2 = chat(EXTRACT_SYS, numbered(p), EXTRACT_SCHEMA)
    rec["status"] = "추출"; rec["extract_sec"] = round(dt2, 1); rec["tokens"] = {"prompt": pe2, "out": ev2}
    rec["items"] = ex.get("items", ex)
    for it in ex.get("items", []):
        texts = [resolve(p, s) for s in it.get("sent", [])]
        items.append({"id": len(items) + 1, "page": p["no"], "grade": it.get("grade"), "topic": it.get("topic"),
                      "question": it.get("question"), "sent": it.get("sent"), "texts": texts})
        print(f"      [{it.get('grade')}] {it.get('topic')}  ← {it.get('sent')}")
    print(f"      (추출 {dt2:.1f}s, 입력 {pe2} tok, 출력 {ev2} tok)")
    log["pages"].append(rec)

log["items"] = items
if items:
    lines = [f"id={it['id']} | p.{it['page']} | 등급 {it['grade']} | {it['topic']} | 근거: " + " / ".join(it["texts"]) for it in items]
    mg, dt3, pe3, ev3 = chat(MERGE_SYS, "\n".join(lines), MERGE_SCHEMA, num_predict=1500)
    log["merge"] = {"result": mg, "sec": round(dt3, 1), "tokens": {"prompt": pe3, "out": ev3}}
    print(f"\n=== 주제 병합 ({dt3:.1f}s) ===")
    for t in mg.get("topics", []):
        print(f"[{t.get('grade')}] {t.get('topic')}  ← items {t.get('item_ids')}\n      Q: {t.get('question')}")
log["timing"]["total_sec"] = round(time.time() - t_all, 1)
Path(out_path).write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"\n총 소요 {log['timing']['total_sec']}s, 항목 {len(items)}개 → {out_path}")
