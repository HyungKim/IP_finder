"""레이아웃 시험용 가짜 PDF 보고자료 생성기. 실제 사내 자료는 포함하지 않는다.

PDF 리더(레이아웃 분석)를 여러 배치에서 검증하기 위한 합성 보고서 5건을 만든다. 모든 회사·제품·수치는 지어낸 것이다.
  01 단일 단 불릿 보고서(PPT 출력 모사): 머리말·꼬리말 반복, 긴 문장 줄바꿈, 하위 불릿, 번호 목록, 테두리 표
  02 문서형 2단·3단 기술 검토서: 좌우 단 읽기 순서, 영문 하이픈 줄바꿈, 단 아래 전체 폭 표, 셀 안 줄바꿈
  03 도식 중심 보고서: 블록도(박스·화살표), 막대 차트 자리, 사진 전용 페이지, 순서도, 2×2 매트릭스
  04 표 중심 보고서: 큰 표, 좌 표·우 설명, 선 없는 공백 정렬 표, 일정표, 담당자 표
  05 영문 혼용·규격 검토서: 영문 소제목, 영어만 있는 줄, 수식, 짧은 라벨, 회전 페이지, 옆으로 누운 글
사용: python -m ip_finder.layout_samples [출력폴더]   (기본 demo/layout)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pymupdf

from .samples import _font

LANDSCAPE = (842, 595)
PORTRAIT = (595, 842)
GRAY = (0.35, 0.35, 0.35)
LIGHT = (0.85, 0.85, 0.85)
BLUE = (0.2, 0.35, 0.65)

# 테스트가 참조하는 문장들
WRAPPED_BULLET = ("주축 회전수 24,000 rpm 이상 구간에서 베어링 예압 손실로 1차 공진 주파수가 310 Hz 부근으로 내려오면서 "
                  "가공면 표면 거칠기 Ra 가 규격 0.4 ㎛ 를 초과하는 불량이 3월 이후 월평균 42건 발생")
SUB_BULLET = "불량 로트의 80%가 야간 연속 가공 6시간 이후에 집중되어 열변형과의 상관성이 높음"
NUMBERED_ITEM = "열팽창에 따른 외륜 끼워맞춤 공차 변화로 예압이 설계값 대비 35% 감소하는 것을 FEM 해석과 실측으로 확인"
HYPHEN_SENTENCE = "The controller applies a feed-forward term computed from the predicted heat load of each module."
LEFT_COLUMN_FIRST = "현행 제어는 팩 입구 냉각수 온도만을 기준으로 펌프 듀티를 3단계로 바꾸는 방식이라 모듈 간 온도 편차에는 대응하지 못한다."
RIGHT_COLUMN_FIRST = "제안 방식은 모듈별 온도 센서 12점을 1초 주기로 읽어 최댓값과 최솟값의 차이를 편차로 정의하고 편차에 비례해 분배 밸브 개도를 바꾼다."
COLUMN_HEADS = ("개선안 A: 분배 밸브 비례 제어", "개선안 B: 펌프 듀티 연속 가변", "개선안 C: 냉각수 유로 이중화")
BLOCK_LABELS = ("Radar 전처리", "Confidence 추정기", "가중치 제어기", "융합 출력", "진단 모듈")
TEXT_TABLE = [["공정", "불량률(개선 전)", "불량률(개선 후)", "조치"],
              ["세정", "2.4 %", "0.9 %", "세정액 농도 자동 보정"],
              ["도포", "3.1 %", "0.7 %", "노즐 압력 폐루프 제어"],
              ["경화", "1.2 %", "1.1 %", "변경 없음"],
              ["검사", "0.8 %", "0.3 %", "비전 조명 각도 변경"]]
ROTATED_LINE = "회전된 페이지에서도 바로 선 글은 읽는다: 냉각 유로 이중화 시 모듈 온도 편차 2.1℃ → 0.8℃"
SIDEWAYS_CAPTION = "그림 4. 옆으로 누운 도면 (세로 글자는 읽지 않음)"
ENGLISH_ONLY = "IEC 61508-2:2010, SIL 2 / ISO 13849-1 PL d"
FORMULA = "τ = J·α + c·ω + K·θ"


class Sheet:
    """PyMuPDF 페이지 위에 글·표·도형을 그리는 작은 도구."""

    def __init__(self, doc: pymupdf.Document, font: pymupdf.Font, size: tuple[int, int] = LANDSCAPE) -> None:
        self.w, self.h = size
        self.page = doc.new_page(width=self.w, height=self.h)
        self.font = font
        self.tw = pymupdf.TextWriter(self.page.rect)

    # ---- 글 ----
    def text(self, x: float, y: float, s: str, size: float = 11, color=None) -> None:
        self.tw.append((x, y), s, font=self.font, fontsize=size)

    def width(self, s: str, size: float) -> float:
        return self.font.text_length(s, fontsize=size)

    def wrap(self, x: float, y: float, width: float, s: str, size: float = 11, leading: float | None = None,
             cont_indent: float = 0) -> float:
        """공백 단위로 줄바꿈해 쓴다. 다음 줄의 기준선 y 를 돌려준다."""
        leading = leading or size * 1.55
        line, first = "", True
        for word in s.split(" "):
            cand = f"{line} {word}".strip()
            avail = width - (0 if first else cont_indent)
            if line and self.width(cand, size) > avail:
                self.text(x + (0 if first else cont_indent), y, line, size)
                y += leading
                first, line = False, word
            else:
                line = cand
        if line:
            self.text(x + (0 if first else cont_indent), y, line, size)
            y += leading
        return y

    def para(self, x: float, y: float, width: float, s: str, size: float = 11, gap: float = 6) -> float:
        return self.wrap(x, y, width, s, size) + gap

    def bullets(self, x: float, y: float, width: float, items, size: float = 11, gap: float = 4) -> float:
        """items: str 또는 (str, level). level 0 '•', 1 '–', 2 '·'."""
        markers = ("•", "–", "·")
        for item in items:
            text, level = (item, 0) if isinstance(item, str) else item
            ind = 18 * level
            marker = markers[min(level, 2)] + " "
            y = self.wrap(x + ind, y, width - ind, marker + text, size - min(level, 1), cont_indent=self.width(marker, size)) + gap
        return y

    def numbered(self, x: float, y: float, width: float, items: list[str], size: float = 11, gap: float = 5) -> float:
        for n, text in enumerate(items, 1):
            marker = f"{n}. "
            y = self.wrap(x, y, width, marker + text, size, cont_indent=self.width(marker, size)) + gap
        return y

    def heading(self, x: float, y: float, s: str, size: float = 14) -> float:
        self.text(x, y, s, size)
        return y + size * 1.7

    # ---- 표 ----
    def table(self, x: float, y: float, col_widths: list[float], rows: list[list[str]], size: float = 10,
              borders: bool = True, pad: float = 5, header: bool = True) -> float:
        leading = size * 1.4
        for r, row in enumerate(rows):
            # 셀마다 줄바꿈 수를 먼저 세어 행 높이를 정한다
            wrapped: list[list[str]] = []
            for cw, cell in zip(col_widths, row):
                lines, line = [], ""
                for word in cell.split(" "):
                    cand = f"{line} {word}".strip()
                    if line and self.width(cand, size) > cw - 2 * pad:
                        lines.append(line)
                        line = word
                    else:
                        line = cand
                lines.append(line)
                wrapped.append(lines)
            row_h = max(len(ls) for ls in wrapped) * leading + 2 * pad
            cx = x
            for cw, lines in zip(col_widths, wrapped):
                if borders:
                    rect = pymupdf.Rect(cx, y, cx + cw, y + row_h)
                    self.page.draw_rect(rect, color=GRAY, width=0.8, fill=LIGHT if (header and r == 0) else None)
                ty = y + pad + size
                for ln in lines:
                    self.text(cx + pad, ty, ln, size)
                    ty += leading
                cx += cw
            y += row_h
        return y + 8

    # ---- 도형 ----
    def box(self, x: float, y: float, w: float, h: float, label: str, size: float = 10, fill=None) -> None:
        self.page.draw_rect(pymupdf.Rect(x, y, x + w, y + h), color=GRAY, width=1.0, fill=fill)
        lines = label.split("\n")
        ty = y + h / 2 - (len(lines) - 1) * size * 0.7 + size * 0.35
        for ln in lines:
            self.text(x + (w - self.width(ln, size)) / 2, ty, ln, size)
            ty += size * 1.4

    def arrow(self, x1: float, y1: float, x2: float, y2: float) -> None:
        self.page.draw_line((x1, y1), (x2, y2), color=GRAY, width=1.0)
        if x2 >= x1 and abs(y2 - y1) < 1:
            head = [(x2, y2), (x2 - 7, y2 - 4), (x2 - 7, y2 + 4)]
        elif y2 > y1:
            head = [(x2, y2), (x2 - 4, y2 - 7), (x2 + 4, y2 - 7)]
        else:
            head = [(x2, y2), (x2 + 7, y2 - 4), (x2 + 7, y2 + 4)]
        self.page.draw_polyline(head, color=GRAY, fill=GRAY, closePath=True)

    def image(self, x: float, y: float, w: float, h: float) -> None:
        """사진 대신 회색 바둑판 이미지를 넣는다."""
        pix = pymupdf.Pixmap(pymupdf.csGRAY, pymupdf.IRect(0, 0, 160, 120), False)
        pix.clear_with(170)
        for i in range(0, 160, 40):
            for j in range(0, 120, 40):
                if (i // 40 + j // 40) % 2 == 0:
                    pix.set_rect(pymupdf.IRect(i, j, i + 40, j + 40), (110,))
        self.page.insert_image(pymupdf.Rect(x, y, x + w, y + h), pixmap=pix)

    def bar_chart(self, x: float, y: float, w: float, h: float, labels: list[str], values: list[float], unit: str) -> None:
        self.page.draw_line((x, y + h), (x + w, y + h), color=GRAY, width=1)
        self.page.draw_line((x, y), (x, y + h), color=GRAY, width=1)
        vmax = max(values) * 1.2
        bw = w / (len(values) * 2)
        for i, (lab, v) in enumerate(zip(labels, values)):
            bx = x + bw * (2 * i + 0.5)
            bh = h * v / vmax
            self.page.draw_rect(pymupdf.Rect(bx, y + h - bh, bx + bw, y + h), color=BLUE, fill=BLUE)
            self.text(bx + (bw - self.width(lab, 8)) / 2, y + h + 12, lab, 8)
            val = f"{v:g}{unit}"
            self.text(bx + (bw - self.width(val, 8)) / 2, y + h - bh - 4, val, 8)
        for k in range(5):
            yy = y + h - h * k / 4
            self.page.draw_line((x - 3, yy), (x, yy), color=GRAY, width=0.6)
            self.text(x - 26, yy + 3, f"{vmax * k / 4:.0f}", 7)

    # ---- 머리말·꼬리말 ----
    def frame(self, header: str, footer: str, page_no: int, number_style: str = "dash") -> None:
        self.text(40, 26, header, 8)
        self.text(40, self.h - 16, footer, 8)
        num = f"- {page_no} -" if number_style == "dash" else f"{page_no}"
        self.text(self.w - 40 - self.width(num, 8), self.h - 16, num, 8)

    def finish(self) -> None:
        self.tw.write_text(self.page)


def _rotated_text(page: pymupdf.Page, font: pymupdf.Font, vx: float, vy: float, s: str, size: float) -> None:
    """/Rotate 90 페이지에서 화면 기준 (vx, vy) 에 바로 선 글을 쓴다."""
    p = pymupdf.Point(vx, vy) * ~page.rotation_matrix
    tw = pymupdf.TextWriter(page.rect)
    tw.append(p, s, font=font, fontsize=size)
    tw.write_text(page, morph=(p, pymupdf.Matrix(90)))


# ------------------------------------------------------------------ 01 단일 단 불릿 보고서
def report_spindle(doc: pymupdf.Document, font: pymupdf.Font) -> None:
    H = "SV-700 고속 스핀들 진동 저감 과제 | 대외비"
    F = "생산기술연구소 정밀가공팀"
    n = 0

    def sheet() -> Sheet:
        nonlocal n
        n += 1
        s = Sheet(doc, font)
        s.frame(H, F, n)
        return s

    s = sheet()
    s.text(60, 200, "SV-700 고속 스핀들 진동 저감 개선 결과 보고", 28)
    s.text(60, 240, "베어링 예압 자동 조정 구조와 공진 회피 제어 적용", 16)
    s.text(60, 330, "생산기술연구소 정밀가공팀 · 설비제어팀", 13)
    s.text(60, 352, "2026. 10. 28.", 13)
    s.finish()

    s = sheet()
    y = s.heading(50, 70, "목차", 22)
    s.numbered(70, y + 10, 600, ["배경 및 문제점", "원인 분석", "개선안 1: 베어링 예압 자동 조정 구조", "개선안 2: 공진 회피 제어",
                                  "검증 결과", "양산 적용 일정 및 비용", "향후 계획"], 13, gap=10)
    s.finish()

    s = sheet()
    y = s.heading(50, 70, "배경 및 문제점", 22)
    y = s.bullets(60, y + 8, 720, [
        WRAPPED_BULLET,
        (SUB_BULLET, 1),
        ("가공 후 수정 작업으로 라인 가동률이 3.2%p 하락하고 월 2,400만 원의 재작업 비용 발생", 1),
        "진동 센서(가속도계) 데이터에서 24,000 rpm 이상 구간의 진동 속도 RMS 가 4.5 mm/s 로 ISO 10816 기준 2.8 mm/s 초과",
        "기존 대응은 회전수를 22,000 rpm 으로 낮추는 방법뿐이어서 사이클 타임이 11% 늘어남",
        "고객사 B 의 알루미늄 하우징 신규 모델은 24,000 rpm 가공이 필수 조건이라 근본 대책 필요",
    ], 13)
    s.finish()

    s = sheet()
    y = s.heading(50, 70, "원인 분석", 22)
    y = s.heading(60, y + 4, "1) 구조 요인", 14)
    y = s.numbered(70, y, 700, [
        NUMBERED_ITEM,
        "주축 전면 베어링 하우징의 냉각 재킷이 후면에만 있어 전후 온도차 14℃ 가 발생하고 예압이 비대칭으로 풀림",
        "스핀들 모터 로터와 주축의 열팽창 계수 차이(강 11.5 vs 알루미늄 23 ×10⁻⁶/℃)로 축방향 간섭이 변함",
    ], 12)
    y = s.heading(60, y + 6, "2) 제어 요인", 14)
    y = s.bullets(70, y, 700, [
        "가공 프로그램이 회전수를 고정값으로 지정해 공진 주파수가 이동해도 회피하지 못함",
        "진동 모니터링은 사후 알람만 발생시키고 제어기와 연동되어 있지 않음",
        ("알람 임계값 5.0 mm/s 는 불량 발생 시점(3.8 mm/s)보다 높게 설정되어 있었음", 1),
    ], 12)
    s.finish()

    s = sheet()
    y = s.heading(50, 70, "개선안 1: 베어링 예압 자동 조정 구조", 22)
    y = s.bullets(60, y + 8, 720, [
        "전면 베어링 외륜을 피에조 액추에이터 3점으로 지지하고 주축 온도 센서 값에 따라 축방향 예압을 0~800 N 범위에서 보정",
        ("액추에이터 변위 분해능 0.1 ㎛, 응답 시간 20 ms 로 열팽창 속도(최대 0.5 ㎛/s)보다 충분히 빠름", 1),
        ("예압 목표값은 회전수와 온도의 2차원 테이블로 관리하고 시운전 데이터로 초기 테이블을 채움", 1),
        "전면 하우징에 냉각 재킷을 추가하고 전후 냉각수 유량을 독립 제어하여 전후 온도차를 3℃ 이내로 유지",
        "외륜 끼워맞춤을 억지 끼워맞춤에서 중간 끼워맞춤으로 바꾸고 회전 방지 키를 추가",
        ("기존 스핀들 카트리지와 치수 호환을 유지해 현장 교체 시간 4시간 이내", 1),
        "제어 보드는 기존 CNC 의 PLC 입출력 모듈과 EtherCAT 으로 연결하며 별도 PC 가 필요 없음",
    ], 13)
    s.finish()

    s = sheet()
    y = s.heading(50, 70, "개선안 2: 공진 회피 제어", 22)
    y = s.para(60, y + 8, 720, "진동 센서의 주파수 스펙트럼을 100 ms 주기로 분석해 1차 공진 주파수를 추정하고, 현재 회전수가 공진 "
               "주파수의 ±8% 안에 들어오면 가공 부하가 작은 구간에서 회전수를 공진 밴드 바깥으로 자동 이동시킨다. 이동 폭은 "
               "공구 수명과 표면 조도 영향을 고려해 최대 6% 로 제한한다.", 13)
    y = s.para(60, y, 720, "회전수 변경은 이송 속도와 연동해 절삭량을 일정하게 유지하므로 가공 시간은 변하지 않는다. 공진 주파수 추정은 "
               "최근 30초 데이터의 이동 평균을 쓰며, 추정값이 급변하면 센서 이상으로 보고 이전 값을 유지한다.", 13)
    y = s.heading(60, y + 4, "제어식", 14)
    s.text(80, y, "n_cmd = n_set × (1 + k · sgn(f_res − f_cur) · min(|f_res − f_cur| / f_res, 0.06))", 12)
    y += 30
    s.bullets(60, y, 720, ["k 는 공구 종류별 계수(엔드밀 0.8, 페이스밀 1.0), f_res 는 추정 공진 주파수, f_cur 는 현재 회전 주파수",
                           "시운전에서 k 를 0.5~1.2 로 바꿔 가며 표면 조도와 진동을 함께 측정해 결정"], 12)
    s.finish()

    s = sheet()
    y = s.heading(50, 70, "검증 결과", 22)
    y = s.table(60, y + 6, [170, 130, 130, 130, 160], [
        ["항목", "개선 전", "개선 후", "목표", "비고"],
        ["진동 속도 RMS (24,000 rpm)", "4.5 mm/s", "1.9 mm/s", "2.8 mm/s 이하", "ISO 10816 Zone B"],
        ["표면 거칠기 Ra", "0.52 ㎛", "0.28 ㎛", "0.4 ㎛ 이하", "알루미늄 하우징 기준"],
        ["전후 베어링 온도차", "14 ℃", "2.6 ℃", "3 ℃ 이내", "6시간 연속 가공"],
        ["월 불량 건수", "42 건", "3 건", "5 건 이하", "9월 실적"],
    ], 11)
    s.bullets(60, y + 6, 720, [
        "두 개선안을 모두 적용한 조건의 결과이며, 개선안 1 만 적용 시 진동 2.7 mm/s, 개선안 2 만 적용 시 3.1 mm/s",
        "공구 수명은 변화 없음(엔드밀 평균 41분 → 42분), 사이클 타임은 22,000 rpm 운전 대비 10% 단축",
    ], 12)
    s.finish()

    s = sheet()
    y = s.heading(50, 70, "양산 적용 일정 및 비용", 22)
    y = s.bullets(60, y + 8, 720, [
        "2026년 11월 1호기 개조 완료, 12월 2주간 양산 검증 후 2027년 1분기에 나머지 7대 순차 적용",
        "개조 비용 대당 3,800만 원(액추에이터 1,200, 냉각 재킷 900, 제어 보드 700, 공사 1,000), 총 3.04억 원",
        "재작업 비용 절감 월 2,400만 원과 가동률 회복 효과로 투자 회수 기간 약 11개월",
        "담당: 정밀가공팀(구조 설계·검증), 설비제어팀(제어 소프트웨어), 구매팀(액추에이터 조달)",
        "2027. 3. 31. 까지 전 호기 적용 완료 목표, 월간 설비 회의에서 진행 상황 보고",
    ], 13)
    s.finish()

    s = sheet()
    y = s.heading(50, 70, "향후 계획", 22)
    y = s.bullets(60, y + 8, 720, [
        "예압 자동 조정 구조를 차기 모델 SV-900(30,000 rpm)에 기본 사양으로 반영",
        "공진 회피 제어를 다축 가공기로 확장하고 채터 예측 모델과 결합",
        "진동·온도 데이터를 설비 데이터 플랫폼에 저장해 베어링 잔여 수명 예측에 활용",
        "사내 스핀들 설계 표준 개정 추진(2027년 상반기)",
    ], 13)
    s.text(380, 420, "감사합니다", 20)
    s.text(410, 450, "Q&A", 13)
    s.finish()


# ------------------------------------------------------------------ 02 문서형 2단·3단 기술 검토서
def report_thermal(doc: pymupdf.Document, font: pymupdf.Font) -> None:
    H = "배터리 팩 열관리 제어 로직 검토서  v1.2"
    F = "Confidential · 열관리개발팀"
    n = 0

    def sheet() -> Sheet:
        nonlocal n
        n += 1
        s = Sheet(doc, font, PORTRAIT)
        s.frame(H, F, n, "plain")
        return s

    L, R, CW = 50, 310, 240   # 2단: 왼쪽 x, 오른쪽 x, 단 폭
    s = sheet()
    y = s.heading(50, 80, "배터리 팩 열관리 제어 로직 검토서", 20)
    y = s.para(50, y, 500, "본 문서는 모듈 간 온도 편차를 줄이기 위한 냉각수 분배 제어 방식을 검토한 결과를 정리한 것이다. 현행 방식의 "
               "한계와 제안 방식의 구성, 시뮬레이션 결과, 적용 시 고려 사항을 다룬다. 수치는 모두 합성 예시이다.", 11)
    y = s.para(50, y, 500, "요약: 모듈별 온도 센서를 활용한 비례 분배 제어로 온도 편차를 2.1℃ 에서 0.8℃ 로 줄일 수 있으며, 펌프 소비 "
               "전력은 6% 감소한다. 밸브 구동기 추가에 따른 원가 상승은 팩당 약 1.4만 원이다.", 11)
    y0 = y + 6
    s.heading(L, y0, "1. 현행 방식과 문제", 13)
    s.heading(R, y0, "2. 제안 방식", 13)
    yl = y0 + 22
    yl = s.para(L, yl, CW, LEFT_COLUMN_FIRST, 10)
    yl = s.para(L, yl, CW, "급속 충전 중 중앙 모듈의 온도가 가장자리 모듈보다 평균 2.1℃ 높게 유지되며, 이 편차가 셀 열화 속도의 "
                "차이로 이어져 팩 수명을 설계값보다 8% 단축시키는 것으로 추정된다.", 10)
    yl = s.bullets(L, yl, CW, ["펌프 듀티 3단계(40/70/100%)", "입구 온도 기준 히스테리시스 2℃", "모듈 온도는 알람에만 사용"], 10)
    yr = y0 + 22
    yr = s.para(R, yr, CW, RIGHT_COLUMN_FIRST, 10)
    yr = s.para(R, yr, CW, "분배 비율은 모듈 열용량의 역수에 비례하도록 계산하고, 계산된 비율은 5초 이동 평균으로 평활화한 뒤 "
                "밸브 구동기에 전달한다. 편차가 0.5℃ 이하로 줄면 기본 분배 비율로 복귀한다.", 10)
    yr = s.bullets(R, yr, CW, ["센서 주기 1초, 제어 주기 5초", "밸브 개도 범위 20~100%", "펌프 듀티는 총 유량 요구에 따라 연속 가변"], 10)
    s.finish()

    s = sheet()
    y0 = 80
    s.heading(L, y0, "3. 제어 로직 상세", 13)
    s.heading(R, y0, "4. 영문 요약 (Abstract)", 13)
    yl = y0 + 22
    yl = s.para(L, yl, CW, "편차 계산은 유효한 센서 값만 사용한다. 센서 값이 1초 안에 5℃ 이상 변하거나 범위(-40~120℃)를 벗어나면 "
                "해당 센서를 제외하고, 유효 센서가 8점 미만이면 기본 분배 비율로 전환하며 진단 코드를 기록한다.", 10)
    yl = s.para(L, yl, CW, "밸브 개도 변경은 1회당 최대 10%p 로 제한해 유량 충격을 막는다. 개도 변경 후 15초 동안은 편차를 다시 "
                "평가하지 않아 제어 진동을 방지한다.", 10)
    yl = s.numbered(L, yl, CW, ["모듈 온도 12점 읽기", "이상 센서 제외 후 최댓값·최솟값 계산", "편차 ≥ 1℃ 이면 분배 비율 갱신",
                                "개도 명령 전송 및 15초 대기"], 10)
    yr = y0 + 22
    yr = s.para(R, yr, CW, "This document reviews a proportional coolant distribution scheme for battery packs. "
                "Module temperatures are sampled every second and the spread between the hottest and the coldest module "
                "drives the valve opening of each branch.", 10)
    for ln in ("The controller applies a feed-forward term com-", "puted from the predicted heat load of each", "module."):
        s.text(R, yr, ln, 10)                                     # 줄 끝 하이픈: 'com-' + 'puted' → 'computed'
        yr += 15.5
    yr = s.para(R, yr + 6, CW, "Simulation shows a spread reduction from 2.1 to 0.8 degrees with a 6% lower pump energy.", 10)
    y = max(yl, yr) + 10
    y = s.heading(L, y, "5. 시뮬레이션 조건", 13)
    s.table(L, y, [110, 130, 130, 130], [
        ["항목", "현행", "제안", "비고"],
        ["급속 충전 전류", "150 A", "150 A", "SOC 20→80%"],
        ["외기 온도", "35 ℃", "35 ℃", "여름 조건"],
        ["온도 편차 (최대-최소)", "2.1 ℃", "0.8 ℃", "충전 종료 시점"],
        ["펌프 소비 전력", "48 W", "45 W", "평균값, 6% 감소"],
    ], 10)
    s.finish()

    s = sheet()
    y = s.heading(50, 80, "6. 개선안 비교", 16)
    xs = (50, 225, 400)
    cw3 = 160
    ys = []
    bodies = (
        ["분배 밸브 3개 추가, 모듈 온도 비례 제어", "온도 편차 0.8℃, 원가 +1.4만 원", "제어 로직 변경 범위 중간"],
        ["펌프 듀티를 0~100% 연속 가변", "온도 편차 1.6℃, 원가 변동 없음", "편차 자체는 줄이지 못함"],
        ["중앙 모듈에 독립 유로 추가", "온도 편차 0.5℃, 원가 +4.8만 원", "팩 구조 변경으로 금형 수정 필요"],
    )
    for x, head, body in zip(xs, COLUMN_HEADS, bodies):
        s.page.draw_rect(pymupdf.Rect(x - 6, y - 16, x + cw3 + 6, y + 150), color=GRAY, width=0.8)
        yy = s.wrap(x, y, cw3, head, 11)
        yy = s.bullets(x, yy + 2, cw3, body, 9)
        ys.append(yy)
    y = max(ys) + 24
    y = s.heading(50, y, "7. 결론", 13)
    y = s.para(50, y, 500, "개선안 A 가 원가와 효과의 균형이 가장 좋다. 개선안 C 는 효과가 크지만 금형 수정으로 적용 시점이 1년 이상 "
               "늦어지므로 차기 팩 설계에 반영한다. 개선안 B 는 A 와 함께 적용하면 펌프 전력을 추가로 4% 줄일 수 있다.", 11)
    s.para(50, y, 500, "다음 단계로 실차 팩 1대에 분배 밸브를 장착해 11월까지 급속 충전 시험을 수행하고, 시험 결과로 분배 비율 "
           "계산식의 계수를 확정한다.", 11)
    s.finish()

    s = sheet()
    y = s.heading(50, 80, "8. 시험 조건 및 결과", 16)
    y = s.table(50, y, [120, 190, 190], [
        ["시험", "조건", "판정 기준"],
        ["급속 충전 열 시험", "SOC 20→80%, 150 A, 외기 35℃, 3회 반복", "모듈 간 편차 1.0℃ 이하, 최고 온도 45℃ 이하"],
        ["센서 고장 모사", "센서 2점 단선, 2점 단락", "기본 분배로 전환, 진단 코드 기록, 편차 1.5℃ 이하"],
        ["밸브 고착 모사", "분기 1 밸브 50% 고정", "나머지 분기로 보상, 편차 1.2℃ 이하"],
    ], 10)
    y = s.para(50, y, 500, "표의 판정 기준은 사내 열관리 시험 표준 TM-07 의 급속 충전 항목을 따랐다. 센서 고장 모사는 "
               "실제 단선 대신 신호선에 저항을 삽입해 구현했다.", 10)
    y = s.table(50, y + 6, [120, 100, 100, 180], [
        ["시험", "결과", "판정", "비고"],
        ["급속 충전 열 시험", "편차 0.8℃", "합격", "최고 온도 43.2℃"],
        ["센서 고장 모사", "편차 1.3℃", "합격", "전환 지연 4초"],
        ["밸브 고착 모사", "편차 1.4℃", "불합격", "보상 로직 계수 재조정 필요"],
    ], 10)
    s.para(50, y, 500, "밸브 고착 시험은 보상 계수를 1.5 로 올린 뒤 재시험에서 편차 1.1℃ 로 합격했다. 계수 변경은 로직 v1.3 에 반영한다.", 10)
    s.finish()


# ------------------------------------------------------------------ 03 도식 중심 보고서
def report_fusion(doc: pymupdf.Document, font: pymupdf.Font) -> None:
    H = "센서 융합 인식 성능 개선 과제 | 대외비"
    F = "자율주행인식팀"
    n = 0

    def sheet() -> Sheet:
        nonlocal n
        n += 1
        s = Sheet(doc, font)
        s.frame(H, F, n)
        return s

    s = sheet()
    y = s.heading(50, 70, "융합 제어 구조", 22)
    bx, by, bw, bh = 60, 150, 110, 50
    for i, label in enumerate(BLOCK_LABELS[:4]):
        s.box(bx + i * 140, by, bw, bh, label, 10)
        if i < 3:
            s.arrow(bx + i * 140 + bw, by + bh / 2, bx + (i + 1) * 140, by + bh / 2)
    s.box(bx + 140, by + 110, bw, bh, BLOCK_LABELS[4], 10)
    s.arrow(bx + 140 + bw / 2, by + 110, bx + 140 + bw / 2, by + bh)
    s.text(bx, by + 200, "그림 1. 야간 신뢰도 기반 가중치 제어 구조", 10)
    s.bullets(610, 150, 200, [
        "Confidence 추정기는 카메라 영상의 조도와 대비를 100 ms 마다 계산해 0~1 사이 신뢰도로 변환",
        "가중치 제어기는 신뢰도가 0.4 아래로 내려가면 레이더 가중치를 0.5 에서 0.8 로 올리고 카메라 가중치를 낮춤",
        "진단 모듈은 두 센서 판단이 2초 이상 어긋나면 운전자에게 알림",
    ], 11)
    s.finish()

    s = sheet()
    y = s.heading(50, 70, "야간 오검출률 비교", 22)
    s.bar_chart(90, 130, 320, 200, ["기존 고정 가중치", "제안 방식", "제안+진단"], [8.4, 5.1, 4.6], "%")
    s.text(90, 360, "그림 2. 야간 주행 2,000 km 기준 오검출률", 10)
    s.para(470, 140, 330, "제안 방식은 야간 시나리오에서 오검출률을 8.4% 에서 5.1% 로 낮췄다. 진단 모듈을 함께 켜면 "
           "두 센서가 어긋난 구간을 제외해 4.6% 까지 내려간다.", 12)
    s.para(470, 230, 330, "주간 시나리오에서는 세 조건 모두 2.0% 안팎으로 차이가 없었다. 신뢰도 임계값 0.4 는 "
           "터널 진입 구간의 급격한 조도 변화를 기준으로 정했다.", 12)
    s.finish()

    s = sheet()
    s.text(50, 70, "야간 시험 주행 장면", 22)
    s.image(60, 100, 720, 440)
    s.text(60, 560, "그림 3. 시험 차량 전방 카메라 영상 (합성 예시 이미지)", 10)
    s.finish()

    s = sheet()
    y = s.heading(50, 70, "가중치 전환 순서도", 22)
    fx, fy = 80, 120
    steps = ["조도·대비 계산", "신뢰도 < 0.4 ?", "레이더 가중치 0.8", "가중치 유지", "융합 결과 출력"]
    s.box(fx, fy, 150, 40, steps[0], 10)
    s.arrow(fx + 75, fy + 40, fx + 75, fy + 70)
    s.box(fx, fy + 70, 150, 40, steps[1], 10)
    s.arrow(fx + 75, fy + 110, fx + 75, fy + 140)
    s.text(fx + 80, fy + 130, "Yes", 9)
    s.box(fx, fy + 140, 150, 40, steps[2], 10)
    s.arrow(fx + 150, fy + 90, fx + 230, fy + 90)
    s.text(fx + 180, fy + 84, "No", 9)
    s.box(fx + 230, fy + 70, 150, 40, steps[3], 10)
    s.arrow(fx + 75, fy + 180, fx + 75, fy + 210)
    s.box(fx, fy + 210, 150, 40, steps[4], 10)
    s.numbered(500, 130, 300, [
        "카메라 프레임마다 평균 조도와 대비를 계산하고 100 ms 이동 평균을 취한다",
        "신뢰도가 0.4 아래이면 레이더 가중치를 0.8 로 올리고 전환은 500 ms 에 걸쳐 선형으로 수행한다",
        "신뢰도가 0.6 을 다시 넘으면 기본 가중치로 복귀한다(히스테리시스 0.2)",
        "전환 중에는 진단 모듈의 어긋남 판정을 멈춘다",
    ], 11)
    s.finish()

    s = sheet()
    y = s.heading(50, 70, "개선 항목 우선순위 매트릭스", 22)
    cells = [
        ("효과 큼 · 적용 쉬움", ["신뢰도 기반 가중치 전환", "히스테리시스 0.2 적용"]),
        ("효과 큼 · 적용 어려움", ["레이더 포인트 클라우드 재학습", "카메라 HDR 모드 연동"]),
        ("효과 작음 · 적용 쉬움", ["알림 문구 개선", "로그 저장 주기 단축"]),
        ("효과 작음 · 적용 어려움", ["초음파 센서 추가", "차량 간 통신 활용"]),
    ]
    for i, (head, items) in enumerate(cells):
        x = 80 + (i % 2) * 360
        yy = 120 + (i // 2) * 200
        s.page.draw_rect(pymupdf.Rect(x, yy, x + 340, yy + 180), color=GRAY, width=1.0, fill=LIGHT if i == 0 else None)
        s.text(x + 12, yy + 26, head, 12)
        s.bullets(x + 12, yy + 56, 310, items, 11)
    s.finish()


# ------------------------------------------------------------------ 04 표 중심 보고서
def report_process(doc: pymupdf.Document, font: pymupdf.Font) -> None:
    H = "LP-40 라인 공정 불량 개선 보고 | 대외비"
    F = "생산기술팀"
    n = 0

    def sheet() -> Sheet:
        nonlocal n
        n += 1
        s = Sheet(doc, font)
        s.frame(H, F, n)
        return s

    s = sheet()
    s.text(60, 220, "LP-40 라인 공정 불량 개선 결과 보고", 28)
    s.text(60, 260, "도포 공정 폐루프 제어와 비전 검사 조명 개선", 16)
    s.text(60, 340, "생산기술팀 · 품질보증팀", 13)
    s.text(60, 362, "2026. 10.", 13)
    s.finish()

    s = sheet()
    y = s.heading(50, 70, "공정별 불량 현황", 22)
    y = s.table(60, y + 6, [120, 110, 110, 110, 270], [
        ["공정", "3월 불량률", "6월 불량률", "9월 불량률", "주요 불량 유형"],
        ["세정", "2.4 %", "1.6 %", "0.9 %", "잔류 이물, 얼룩"],
        ["도포", "3.1 %", "1.8 %", "0.7 %", "두께 편차, 기포"],
        ["경화", "1.2 %", "1.2 %", "1.1 %", "미경화(저온 구간)"],
        ["검사", "0.8 %", "0.5 %", "0.3 %", "과검출(조명 반사)"],
        ["합계", "7.5 %", "5.1 %", "3.0 %", "목표 3.5 % 달성"],
    ], 11)
    s.text(60, y + 6, "※ 불량률은 월간 생산 수량 대비 공정 불량 수량. 9월은 개선 적용 후 첫 달 실적.", 10)
    s.finish()

    s = sheet()
    y = s.heading(50, 70, "도포 공정 개선 방향", 22)
    s.table(60, y + 6, [120, 110, 110], [
        ["인자", "개선 전", "개선 후"],
        ["노즐 압력", "고정 0.30 MPa", "두께 센서 폐루프"],
        ["토출 온도", "실온", "28 ℃ 항온"],
        ["라인 속도", "12 m/min", "12 m/min"],
        ["두께 편차", "±18 ㎛", "±6 ㎛"],
    ], 11)
    s.bullets(430, y + 14, 370, [
        "두께 센서(레이저 변위계 2점)를 노즐 하류 300 mm 에 설치하고 측정값으로 노즐 압력을 0.2~0.4 MPa 범위에서 PI 제어",
        "제어 주기는 200 ms, 라인 속도 12 m/min 에서 두께 변화가 40 mm 이동 안에 반영됨",
        "토출 온도를 28℃ 로 유지해 점도 변동을 줄이고, 압력 제어 범위를 좁혀 기포 발생을 억제",
        "두께 편차 ±6 ㎛ 는 고객 규격 ±10 ㎛ 를 여유 있게 만족",
    ], 12)
    s.finish()

    s = sheet()
    y = s.heading(50, 70, "공정별 조치 요약", 22)
    y = s.table(60, y + 10, [120, 170, 170, 300], TEXT_TABLE, 12, borders=False, header=False)
    s.para(60, y + 10, 720, "세정과 도포 공정의 개선 효과가 크고, 경화 공정은 저온 구간 미경화가 남아 있어 히터 배치 변경을 4분기에 "
           "검토한다. 검사 공정의 과검출은 조명 각도를 45도에서 30도로 바꿔 반사를 줄인 결과이다.", 12)
    s.finish()

    s = sheet()
    y = s.heading(50, 70, "추진 일정", 22)
    months = ["구분", "10월", "11월", "12월", "1월", "2월", "3월"]
    y = s.table(60, y + 6, [160, 100, 100, 100, 100, 100, 100], [months,
                                                                    ["도포 폐루프 제어 2호기 적용", "■■", "■■", "", "", "", ""],
                                                                    ["경화 히터 배치 변경 검토", "", "■■", "■■", "", "", ""],
                                                                    ["경화 히터 개조 공사", "", "", "", "■■", "■■", ""],
                                                                    ["검사 조명 전 라인 적용", "■■", "", "", "", "", ""],
                                                                    ["효과 검증 및 표준 개정", "", "", "", "", "■■", "■■"]], 11)
    y = s.table(60, y + 6, [160, 200, 200], [["구분", "담당", "협조"], ["도포 제어", "생산기술팀 김OO", "설비팀"],
                                            ["경화 개조", "생산기술팀 이OO", "설비팀, 안전환경팀"], ["검사 조명", "품질보증팀 박OO", "생산기술팀"]], 11)
    s.finish()

    s = sheet()
    y = s.heading(50, 70, "결론 및 향후 계획", 22)
    s.bullets(60, y + 8, 720, [
        "공정 불량률 7.5% → 3.0% 로 목표 3.5% 를 달성했으며, 도포 폐루프 제어가 가장 큰 기여(불량률 2.4%p 감소)",
        "노즐 압력 폐루프 제어 방식은 타 라인(LP-20, LP-60)에도 적용 가능하며 센서 설치 위치만 라인별로 조정",
        "경화 공정 미경화는 히터 배치 변경으로 해결 예정이며, 변경 전까지 저온 구간 라인 속도를 10% 낮춰 대응",
        "검사 조명 각도 변경 결과를 검사 표준 QS-112 에 반영하고 타 라인 전개",
    ], 13)
    s.finish()


# ------------------------------------------------------------------ 05 영문 혼용·규격 검토서 (회전 페이지 포함)
def report_mixed(doc: pymupdf.Document, font: pymupdf.Font) -> None:
    H = "SC-10 안전 제어기 규격 적합성 검토  Rev. B"
    F = "기능안전팀"
    n = 0

    def sheet() -> Sheet:
        nonlocal n
        n += 1
        s = Sheet(doc, font, PORTRAIT)
        s.frame(H, F, n, "plain")
        return s

    s = sheet()
    y = s.heading(50, 80, "SC-10 안전 제어기 규격 적합성 검토", 20)
    y = s.heading(50, y + 4, "1. Scope", 13)
    y = s.para(50, y, 500, "본 검토는 SC-10 안전 제어기의 하드웨어 구조와 진단 기능이 아래 규격의 요구 사항을 만족하는지 확인한다. "
               "대상은 2채널 입력 비교기, 워치독, 전원 감시 회로이다.", 11)
    s.text(70, y, ENGLISH_ONLY, 11)
    y += 22
    s.text(70, y, "Target device: SC-10 Rev. B, MCU STM32H743 (dual-core lockstep configuration)", 11)
    y += 22
    y = s.heading(50, y + 4, "2. Safety function", 13)
    y = s.para(50, y, 500, "두 입력 채널의 값이 20 ms 이상 10% 넘게 다르면 출력을 안전 상태(OFF)로 전환한다. 전환 지연은 입력 필터 "
               "5 ms 와 비교 주기 10 ms 를 더한 15 ms 이내이다. 토크 제한은 다음 식으로 계산한다.", 11)
    s.text(70, y, FORMULA, 12)
    y += 24
    y = s.bullets(50, y, 500, ["τ: 허용 토크, J: 관성, α: 각가속도, c: 점성 계수, ω: 각속도, K: 강성, θ: 각변위",
                               "계수는 축별 파라미터 테이블에서 읽으며 플래시 CRC 로 무결성을 확인"], 10)
    s.finish()

    s = sheet()
    y = s.heading(50, 80, "3. Diagnostic coverage", 13)
    y = s.bullets(50, y, 500, [
        "워치독은 윈도우 방식(window 8~12 ms)으로 동작하며 MCU 두 코어가 교대로 리셋 신호를 갱신한다",
        "전원 감시 회로는 3.3 V 레일이 ±5% 를 벗어나면 150 ㎲ 안에 리셋을 발생시킨다",
        "RAM 은 March-C 알고리즘으로 기동 시 전체 검사, 운전 중에는 4 KB 단위로 순환 검사",
        ("검사 1회 주기는 24 시간 이내로 IEC 61508 의 진단 시험 간격 요구를 만족", 1),
        "ADC 입력은 기준 전압 2점을 주기적으로 읽어 이득 오차 0.5% 이상이면 채널 고장으로 판정",
    ], 11)
    y = s.heading(50, y + 6, "4. Labels", 13)
    for lab in ("DC = 92 %", "SFF = 96 %", "PFH = 3.2E-8 /h", "HFT = 1", "Type B"):
        s.text(70, y, lab, 11)
        y += 18
    y = s.para(50, y + 6, 500, "위 지표는 FMEDA 결과이며, 진단 커버리지 92% 는 SIL 2 의 요구(90% 이상)를 만족한다. "
               "PFH 값은 평균 수리 시간 8시간, 운전 시간 8,760 시간/년 조건으로 계산했다.", 11)
    s.finish()

    # 회전 페이지: /Rotate 90 이지만 화면에서는 바로 선 글
    page = doc.new_page(width=PORTRAIT[0], height=PORTRAIT[1])
    page.set_rotation(90)
    n += 1
    _rotated_text(page, font, 40, 26, H, 8)
    _rotated_text(page, font, 50, 70, "5. 모듈 온도 시험 결과 (가로 표 페이지)", 18)
    _rotated_text(page, font, 60, 110, ROTATED_LINE, 11)
    vx, vy = 60, 140
    cols = [150, 150, 150, 200]
    rows = [["조건", "현행 편차", "개선 편차", "비고"], ["급속 충전 150 A", "2.1 ℃", "0.8 ℃", "외기 35 ℃"], ["완속 충전 30 A", "0.9 ℃", "0.4 ℃", "외기 25 ℃"]]
    for r, row in enumerate(rows):
        cx = vx
        for cw, cell in zip(cols, row):
            p1 = pymupdf.Point(cx, vy) * ~page.rotation_matrix
            p2 = pymupdf.Point(cx + cw, vy + 24) * ~page.rotation_matrix
            page.draw_rect(pymupdf.Rect(p1, p2), color=GRAY, width=0.8)
            _rotated_text(page, font, cx + 5, vy + 16, cell, 10)
            cx += cw
        vy += 24
    _rotated_text(page, font, 60, vy + 24, "표의 개선 편차는 분배 밸브 비례 제어를 적용한 시뮬레이션 값이다.", 11)
    _rotated_text(page, font, 40, LANDSCAPE[1] - 16, f"{F}   {n}", 8)

    # 옆으로 누운 글 페이지: 도면을 세로로 돌려 넣은 경우
    s = sheet()
    s.text(60, 80, "6. 도면", 13)
    s.finish()
    tw = pymupdf.TextWriter(s.page.rect)
    for i, line in enumerate(["배관 계통도 - 분배 밸브 V1, V2, V3", "펌프 P1 → 열교환기 HX1 → 모듈 1~12", "밸브 개도 20~100 %, 신호 4~20 mA"]):
        p = pymupdf.Point(120 + i * 30, 700)
        tw2 = pymupdf.TextWriter(s.page.rect)
        tw2.append(p, line, font=font, fontsize=11)
        tw2.write_text(s.page, morph=(p, pymupdf.Matrix(-90)))
    s.page.draw_rect(pymupdf.Rect(100, 150, 500, 720), color=GRAY, width=1.0)
    tw.append((60, 760), SIDEWAYS_CAPTION, font=font, fontsize=10)
    tw.write_text(s.page)


REPORTS = (
    ("layout_01_single_column", report_spindle),
    ("layout_02_two_columns", report_thermal),
    ("layout_03_diagrams", report_fusion),
    ("layout_04_tables", report_process),
    ("layout_05_mixed_rotated", report_mixed),
)


def make_report(name: str, out_dir: Path, font: pymupdf.Font | None = None) -> Path:
    fn = dict(REPORTS)[name]
    font = font or _font()
    doc = pymupdf.open()
    fn(doc, font)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{name}.pdf"
    doc.subset_fonts()
    doc.save(str(out), garbage=4, deflate=True)
    doc.close()
    return out


def make_all(out_dir: Path) -> list[Path]:
    font = _font()
    return [make_report(name, out_dir, font) for name, _ in REPORTS]


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("demo") / "layout"
    for p in make_all(target):
        print(p)
