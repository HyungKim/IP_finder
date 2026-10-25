"""후처리: 제목 기반 보정, 재현율 안전장치, 섹션 묶기, 논의 포인트 템플릿."""
from .title_fix import apply_title_fix
from .safety_net import apply_safety_net
from .sections import assign_sections, section_name
from .templates import discussion_point

__all__ = ["apply_title_fix", "apply_safety_net", "assign_sections", "section_name", "discussion_point"]
