from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable, List


@dataclass(frozen=True)
class DeterministicHashEmbeddingFunction:
    dim: int = 384

    def __call__(self, texts: Iterable[str]) -> List[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            buf = (digest * ((self.dim * 4 // len(digest)) + 1))[: self.dim * 4]
            vec: list[float] = []
            for i in range(0, len(buf), 4):
                n = int.from_bytes(buf[i : i + 4], "little", signed=False)
                vec.append(((n % 2000) - 1000) / 1000.0)
            vectors.append(vec)
        return vectors


def build_embedding_function(model_name: str):
    try:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

        return SentenceTransformerEmbeddingFunction(model_name=model_name)
    except Exception:
        return DeterministicHashEmbeddingFunction()

