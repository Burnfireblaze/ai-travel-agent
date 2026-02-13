from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import chromadb

from .embeddings import build_embedding_function
from .schemas import MemoryHit, MemoryMetadata, MemoryDocType


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class MemoryStore:
    user_id: str
    persist_dir: Path
    embedding_model: str
    session_collection_name: str = "session_memory"
    user_collection_name: str = "user_memory"

    def __post_init__(self) -> None:
        self.persist_dir = self.persist_dir.resolve()
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        self._embedding_fn = build_embedding_function(self.embedding_model)

        self._persistent_client = chromadb.PersistentClient(path=str(self.persist_dir))
        try:
            self._session_client = chromadb.EphemeralClient()
        except Exception:
            self._session_client = chromadb.Client()

        self._session = self._session_client.get_or_create_collection(
            name=self.session_collection_name, embedding_function=self._embedding_fn
        )
        self._user = self._persistent_client.get_or_create_collection(
            name=self.user_collection_name, embedding_function=self._embedding_fn
        )

    def add_session(
        self,
        *,
        text: str,
        run_id: str,
        doc_type: MemoryDocType,
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        return self._add(self._session, text=text, run_id=run_id, doc_type=doc_type, metadata=metadata)

    def add_user(
        self,
        *,
        text: str,
        run_id: str,
        doc_type: MemoryDocType,
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        return self._add(self._user, text=text, run_id=run_id, doc_type=doc_type, metadata=metadata)

    def _add(self, collection, *, text: str, run_id: str, doc_type: MemoryDocType, metadata: Mapping[str, Any] | None):
        doc_id = str(uuid.uuid4())
        meta: MemoryMetadata = {
            "type": doc_type,
            "user_id": self.user_id,
            "run_id": run_id,
            "created_at": _utc_now_iso(),
        }
        if metadata:
            meta.update({k: v for k, v in metadata.items() if v is not None})
        collection.add(ids=[doc_id], documents=[text], metadatas=[meta])
        return doc_id

    def search(
        self,
        *,
        query: str,
        k: int = 5,
        include_session: bool = True,
        include_user: bool = True,
    ) -> list[MemoryHit]:
        hits: list[MemoryHit] = []
        if include_user:
            hits.extend(self._query_collection(self._user, query=query, k=k))
        if include_session:
            hits.extend(self._query_collection(self._session, query=query, k=k))
        hits.sort(key=lambda h: (h.distance if h.distance is not None else 1e9))
        return hits[:k]

    def _query_collection(self, collection, *, query: str, k: int) -> list[MemoryHit]:
        res = collection.query(query_texts=[query], n_results=k, include=["documents", "metadatas", "distances"])
        out: list[MemoryHit] = []
        ids = res.get("ids", [[]])[0]
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0] if "distances" in res else [None] * len(ids)
        for doc_id, text, meta, dist in zip(ids, docs, metas, dists, strict=False):
            out.append(MemoryHit(id=doc_id, text=text, metadata=meta, distance=dist))
        return out

    def reset_session(self) -> None:
        self._session_client.delete_collection(self.session_collection_name)
        self._session = self._session_client.get_or_create_collection(
            name=self.session_collection_name, embedding_function=self._embedding_fn
        )

