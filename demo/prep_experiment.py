"""전처리 변형 실험: 페이지 유형 힌트 / 여러 페이지 묶음 호출 / 시스템 프롬프트 압축. 샘플 PPTX, qwen3:4b-instruct."""
import re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ip_finder.config import Config
from ip_finder.readers import load_document
from ip_finder.pipeline import prepare
from ip_finder.label.labeler import SYSTEM_PROMPT
from ip_finder.llm import OllamaClient
from ip_finder.models import LabeledLine
from ip_finder.post import apply_title_fix

GOLD = {3: [{"C"}, {"B", "C", "X"}, {"X"}, {"C"}], 4: [{"C"}, {"C"}, {"C", "B"}, {"C", "X"}],
        5: [{"A"}, {"A"}, {"A"}], 6: [{"A"}, {"A"}, {"A"}, {"B", "X"}],
        8: [{"B"}, {"B"}, {"B", "X"}, {"D", "X"}, {"B"}, {"B"}], 9: [{"C"}, {"D"}, {"B"}], 11: [{"D"}, {"D"}, {"X"}]}

HINTS = [
    (re.compile(r"(원인|문제|배경|현황|이슈|과제|불량|한계)"), "과제·원인 설명 페이지. 원인이나 현상 설명은 C"),
    (re.compile(r"(결과|검증|효과|성능|평가|비교|시험)"), "결과·효과 페이지. 수치 결과는 B"),
    (re.compile(r"(개선|방안|대책|설계|구조|알고리즘|적용)"), "수단 설명 페이지. 구체적 수단은 A"),
    (re.compile(r"(계획|향후|로드맵|검토 사항|추진)"), "계획 페이지. 예정·검토는 D"),
]
def hint(title):
    for rx, h in HINTS:
        if rx.search(title): return h
    return None

COMPACT = ("각 문장에 라벨 하나. 특허성(신규성·진보성)은 판단하지 않음. 판정 순서: X → A → B → C → D.\n"
           "X=기술 내용 없음(일정·비용·인력·고객대응·클레임·규정 개정·진행 현황·인사말). "
           "A=구조·재료·치수·조건·알고리즘·파라미터·저장 방식 등 수단이 문장에 직접 적힘. "
           "B=효과·수치·전후 비교·경쟁사 대비만 적힘. C=문제·원인·현상·메커니즘·한계. D=적용 예정·검토 중·계획.\n"
           "예: '냉각 유로를 이중 구조로 변경'→A, '소비 전력 15% 감소'→B, '습기 침투로 접점 부식 발생'→C, "
           "'차기 라인에 이중 실링 적용 예정'→D, '3분기 양산, 투자 2억'→X.\n문장 순서대로 라벨 배열만 출력.")

def page_block(p, start, with_hint):
    lines = p.active_lines()
    head = f"[슬라이드 {p.no}] 제목: {p.title}"
    if with_hint and (h := hint(p.title)): head += f"\n(페이지 유형: {h})"
    body = [f"[{start + i}] {'  ' * ln.level}{ln.text}" for i, ln in enumerate(lines)]
    return "\n".join([head, *body]), lines

def run(name, system, with_hint=False, batch_chars=0):
    doc = load_document("demo/sample_report.pptx"); prepare(doc, Config(use_cache=False))
    pages = [p for p in doc.pages if p.excluded_reason is None and p.active_lines()]
    client = OllamaClient("http://127.0.0.1:11434", "qwen3:4b-instruct", num_ctx=2048)
    # 묶음 만들기
    groups, cur, size = [], [], 0
    for p in pages:
        chars = sum(len(l.text) for l in p.active_lines()) + len(p.title)
        if cur and batch_chars and size + chars > batch_chars:
            groups.append(cur); cur, size = [], 0
        cur.append(p); size += chars
        if not batch_chars: groups.append(cur); cur, size = [], 0
    if cur: groups.append(cur)
    t0 = time.time(); labeled = []
    for g in groups:
        blocks, all_lines, start = [], [], 1
        for p in g:
            b, lines = page_block(p, start, with_hint); blocks.append(b); all_lines += [(p, l) for l in lines]; start += len(lines)
        labels = client.chat_labels(system, "\n\n".join(blocks), len(all_lines))
        for (p, l), lab in zip(all_lines, labels):
            labeled.append(LabeledLine(page_no=p.no, page_title=p.title, section="", line_idx=l.idx, text=l.text, label=lab, raw_label=lab))
    elapsed = time.time() - t0
    raw_hit = sum(ll.raw_label in GOLD[ll.page_no][ll.line_idx - 1] for ll in labeled)
    apply_title_fix(labeled)
    fix_hit = sum(ll.label in GOLD[ll.page_no][ll.line_idx - 1] for ll in labeled)
    wrong = [f"p{ll.page_no}[{ll.line_idx}]{ll.raw_label}→{'/'.join(sorted(GOLD[ll.page_no][ll.line_idx-1]))}" for ll in labeled if ll.raw_label not in GOLD[ll.page_no][ll.line_idx - 1]]
    print(f"{name:<34} 호출 {client.calls}  {elapsed:5.1f}s  입력 {client.prompt_tokens:>5} tok  출력 {client.output_tokens:>3} tok  "
          f"정확도 raw {raw_hit}/{len(labeled)}  보정후 {fix_hit}/{len(labeled)}")
    print(f"{'':34} 오답(raw): {', '.join(wrong) if wrong else '없음'}")

run("A 현재 (페이지별, 기본 프롬프트)", SYSTEM_PROMPT)
run("B + 페이지 유형 힌트", SYSTEM_PROMPT, with_hint=True)
run("C 묶음 호출(~900자) + 힌트", SYSTEM_PROMPT, with_hint=True, batch_chars=900)
run("D 압축 프롬프트 + 힌트", COMPACT, with_hint=True)
run("E 압축 프롬프트 + 힌트 + 묶음", COMPACT, with_hint=True, batch_chars=900)
print(f"\n기본 프롬프트 {len(SYSTEM_PROMPT)}자, 압축 프롬프트 {len(COMPACT)}자")
