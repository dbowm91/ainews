"""Shared cache mixin for in-memory LRU eviction."""

import time

_MAX_MEMORY_ENTRIES = 500


class MemoryCacheMixin:
    """Mixin providing LRU eviction for in-memory cache dicts.

    Subclasses must define `self._memory` as a dict of
    `str -> (expires_at: float, value)` tuples.
    """

    _memory: dict

    def _evict_stale(self) -> None:
        if len(self._memory) <= _MAX_MEMORY_ENTRIES:
            return
        now = time.monotonic()
        expired = [k for k, (exp, _) in self._memory.items() if now >= exp]
        for k in expired:
            del self._memory[k]
        if len(self._memory) > _MAX_MEMORY_ENTRIES:
            sorted_items = sorted(self._memory.items(), key=lambda x: x[1][0])
            for k, _ in sorted_items[: len(self._memory) - _MAX_MEMORY_ENTRIES]:
                del self._memory[k]
