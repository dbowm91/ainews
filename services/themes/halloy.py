from __future__ import annotations

import re
import tomllib
import unicodedata
from pathlib import Path

from services.themes.colors import parse_hex_color
from services.themes.errors import ThemeParseError, ThemeValidationError
from services.themes.models import (
    HalloyBuffer,
    HalloyButton,
    HalloyGeneral,
    HalloyText,
    HalloyTheme,
)

MAX_HALLOY_FILE_BYTES = 256 * 1024


def normalize_identifier(stem: str) -> str:
    normalized = unicodedata.normalize("NFKD", stem)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.lower()
    result = re.sub(r"[^a-z0-9]+", "-", lowered)
    result = result.strip("-")
    if not result:
        raise ThemeValidationError(f"Normalized identifier is empty for stem: {stem!r}")
    return result


def _validate_hex_fields(data: dict[str, object], section_path: str, known_keys: set[str] | None = None) -> None:
    for key, value in data.items():
        if known_keys is not None and key not in known_keys:
            continue
        if value is None:
            continue
        if isinstance(value, dict):
            continue
        if not isinstance(value, str):
            raise ThemeValidationError(
                f"Expected string value in {section_path}.{key}, got {type(value).__name__}"
            )
        parse_hex_color(value)


def _extract_button_table(table: dict[str, object]) -> HalloyButton:
    allowed = {"background", "background_hover", "background_selected", "background_selected_hover"}
    for key, value in table.items():
        if key not in allowed:
            continue
        if value is None:
            continue
        if not isinstance(value, str):
            raise ThemeValidationError(
                f"Expected string in button table, got {type(value).__name__} for key {key!r}"
            )
        parse_hex_color(value)
    return HalloyButton.model_validate(table)


def _classify_top_level(data: dict[str, object]) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, dict[str, object]]]:
    general_data: dict[str, object] = {}
    text_data: dict[str, object] = {}
    buffer_data: dict[str, object] = {}
    buttons_tables: dict[str, dict[str, object]] = {}

    for key, value in data.items():
        if not isinstance(value, dict):
            raise ThemeValidationError(f"Top-level key {key!r} must be a table")
        if key == "general":
            general_data = value
        elif key == "text":
            text_data = value
        elif key == "buffer":
            buffer_data = value
        elif key == "buttons":
            for btn_name, btn_data in value.items():
                if isinstance(btn_data, dict):
                    buttons_tables[btn_name] = btn_data

    return general_data, text_data, buffer_data, buttons_tables


def _filter_buffer_scalars(buffer_data: dict[str, object]) -> dict[str, object]:
    return {k: v for k, v in buffer_data.items() if not isinstance(v, dict)}


def parse_halloy_toml(raw: bytes | str) -> HalloyTheme:
    if isinstance(raw, str):
        raw_bytes = raw.encode("utf-8")
    else:
        raw_bytes = raw

    if len(raw_bytes) > MAX_HALLOY_FILE_BYTES:
        raise ThemeParseError(
            f"File too large: {len(raw_bytes)} bytes (max {MAX_HALLOY_FILE_BYTES})"
        )

    if not raw_bytes.strip():
        raise ThemeParseError("Empty TOML content")

    try:
        data = tomllib.loads(raw_bytes.decode("utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ThemeParseError(f"Invalid TOML: {exc}") from exc

    if not isinstance(data, dict):
        raise ThemeParseError("TOML root must be a table (dict)")

    general_data, text_data, buffer_data, buttons_tables = _classify_top_level(data)

    _validate_hex_fields(general_data, "general", set(HalloyGeneral.model_fields.keys()))
    _validate_hex_fields(text_data, "text", set(HalloyText.model_fields.keys()))

    buffer_scalars = _filter_buffer_scalars(buffer_data)
    _validate_hex_fields(buffer_scalars, "buffer", set(HalloyBuffer.model_fields.keys()))

    general_model = HalloyGeneral.model_validate(general_data)
    text_model = HalloyText.model_validate(text_data)
    buffer_model = HalloyBuffer.model_validate(buffer_scalars)

    bp_data = buttons_tables.get("primary")
    bs_data = buttons_tables.get("secondary")

    return HalloyTheme(
        general=general_model,
        text=text_model,
        buffer=buffer_model,
        buttons_primary=_extract_button_table(bp_data) if bp_data is not None else None,
        buttons_secondary=_extract_button_table(bs_data) if bs_data is not None else None,
    )


def load_halloy_theme(path: Path) -> tuple[str, HalloyTheme]:
    file_path = path if path.is_file() else Path(path)
    if not file_path.is_file():
        raise ThemeParseError(f"File not found: {file_path}")

    file_size = file_path.stat().st_size
    if file_size > MAX_HALLOY_FILE_BYTES:
        raise ThemeParseError(
            f"File too large: {file_size} bytes (max {MAX_HALLOY_FILE_BYTES})"
        )

    raw = file_path.read_bytes()
    theme = parse_halloy_toml(raw)
    normalized_id = normalize_identifier(file_path.stem)
    return normalized_id, theme
