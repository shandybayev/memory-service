"""TF-IDF semantic encoding for hybrid retrieval."""

from __future__ import annotations

import re

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer


def _tokenize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class SemanticEncoder:
    """Lightweight semantic similarity via character/word n-gram TF-IDF."""

    def __init__(self) -> None:
        self._vectorizer: TfidfVectorizer | None = None
        self._fitted = False

    def encode_single(self, text: str) -> list[float]:
        vec = self._fit_and_transform([text])
        return vec[0].tolist()

    def encode_batch(self, texts: list[str]) -> np.ndarray:
        return self._fit_and_transform(texts)

    def similarity(self, query: str, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.array([])
        cleaned = [_tokenize(t) for t in texts]
        query_clean = _tokenize(query)
        vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, stop_words="english")
        matrix = vectorizer.fit_transform([query_clean, *cleaned])
        query_vec = matrix[0]
        doc_matrix = matrix[1:]
        scores = (doc_matrix @ query_vec.T).toarray().ravel()
        max_score = scores.max() if scores.size else 0.0
        if max_score > 0:
            scores = scores / max_score
        return scores

    def _fit_and_transform(self, texts: list[str]) -> np.ndarray:
        cleaned = [_tokenize(t) for t in texts]
        vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, stop_words="english")
        matrix = vectorizer.fit_transform(cleaned)
        return matrix.toarray()
