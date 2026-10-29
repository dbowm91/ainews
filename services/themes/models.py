from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from services.themes.errors import ThemeDiagnostic


class HalloyGeneral(BaseModel):
    model_config = ConfigDict(extra="ignore")

    background: str | None = None
    border: str | None = None
    horizontal_rule: str | None = None
    unread_indicator: str | None = None


class HalloyText(BaseModel):
    model_config = ConfigDict(extra="ignore")

    primary: str | None = None
    secondary: str | None = None
    tertiary: str | None = None
    success: str | None = None
    error: str | None = None


class HalloyBuffer(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: str | None = None
    background: str | None = None
    background_text_input: str | None = None
    background_title_bar: str | None = None
    border: str | None = None
    border_selected: str | None = None
    code: str | None = None
    highlight: str | None = None
    nickname: str | None = None
    selection: str | None = None
    timestamp: str | None = None
    topic: str | None = None
    url: str | None = None


class HalloyButton(BaseModel):
    model_config = ConfigDict(extra="ignore")

    background: str | None = None
    background_hover: str | None = None
    background_selected: str | None = None
    background_selected_hover: str | None = None


class HalloyTheme(BaseModel):
    model_config = ConfigDict(extra="ignore")

    general: HalloyGeneral = Field(default_factory=HalloyGeneral)
    text: HalloyText = Field(default_factory=HalloyText)
    buffer: HalloyBuffer = Field(default_factory=HalloyBuffer)
    buttons_primary: HalloyButton | None = None
    buttons_secondary: HalloyButton | None = None

    def all_color_values(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for prefix, section in [
            ("general", self.general),
            ("text", self.text),
            ("buffer", self.buffer),
        ]:
            for field_name in section.model_fields_set:
                val = getattr(section, field_name)
                if val is not None:
                    result[f"{prefix}.{field_name}"] = val
        if self.buttons_primary is not None:
            for field_name in self.buttons_primary.model_fields:
                val = getattr(self.buttons_primary, field_name)
                if val is not None:
                    result[f"buttons_primary.{field_name}"] = val
        if self.buttons_secondary is not None:
            for field_name in self.buttons_secondary.model_fields:
                val = getattr(self.buttons_secondary, field_name)
                if val is not None:
                    result[f"buttons_secondary.{field_name}"] = val
        return result


class TokenSource(Enum):
    DIRECT = "direct"
    DEFAULTED = "defaulted"
    DERIVED = "derived"


@dataclass(frozen=True)
class TokenProvenance:
    token: str
    source: TokenSource
    source_field: str | None = None


class AinewsTheme(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bg_primary: str
    bg_secondary: str
    bg_tertiary: str
    bg_subtle: str
    bg_input: str
    bg_hover: str
    bg_selected: str

    border: str
    border_light: str
    border_focus: str

    text_primary: str
    text_secondary: str
    text_muted: str
    text_dim: str
    text_inverse: str

    accent: str
    accent_hover: str
    accent_active: str
    accent_contrast: str
    link: str
    link_hover: str
    focus_ring: str

    success: str
    warning: str
    error: str
    info: str

    category_ai: str
    category_privacy: str
    category_security: str
    category_programming: str
    category_hardware: str
    category_other: str

    skeleton_base: str
    skeleton_shine: str
    selection: str
    overlay: str

    appearance: Literal["light", "dark"]


@dataclass(frozen=True)
class ThemeTranslationResult:
    theme: AinewsTheme
    warnings: tuple[ThemeDiagnostic, ...]
    provenance: dict[str, TokenProvenance]
    appearance_source: TokenSource
