"""분류기 입력 특성.
- cue_matrix: 정규식 단서 13개(cues.cue_features)를 0/1 행렬로. 임베딩 뒤에 이어 붙인다(softmax, ovr).
- ngram_matrix: 글자 2·3-gram 을 해시로 고정 길이 벡터에 담는다(ngram 분류기). 임베딩 모델이 전혀 없어도 동작하는 비교 기준."""
from __future__ import annotations

import re
import zlib

import numpy as np

from ..cues import FEATURE_NAMES, cue_features

NGRAM_DIM = 4096
_SPACE = re.compile(r"\s+")


def cue_matrix(texts: list[str], page_types: list[str]) -> np.ndarray:
    return np.asarray([cue_features(t, pt) for t, pt in zip(texts, page_types)], dtype=np.float32)


def with_cues(vectors: np.ndarray, texts: list[str], page_types: list[str]) -> np.ndarray:
    """임베딩 + 단서 특성 (열 이어 붙이기)."""
    V = np.asarray(vectors, dtype=np.float32)
    return np.hstack([V, cue_matrix(texts, page_types)])


def ngram_matrix(texts: list[str], dim: int = NGRAM_DIM) -> np.ndarray:
    """문장마다 글자 2-gram·3-gram 을 세어 해시 버킷에 더한 뒤 길이 1 로 정규화한다. 공백은 하나로 줄이고 소문자로 맞춘다."""
    M = np.zeros((len(texts), dim), dtype=np.float32)
    for r, t in enumerate(texts):
        s = _SPACE.sub(" ", str(t)).strip().lower()
        if not s:
            continue
        for n in (2, 3):
            for i in range(len(s) - n + 1):
                M[r, zlib.crc32(s[i:i + n].encode("utf-8")) % dim] += 1.0
        norm = np.linalg.norm(M[r])
        if norm > 0:
            M[r] /= norm
    return M


__all__ = ["FEATURE_NAMES", "cue_matrix", "with_cues", "ngram_matrix", "NGRAM_DIM"]
