"""속도 실험: (1) 라벨만 출력하는 경량 추출 vs 기존 추출  (2) bge-m3 임베딩 사전 필터 속도/분리력"""
import json, time, math, urllib.request
BASE = "http://127.0.0.1:11434"
sample = json.load(open("sample.json", encoding="utf-8"))
prev = json.load(open("results_4b.json", encoding="utf-8"))

def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})
    t = time.time()
    with urllib.request.urlopen(req, timeout=600) as r:
        res = json.loads(r.read())
    return res, time.time() - t

# ---------- (1) 라벨만 출력 ----------
LABEL_SYS = (
    "보고서 슬라이드의 각 문장에 라벨 하나를 붙이세요. 특허성(신규성·진보성)은 판단하지 않습니다.\n"
    "판정 순서: 먼저 X인지 확인하고, 아니면 A→B→C→D 순으로 처음 해당하는 것을 고릅니다.\n"
    "X = 기술 내용이 없는 문장: 일정, 비용·금액, 인력·담당, 고객 대응·클레임·영업, 표준·규정·문서 개정, 단순 진행 현황, 인사말.\n"
    "A = 구체적 수단이 적힘: 구조, 재료, 치수, 공정 조건, 알고리즘, 수식, 파라미터, 저장·제어 방식, 절차.\n"
    "B = 효과·성능이 적힘: 개선, 저감, 향상, 전후 수치 비교, 경쟁사·기존 대비. 수단 자체는 없음.\n"
    "C = 문제·원인·한계가 적힘: 현상, 불량 원인, 메커니즘 설명, 기존 방식의 한계.\n"
    "D = 변경 의도만 적힘: 적용 예정, 검토 중, 도입 계획, 신규·자체 개발 계획.\n"
    "예: '냉각 유로를 이중 구조로 변경' → A. '소비 전력 15% 감소' → B. '진동으로 체결부 풀림 발생' → C. "
    "'차기 라인에 신규 검사 방식 도입 검토' → D. '3분기 양산, 설비 투자 2억' → X.\n"
    "발표자 노트([N1] 등)도 같은 기준으로 라벨을 붙입니다. 모든 문장에 라벨을 출력하세요."
)
LABEL_SCHEMA = {"type": "object", "properties": {"labels": {"type": "array", "items": {"type": "object", "properties": {
    "id": {"type": "string"}, "label": {"type": "string", "enum": ["A", "B", "C", "D", "X"]}}, "required": ["id", "label"]}}},
    "required": ["labels"]}
GOLD = {3: [{"C"}, {"X", "C", "B"}, {"X"}, {"C"}], 4: [{"C"}, {"C"}, {"C", "B"}, {"C", "X"}],
        5: [{"A"}, {"A"}, {"A"}, {"A"}], 6: [{"A"}, {"A"}, {"A"}, {"B", "X"}],
        8: [{"B"}, {"B"}, {"B", "X"}, {"X", "D"}], 9: [{"C"}, {"D"}, {"B"}], 11: [{"D"}, {"D"}, {"X"}]}

def numbered(p):
    out = [f"[슬라이드 {p['no']}] 제목: {p['title']}"]
    ids = []
    for i, l in enumerate(p["lines"], 1):
        out.append(f"[{i}] {l}"); ids.append(str(i))
    for i, n in enumerate(p["notes"], 1):
        out.append(f"[N{i}] (발표자 노트) {n}"); ids.append(f"N{i}")
    return "\n".join(out), ids

print("=== (1) 라벨만 출력 (qwen3:4b-instruct) vs 기존 추출 ===")
tot_new = tot_old = 0.0; tok_new = tok_old = [0, 0]; hit = n = 0
tok_new = [0, 0]; tok_old = [0, 0]
for p in sample["pages"]:
    if p["no"] not in GOLD: continue
    user, ids = numbered(p)
    res, dt = post("/api/chat", {"model": "qwen3:4b-instruct", "stream": False, "format": LABEL_SCHEMA, "keep_alive": "10m",
                                 "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 300},
                                 "messages": [{"role": "system", "content": LABEL_SYS}, {"role": "user", "content": user}]})
    labels = {d["id"].strip("[]"): d["label"] for d in json.loads(res["message"]["content"]).get("labels", [])}
    old = next(r for r in prev["pages"] if r["no"] == p["no"])
    tot_new += dt; tot_old += old["extract_sec"]
    tok_new[0] += res.get("prompt_eval_count", 0); tok_new[1] += res.get("eval_count", 0)
    tok_old[0] += old["tokens"]["prompt"]; tok_old[1] += old["tokens"]["out"]
    row = []
    for i, ok in zip(ids, GOLD[p["no"]]):
        got = labels.get(i, "?"); good = got in ok; hit += good; n += 1
        row.append(f"[{i}]{got}{'✓' if good else '✗(' + '/'.join(sorted(ok)) + ')'}")
    print(f"p{p['no']:>2} 라벨 {dt:5.1f}s (in {res.get('prompt_eval_count')} / out {res.get('eval_count')} tok) | 기존 추출 {old['extract_sec']:5.1f}s (in {old['tokens']['prompt']} / out {old['tokens']['out']} tok)")
    print("      " + "  ".join(row))
print(f"\n합계: 라벨만 {tot_new:.1f}s (in {tok_new[0]} / out {tok_new[1]} tok)  vs  기존 {tot_old:.1f}s (in {tok_old[0]} / out {tok_old[1]} tok)")
print(f"라벨 정확도: {hit}/{n}  (기존 추출의 등급 채점은 9/26 + 애매 3)")

# ---------- (2) 임베딩 사전 필터 ----------
print("\n=== (2) bge-m3 임베딩 사전 필터 ===")
EXCL = ["양산 적용 일정과 단계별 추진 계획", "설비 투자 비용 및 재료비 단가 상승", "담당 부서 및 인력 배정",
        "고객 클레임 접수와 대응 회신 요청", "매출 및 수주 목표 달성 현황", "사내 표준 문서 및 규정 개정 추진", "진행 현황 공유 및 회의 일정 안내"]
TECH = ["부품 구조와 재료를 변경하여 성능 문제를 개선", "제어 알고리즘과 보정 방식을 적용", "시험 결과 성능 수치가 개선됨",
        "불량의 원인과 발생 메커니즘 분석", "기존 방식의 한계와 기술적 문제점", "차기 제품에 신규 기술 적용 검토"]
lines = []
for p in sample["pages"]:
    for i, l in enumerate(p["lines"], 1): lines.append((p["no"], str(i), l))
    for i, nte in enumerate(p["notes"], 1): lines.append((p["no"], f"N{i}", nte))
texts = [l[2] for l in lines]
res, dt_e = post("/api/embed", {"model": "bge-m3", "input": EXCL + TECH + texts, "keep_alive": "10m"})
E = res["embeddings"]
def cos(a, b):
    return sum(x*y for x, y in zip(a, b)) / (math.sqrt(sum(x*x for x in a)) * math.sqrt(sum(y*y for y in b)))
ex, te, li = E[:len(EXCL)], E[len(EXCL):len(EXCL)+len(TECH)], E[len(EXCL)+len(TECH):]
print(f"문장 {len(texts)}개 + 기준문 {len(EXCL)+len(TECH)}개 임베딩: {dt_e:.2f}s (문장당 {dt_e/(len(texts)+len(EXCL)+len(TECH))*1000:.0f}ms)")
scored = []
for (no, i, txt), v in zip(lines, li):
    s_t = max(cos(v, t) for t in te); s_x = max(cos(v, x) for x in ex)
    gold = "/".join(sorted(GOLD[no][int(i)-1])) if (no in GOLD and not i.startswith("N")) else ("A" if i.startswith("N") else "-")
    scored.append((s_t - s_x, no, i, txt, gold))
scored.sort()
print("점수(기술−제외) 낮은 순. 음수이면 '제외 쪽에 더 가깝다'는 뜻. gold X 문장이 아래쪽에 모이면 사전 필터로 쓸 수 있음.")
for s, no, i, txt, gold in scored:
    print(f"{s:+.3f}  p{no:>2}[{i:>2}] gold={gold:<6} {txt[:48]}")
