"""Small inference backend contract; runtime-specific packages remain worker-only."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class BackendCapabilities:
    voice_design: bool = False
    voice_reference: bool = False
    cfg_scale: bool = False
    languages: tuple[str, ...] = ()
    streaming: bool = False
    sampling: bool = False


class TTSBackend(Protocol):
    name: str
    capabilities: BackendCapabilities

    def load(self, model_id: str, revision: str) -> None: ...
    def synthesize(self, text: str, *, instruction: str, cfg_scale: float) -> tuple[bytes, int]: ...
