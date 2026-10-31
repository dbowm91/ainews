"""Optional, default-off narration services. Importing this package never loads a TTS runtime."""

from .jobs import ensure_narration_job_for_published

__all__ = ["ensure_narration_job_for_published"]
