"""분류기(여기서는 임베딩 제로샷) 선별 → LLM 후판정 구조의 호출 수·토큰·정확도 시뮬레이션."""
import json, math, re, sys, time, urllib.request
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ip_finder.config import Config
from ip_finder.readers import load_document
from ip_finder.pipeline import prepare
from ip_finder.llm import OllamaClient

GOLD = {3: [{"C"}, {"B","C","X"}, {"X"}, {"C"}], 4: [{"C"}, {"C"}, {"C","B"}, {"C","X"}], 5: [{"A"}]*3,
        6: [{"A"}, {"A"}, {"A"}, {"B","X"}], 8: [{"B"}, {"B"}, {"B","X"}, {"D","X"}, {"B"}, {"B"}], 9: [{"C"}, {"D"}, {"B"}], 11: [{"D"}, {"D"}, {"X"}]}
PROTO = {
 "A": ["냉각 유로를 이중 구조로 변경하여 열을 분산", "제어 알고리즘에 PID 보정 항을 추가", "하우징 재질을 알루미늄에서 마그네슘 합금으로 교체", "용접 전류를 120A에서 100A로 낮추고 속도를 조정", "센서 신호를 16비트 ADC로 샘플링하여 메모리에 저장"],
 "B": ["소비 전력 15% 감소", "조립 시간이 40초에서 25초로 단축", "경쟁사 대비 내구성 2배 확보", "불량률 3.2%에서 0.8%로 개선", "처리 속도가 기존 대비 1.5배 향상"],
 "C": ["습기 침투로 접점 부식이 발생해 접촉 저항 증가", "고속 회전 시 진동으로 체결부가 풀리는 현상", "기존 방식은 온도 변화에 대응하지 못함", "원인은 재료 간 열팽창 차이로 추정", "장시간 사용 시 출력이 서서히 변하는 문제"],
 "D": ["차기 모델에 신규 방식 적용 예정", "AI 기반 검사 도입 검토 중", "내년 상반기에 자체 개발 모듈로 대체 계획", "구조 변경 타당성 검토 예정", "파일럿 라인에 시험 적용 추진"],
 "X": ["3분기 양산 전환, 4분기 확대", "설비 투자 비용 2억 원", "담당: 품질팀, 공정팀", "고객 클레임 3건 접수 및 회신", "사내 표준 문서 개정 및 교육 실시", "매출 목표 달성 현황 공유"],
}
HINTS = [(re.compile(r"(원인|문제|배경|현황|이슈|과제|불량|한계)"), "과제·원인 설명 페이지. 원인이나 현상 설명은 C"),
         (re.compile(r"(결과|검증|효과|성능|평가|비교|시험)"), "결과·효과 페이지. 수치 결과는 B"),
         (re.compile(r"(개선|방안|대책|설계|구조|알고리즘|적용)"), "수단 설명 페이지. 구체적 수단은 A"),
         (re.compile(r"(계획|향후|로드맵|검토 사항|추진)"), "계획 페이지. 예정·검토는 D")]
def hint(title):
    for rx, h in HINTS:
        if rx.search(title): return h
    return "일반 페이지"
COMPACT = ("각 문장에 라벨 하나. 특허성(신규성·진보성)은 판단하지 않음. 판정 순서: X → A → B → C → D.\n"
           "X=기술 내용 없음(일정·비용·인력·고객대응·클레임·규정 개정·진행 현황·인사말). "
           "A=구조·재료·치수·조건·알고리즘·파라미터·저장 방식 등 수단이 문장에 직접 적힘. "
           "B=효과·수치·전후 비교·경쟁사 대비만 적힘. C=문제·원인·현상·메커니즘·한계. D=적용 예정·검토 중·계획.\n"
           "예: '냉각 유로를 이중 구조로 변경'→A, '소비 전력 15% 감소'→B, '습기 침투로 접점 부식 발생'→C, "
           "'차기 라인에 이중 실링 적용 예정'→D, '3분기 양산, 투자 2억'→X.\n문장 순서대로 라벨 배열만 출력.")

doc = load_document("demo/sample_report.pptx"); prepare(doc, Config(use_cache=False))
items = [dict(no=p.no, idx=ln.idx, title=p.title, text=ln.text, level=ln.level) for p in doc.pages if p.excluded_reason is None for ln in p.active_lines()]
protos = [(g, s) for g, ss in PROTO.items() for s in ss]
def embed(inputs):
    req = urllib.request.Request("http://127.0.0.1:11434/api/embed", data=json.dumps({"model": "bge-m3", "input": inputs, "keep_alive": "10m"}).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r: return json.loads(r.read())["embeddings"]
def cos(a, b): return sum(x*y for x, y in zip(a, b)) / math.sqrt(sum(x*x for x in a) * sum(y*y for y in b))
E = embed([s for _, s in protos] + [it["text"] for it in items]); PE, TE = E[:len(protos)], E[len(protos):]
for it, v in zip(items, TE):
    best = {}
    for (g, _), pv in zip(protos, PE): best[g] = max(best.get(g, -1), cos(v, pv))
    ranked = sorted(best.items(), key=lambda kv: -kv[1])
    it["zs"], it["margin"] = ranked[0][0], ranked[0][1] - ranked[1][1]
    it["ok_zs"] = it["zs"] in GOLD[it["no"]][it["idx"]-1]

print("제로샷 라벨과 여유(1위-2위 유사도). 여유가 작을수록 애매:")
for it in sorted(items, key=lambda x: x["margin"]):
    print(f"  여유 {it['margin']:.3f} {it['zs']}{'✓' if it['ok_zs'] else '✗'} p{it['no']}[{it['idx']}] {it['text'][:40]}")

def llm_calls(targets, grouping):
    """targets: LLM에 보낼 항목들. grouping='page' 또는 'type'. 라벨을 돌려주고 (호출수, 입력토큰, 시간) 집계."""
    client = OllamaClient("http://127.0.0.1:11434", "qwen3:4b-instruct", num_ctx=2048)
    groups = {}
    for it in targets:
        key = it["no"] if grouping == "page" else hint(it["title"])
        groups.setdefault(key, []).append(it)
    out = {}
    t0 = time.time()
    for key, grp in groups.items():
        if grouping == "page":
            head = f"[슬라이드 {grp[0]['no']}] 제목: {grp[0]['title']}\n(페이지 유형: {hint(grp[0]['title'])})"
            body = [f"[{i}] {'  '*it['level']}{it['text']}" for i, it in enumerate(grp, 1)]
        else:
            head = f"(페이지 유형: {key}) 아래 문장들은 서로 다른 슬라이드에서 왔으며 각 문장 앞 괄호가 슬라이드 제목이다."
            body = [f"[{i}] ({it['title'][:20]}) {it['text']}" for i, it in enumerate(grp, 1)]
        labels = client.chat_labels(COMPACT, "\n".join([head, *body]), len(grp))
        for it, lab in zip(grp, labels): out[(it["no"], it["idx"])] = lab
    return out, client.calls, client.prompt_tokens, time.time() - t0

def report(name, final, calls, tokens, secs):
    hit = sum(final[(it["no"], it["idx"])] in GOLD[it["no"]][it["idx"]-1] for it in items)
    wrong = [f"p{it['no']}[{it['idx']}]{final[(it['no'], it['idx'])]}" for it in items if final[(it["no"], it["idx"])] not in GOLD[it["no"]][it["idx"]-1]]
    print(f"{name:<44} 호출 {calls:>2}  입력 {tokens:>5} tok  {secs:5.1f}s  정확도 {hit}/{len(items)}  오답 {', '.join(wrong) or '없음'}")

print("\n=== 구조 비교 ===")
lab, c, t, s = llm_calls(items, "page"); report("① 전부 LLM, 페이지별 (현재 설계 + 힌트)", lab, c, t, s)
lab, c, t, s = llm_calls(items, "type"); report("② 전부 LLM, 유형별 묶음 호출", lab, c, t, s)
cand = [it for it in items if it["zs"] != "X"]
lab, c, t, s = llm_calls(cand, "page"); final = {(it["no"], it["idx"]): lab.get((it["no"], it["idx"]), "X") for it in items}
report("③ 분류기로 X 제거 후 LLM, 페이지별", final, c, t, s)
for thr in (0.03, 0.05, 0.08):
    amb = [it for it in items if it["margin"] < thr]
    lab, c, t, s = llm_calls(amb, "type")
    final = {(it["no"], it["idx"]): lab.get((it["no"], it["idx"]), it["zs"]) for it in items}
    report(f"④ 애매한 것만 LLM(여유<{thr}, {len(amb)}문장), 유형별 묶음", final, c, t, s)
final = {(it["no"], it["idx"]): it["zs"] for it in items}; report("⑤ 분류기만 (LLM 없음)", final, 0, 0, 0.0)
