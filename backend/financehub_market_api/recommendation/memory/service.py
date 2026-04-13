from __future__ import annotations

from typing import Protocol


class MemoryStore(Protocol):
    def search(self, query: str, *, limit: int) -> list[str]:
        """Return ranked memory snippets for a query."""


class MemoryRecallService:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    def recall(self, query: str, *, limit: int = 5) -> list[str]:
        return self._store.search(query, limit=limit)
