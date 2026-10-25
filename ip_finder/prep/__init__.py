"""전처리: 페이지 제외 규칙 → 줄 제거 규칙 → 번호 부여·분할. LLM을 쓰지 않는다."""
from .page_rules import apply_page_rules
from .line_rules import apply_line_rules
from .splitter import number_lines
from .page_type import page_type, TYPE_KEYS, HINT_BY_KEY

__all__ = ["apply_page_rules", "apply_line_rules", "number_lines", "page_type", "TYPE_KEYS", "HINT_BY_KEY"]
