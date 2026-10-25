"""라벨 배열(id 없음) 스키마 + 프롬프트 v1/v2, 4B vs 8B 비교"""
import json, time, urllib.request
exec(open("speed_test.py", encoding="utf-8").read().split("print(\"=== (1)")[0])  # LABEL_SYS(v1), GOLD, numbered, post, sample

LABEL_SYS_V2 = LABEL_SYS.replace(
    "발표자 노트([N1] 등)도 같은 기준으로 라벨을 붙입니다. 모든 문장에 라벨을 출력하세요.",
    "주의: A는 '무엇을 어떻게 바꿨는지(구조·재료·조건·알고리즘·방식)'가 그 문장 안에 직접 적혀 있을 때만 고릅니다. "
    "현상이나 원인을 설명하는 문장은 수단이 아니므로 C, 결과 수치만 있는 문장은 B, 할 예정이라는 문장은 내용이 구체적이어도 D입니다.\n"
    "반례: '습기 침투로 접점 부식이 생겨 접촉 저항 증가' → C (원인 설명). '소음 42dB에서 35dB로 감소' → B (결과 수치). "
    "'차기 라인에 이중 실링 구조 적용 예정' → D (예정). '공정 표준서 개정 및 교육 실시' → X (관리 업무).\n"
    "발표자 노트([N1] 등)도 같은 기준입니다. 문장 순서대로 라벨만 배열로 출력하세요.")

def schema_for(n):
    return {"type": "object", "properties": {"labels": {"type": "array", "items": {"type": "string", "enum": ["A", "B", "C", "D", "X"]},
            "minItems": n, "maxItems": n}}, "required": ["labels"]}

def run(model, system, tag):
    hit = n = 0; tot = 0.0; tin = tout = 0; rows = []
    for p in sample["pages"]:
        if p["no"] not in GOLD: continue
        user, ids = numbered(p)
        body = {"model": model, "stream": False, "format": schema_for(len(ids)), "keep_alive": "10m", "think": False,
                "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 120},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        res, dt = post("/api/chat", body)
        labels = json.loads(res["message"]["content"]).get("labels", [])
        tot += dt; tin += res.get("prompt_eval_count", 0); tout += res.get("eval_count", 0)
        row = []
        for i, ok, got in zip(ids, GOLD[p["no"]], labels + ["?"] * len(ids)):
            good = got in ok; hit += good; n += 1
            row.append(f"[{i}]{got}{'✓' if good else '✗(' + '/'.join(sorted(ok)) + ')'}")
        rows.append(f"  p{p['no']:>2} {dt:4.1f}s  " + "  ".join(row))
    print(f"\n=== {tag}: {model} ===  합계 {tot:.1f}s, in {tin} / out {tout} tok, 정확도 {hit}/{n}")
    print("\n".join(rows))
    return {"model": model, "tag": tag, "sec": round(tot, 1), "in": tin, "out": tout, "acc": f"{hit}/{n}"}

results = []
results.append(run("qwen3:4b-instruct", LABEL_SYS, "4B 라벨배열 v1 프롬프트"))
results.append(run("qwen3:4b-instruct", LABEL_SYS_V2, "4B 라벨배열 v2 프롬프트(반례 추가)"))
results.append(run("qwen3:8b", LABEL_SYS_V2, "8B 라벨배열 v2 프롬프트"))
json.dump(results, open("speed_results.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\n요약:", json.dumps(results, ensure_ascii=False))
