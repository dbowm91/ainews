from __future__ import annotations

from enum import Enum


class ThemeParseError(ValueError):
    """Invalid TOML, invalid hex, missing file, file too large."""


class ThemeValidationError(ValueError):
    """Pydantic-style validation failures with field info."""


class ThemeTranslationError(ValueError):
    """Translation rules failure."""


class ThemeContrastError(ValueError):
    """Critical contrast failure."""


class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"
    DERIVED = "derived"
    INFO = "info"


class ThemeDiagnostic:
    __slots__ = ("severity", "field", "message", "code")

    def __init__(self, severity: Severity, field: str, message: str, code: str) -> None:
        self.severity = severity
        self.field = field
        self.message = message
        self.code = code

    def __repr__(self) -> str:
        return f"ThemeDiagnostic(severity={self.severity!r}, field={self.field!r}, message={self.message!r}, code={self.code!r})"
