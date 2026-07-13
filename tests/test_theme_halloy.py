from __future__ import annotations

from pathlib import Path

import pytest

from services.themes.errors import ThemeParseError, ThemeValidationError
from services.themes.halloy import (
    MAX_HALLOY_FILE_BYTES,
    load_halloy_theme,
    normalize_identifier,
    parse_halloy_toml,
)
from services.themes.models import HalloyTheme


def _toml(s: str) -> bytes:
    return s.encode("utf-8")


CATPPUCCIN_MOCHA = """\
[general]
background = "#11111B"
border = "#6C7086"
horizontal_rule = "#1E1E2E"
unread_indicator = "#CBA6F7"

[text]
primary = "#CDD6F4"
secondary = "#A6ADC8"
tertiary = "#CBA6F7"
success = "#A6E3A1"
error = "#F38BA8"

[buffer]
action = "#FAB387"
background = "#181825"
background_text_input = "#1E1E2E"
background_title_bar = "#1E1E2E"
border = "#11111B"
border_selected = "#4C4163"
code = "#B7BDF8"
highlight = "#594C76"
nickname = "#89DCEB"
selection = "#2C324A"
timestamp = "#585A6E"
topic = "#7F849C"
url = "#89B4FA"

  [buffer.server_messages]
  default = "#F9E2AF"

[buttons.primary]
background = "#00000000"
background_hover = "#1A1A29"
background_selected = "#1E1E2F"
background_selected_hover = "#222236"

[buttons.secondary]
background = "#232336"
background_hover = "#2B2B42"
background_selected = "#4C4163"
background_selected_hover = "#685786"
"""


class TestParseHalloyToml:
    def test_full_valid_file(self) -> None:
        theme = parse_halloy_toml(_toml(CATPPUCCIN_MOCHA))
        assert isinstance(theme, HalloyTheme)
        assert theme.general.background == "#11111B"
        assert theme.text.primary == "#CDD6F4"
        assert theme.buffer.background == "#181825"
        assert theme.buttons_primary is not None
        assert theme.buttons_primary.background_hover == "#1A1A29"
        assert theme.buttons_secondary is not None
        assert theme.buttons_secondary.background == "#232336"

    def test_minimal_valid_file(self) -> None:
        toml = '[general]\nbackground = "#FF0000"\n'
        theme = parse_halloy_toml(_toml(toml))
        assert theme.general.background == "#FF0000"
        assert theme.text.primary is None
        assert theme.buffer.background is None

    def test_unknown_sections_ignored(self) -> None:
        toml = '[general]\nbackground = "#000000"\n\n[foo]\nbar = "baz"\n'
        theme = parse_halloy_toml(_toml(toml))
        assert theme.general.background == "#000000"

    def test_unknown_keys_ignored(self) -> None:
        toml = '[general]\nbackground = "#ABCDEF"\nunknown_key = "value"\n'
        theme = parse_halloy_toml(_toml(toml))
        assert theme.general.background == "#ABCDEF"

    def test_missing_optional_sections(self) -> None:
        toml = '[general]\nbackground = "#112233"\n'
        theme = parse_halloy_toml(_toml(toml))
        assert theme.text.primary is None
        assert theme.buffer.background is None
        assert theme.buttons_primary is None

    def test_buttons_primary_and_secondary(self) -> None:
        toml = """\
[general]
background = "#000000"

[buttons.primary]
background = "#111111"
background_hover = "#222222"

[buttons.secondary]
background = "#333333"
background_hover = "#444444"
"""
        theme = parse_halloy_toml(_toml(toml))
        assert theme.buttons_primary is not None
        assert theme.buttons_primary.background == "#111111"
        assert theme.buttons_secondary is not None
        assert theme.buttons_secondary.background == "#333333"

    def test_server_messages_excluded_from_buffer(self) -> None:
        theme = parse_halloy_toml(_toml(CATPPUCCIN_MOCHA))
        assert theme.buffer.background == "#181825"
        assert theme.buffer.timestamp == "#585A6E"
        assert not hasattr(theme.buffer, "server_messages")

    def test_six_digit_colors(self) -> None:
        toml = '[general]\nbackground = "#112233"\n'
        theme = parse_halloy_toml(_toml(toml))
        assert theme.general.background == "#112233"

    def test_eight_digit_colors(self) -> None:
        toml = '[general]\nbackground = "#11223344"\n'
        theme = parse_halloy_toml(_toml(toml))
        assert theme.general.background == "#11223344"

    def test_uppercase_hex_normalized(self) -> None:
        toml = '[general]\nbackground = "#AABBCC"\n'
        theme = parse_halloy_toml(_toml(toml))
        assert theme.general.background == "#AABBCC"

    def test_invalid_hex_raises(self) -> None:
        toml = '[general]\nbackground = "#GGG"\n'
        with pytest.raises(ThemeParseError):
            parse_halloy_toml(_toml(toml))

    def test_non_string_value_raises(self) -> None:
        toml = "[general]\nbackground = 12345\n"
        with pytest.raises(ThemeValidationError, match="Expected string"):
            parse_halloy_toml(_toml(toml))

    def test_empty_file_raises(self) -> None:
        with pytest.raises(ThemeParseError, match="Empty TOML"):
            parse_halloy_toml(b"")

    def test_invalid_toml_raises(self) -> None:
        with pytest.raises(ThemeParseError, match="Invalid TOML"):
            parse_halloy_toml(b"[[[")

    def test_file_too_large(self) -> None:
        # Build valid TOML large enough to exceed the limit
        section_blocks = []
        for i in range(20000):
            section_blocks.append(f'[section{i}]\nkey = "#{i:06x}"')
        large = "[general]\n" + 'background = "#000000"\n' + "\n".join(section_blocks)
        raw = large.encode("utf-8")
        assert len(raw) > MAX_HALLOY_FILE_BYTES
        with pytest.raises(ThemeParseError, match="too large"):
            parse_halloy_toml(raw)

    def test_empty_after_strip(self) -> None:
        with pytest.raises(ThemeParseError, match="Empty TOML"):
            parse_halloy_toml(b"   \n  \n  ")

    def test_multiple_buttons_prefers_primary(self) -> None:
        toml = """\
[general]
background = "#000000"

[buttons.primary]
background = "#AAAAAA"

[buttons.secondary]
background = "#BBBBBB"

[buttons.tertiary]
background = "#CCCCCC"
"""
        theme = parse_halloy_toml(_toml(toml))
        assert theme.buttons_primary is not None
        assert theme.buttons_primary.background == "#AAAAAA"
        assert theme.buttons_secondary is not None
        assert theme.buttons_secondary.background == "#BBBBBB"


class TestNormalizeIdentifier:
    def test_catppuccin_mocha(self) -> None:
        assert normalize_identifier("Catppuccin Mocha") == "catppuccin-mocha"

    def test_accents_stripped(self) -> None:
        result = normalize_identifier("Caf\u00e9")
        assert result == "cafe"

    def test_leading_trailing_dashes_stripped(self) -> None:
        result = normalize_identifier("--Hello--World--")
        assert result == "hello-world"

    def test_multiple_separators(self) -> None:
        result = normalize_identifier("My   Cool   Theme")
        assert result == "my-cool-theme"

    def test_empty_input_raises(self) -> None:
        with pytest.raises(ThemeValidationError, match="empty"):
            normalize_identifier("")

    def test_only_non_ascii_raises(self) -> None:
        with pytest.raises(ThemeValidationError, match="empty"):
            normalize_identifier("\u6f22\u5b57")

    def test_numbers_preserved(self) -> None:
        assert normalize_identifier("theme123") == "theme123"

    def test_special_chars_replaced(self) -> None:
        result = normalize_identifier("theme@#$%name")
        assert result == "theme-name"


class TestLoadHalloyTheme:
    def test_load_from_path(self, tmp_path: Path) -> None:
        theme_file = tmp_path / "Test Theme.toml"
        theme_file.write_text(CATPPUCCIN_MOCHA)
        normalized_id, theme = load_halloy_theme(theme_file)
        assert normalized_id == "test-theme"
        assert theme.general.background == "#11111B"

    def test_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(ThemeParseError, match="not found"):
            load_halloy_theme(tmp_path / "missing.toml")

    def test_file_too_large(self, tmp_path: Path) -> None:
        theme_file = tmp_path / "big.toml"
        # Generate valid TOML that exceeds the limit
        lines = ["[general]", 'background = "#000000"']
        for i in range(20000):
            lines.append(f"[unknown{i}]")
            lines.append(f'key = "#{i:06x}"')
        content = "\n".join(lines)
        theme_file.write_text(content)
        with pytest.raises(ThemeParseError, match="too large"):
            load_halloy_theme(theme_file)
