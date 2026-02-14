"""Signal-level cache with scope+version keying.

Key: (signal_name, scope_hash, query_version) → (SignalResult, timestamp)

If 10 controls require "arm:mg_hierarchy", it's queried once.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from signals.types import SignalResult


def _scope_hash(scope_dict: dict[str, Any]) -> str:
    """Deterministic hash from scope parameters."""
    raw = json.dumps(scope_dict, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class SignalCache:
    """In-memory signal cache with TTL support."""

    def __init__(self, default_ttl: int = 900):
        self._store: dict[str, tuple[SignalResult, float]] = {}
        self._default_ttl = default_ttl
        self.hits = 0
        self.misses = 0

    def _key(self, signal_name: str, scope: dict, version: str = "v1") -> str:
        return f"{signal_name}:{_scope_hash(scope)}:{version}"

    def get(
        self,
        signal_name: str,
        scope: dict,
        version: str = "v1",
        freshness_seconds: int | None = None,
    ) -> SignalResult | None:
        """Return cached result if fresh, else None."""
        key = self._key(signal_name, scope, version)
        entry = self._store.get(key)
        if entry is None:
            self.misses += 1
            return None

        result, ts = entry
        ttl = freshness_seconds if freshness_seconds is not None else self._default_ttl
        if time.time() - ts > ttl:
            self.misses += 1
            del self._store[key]
            return None

        self.hits += 1
        return result

    def put(
        self,
        signal_name: str,
        scope: dict,
        result: SignalResult,
        version: str = "v1",
    ) -> None:
        key = self._key(signal_name, scope, version)
        self._store[key] = (result, time.time())

    def invalidate(self, signal_name: str | None = None) -> int:
        """Clear cache entries. If signal_name given, only that signal; else all."""
        if signal_name is None:
            count = len(self._store)
            self._store.clear()
            return count
        to_del = [k for k in self._store if k.startswith(f"{signal_name}:")]
        for k in to_del:
            del self._store[k]
        return len(to_del)

    @property
    def size(self) -> int:
        return len(self._store)

    def stats(self) -> dict:
        return {
            "entries": self.size,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / max(self.hits + self.misses, 1) * 100, 1),
        }
