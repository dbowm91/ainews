"""Deterministic CPU-only fake used by protocol and encoder integration tests."""
from __future__ import annotations

import hashlib
import math
import struct
import wave
from io import BytesIO


class FakeBackend:
    name = "fake-cpu"

    def load(self, model_id: str = "fake", revision: str = "test") -> None:
        self.loaded = True

    def synthesize(self, text: str, *, instruction: str = "", cfg_scale: float = 4.0) -> tuple[bytes, int]:
        if not getattr(self, "loaded", False):
            raise RuntimeError("fake backend is not loaded")
        seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:4], "big")
        sample_rate, seconds = 24_000, min(max(len(text) / 90, 0.2), 4.0)
        out = BytesIO()
        with wave.open(out, "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(sample_rate)
            frames = bytearray()
            for index in range(int(sample_rate * seconds)):
                value = int(5000 * math.sin(2 * math.pi * (180 + seed % 100) * index / sample_rate))
                frames.extend(struct.pack("<h", value))
            wav.writeframes(frames)
        return out.getvalue(), sample_rate
