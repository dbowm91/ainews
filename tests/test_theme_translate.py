from __future__ import annotations

import re

import pytest

from services.themes.errors import ThemeContrastError, Severity
from services.themes.halloy import parse_halloy_toml
from services.themes.models import (
    AinewsTheme,
    HalloyTheme,
    ThemeTranslationResult,
    TokenSource,
)
from services.themes.translate import (
    classify_contrast_findings,
    detect_appearance,
    to_css_variables,
    translate_theme,
)


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

CATPPUCCIN_LATTE = """\
[general]
background = "#DCE0E8"
border = "#9CA0B0"
horizontal_rule = "#CCD0DA"
unread_indicator = "#8839EF"

[text]
primary = "#4C4F69"
secondary = "#6C6F85"
tertiary = "#8839EF"
success = "#40A02B"
error = "#D20F39"

[buffer]
action = "#FE640B"
background = "#E6E9EF"
background_text_input = "#EFF1F5"
background_title_bar = "#EFF1F5"
border = "#DCE0E8"
border_selected = "#CCB8EF"
code = "#7287FD"
highlight = "#D5C9EF"
nickname = "#04A5E5"
selection = "#B5CCF5"
timestamp = "#9EA1B6"
topic = "#8C8FA1"
url = "#1E66F5"

  [buffer.server_messages]
  default = "#DF8E1D"

[buttons.primary]
background = "#00000000"
background_hover = "#D6D9E1"
background_selected = "#C1C4CA"
background_selected_hover = "#B7BAC0"

[buttons.secondary]
background = "#E3E7ED"
background_hover = "#D5D9DE"
background_selected = "#D4C8EF"
background_selected_hover = "#C2A4EF"
"""

FERRA_LIGHT = """\
[general]
background = "#F4ECE6"
border = "#DDD0C8"
horizontal_rule = "#E9D9CE"
unread_indicator = "#FFA07A"

[text]
primary = "#685650"
secondary = "#A79891"
tertiary = "#A352C5"
success = "#74862D"
error = "#DF525E"

[buffer]
action = "#74862D"
background = "#F1E6DE"
background_text_input = "#EEE0D5"
background_title_bar = "#EFE2D8"
border = "#00000000"
border_selected = "#C7B9B1"
code = "#A352C5"
highlight = "#F4D6C7"
nickname = "#C4486C"
selection = "#E6C6C3"
timestamp = "#AE9D95"
topic = "#AB8A79"
url = "#6360D6"

  [buffer.server_messages]
  default = "#C19317"

[buttons.primary]
background = "#F4ECE6"
background_hover = "#F1E5DD"
background_selected = "#EADAD0"
background_selected_hover = "#E6D5C9"

[buttons.secondary]
background = "#E9D5C8"
background_hover = "#DFC2AD"
background_selected = "#D9D1BB"
background_selected_hover = "#C9C5A7"
"""

BLACK_HIGHLIGHTS = """\
[general]
background = "#242424"
border = "#575757"
horizontal_rule = "#414141"
unread_indicator = "#777777"

[text]
primary = "#D0D0D0"
secondary = "#8F8F8F"
tertiary = "#ADADAD"
success = "#9B9B9B"
error = "#9B9B9B"

[buffer]
action = "#B5B5B5"
background = "#0D0D0D"
background_text_input = "#202020"
background_title_bar = "#313131"
border = "#000000"
border_selected = "#7F7F7F"
code = "#EAEAEA"
highlight = "#084A60"
nickname = "#A5A5A5"
selection = "#3C3C3C"
timestamp = "#676767"
topic = "#B5B5B5"
url = "#FFFFFF"

  [buffer.server_messages]
  default = "#B5B5B5"

[buttons.primary]
background = "#242424"
background_hover = "#1B1B1B"
background_selected = "#111111"
background_selected_hover = "#000000"

[buttons.secondary]
background = "#242424"
background_hover = "#414141"
background_selected = "#575757"
background_selected_hover = "#6F6F6F"
"""

CYBERPUNK = """\
[general]
background = "#0A0E14"
border = "#2E3C49"
horizontal_rule = "#1B1F27"
unread_indicator = "#00FFD9"

[text]
primary = "#39FF14"
secondary = "#00BFFF"
tertiary = "#FF00FF"
success = "#00FF9D"
error = "#FF4C4C"

[buffer]
action = "#00FF99"
background = "#0D0F14"
background_text_input = "#11151C"
background_title_bar = "#1B1F27"
border = "#00000000"
border_selected = "#00FFD9"
code = "#39FF14"
highlight = "#8B008B"
nickname = "#FF00FF"
selection = "#1A1E25"
timestamp = "#60708B"
topic = "#00BFFF"
url = "#00BFFF"

  [buffer.server_messages]
  default = "#FFD700"

[buttons.primary]
background = "#0A0E14"
background_hover = "#1D232F"
background_selected = "#0D1218"
background_selected_hover = "#141A21"

[buttons.secondary]
background = "#1B1F27"
background_hover = "#242A33"
background_selected = "#2E3C49"
background_selected_hover = "#394554"
"""


def _parse_fixture(toml_str: str) -> HalloyTheme:
    return parse_halloy_toml(_toml(toml_str))


class TestDetectAppearance:
    def test_dark_theme(self) -> None:
        theme = _parse_fixture(CATPPUCCIN_MOCHA)
        appearance, source = detect_appearance(theme)
        assert appearance == "dark"
        assert source == TokenSource.DIRECT

    def test_light_theme(self) -> None:
        theme = _parse_fixture(CATPPUCCIN_LATTE)
        appearance, source = detect_appearance(theme)
        assert appearance == "light"
        assert source == TokenSource.DIRECT

    def test_light_ferra(self) -> None:
        theme = _parse_fixture(FERRA_LIGHT)
        appearance, _ = detect_appearance(theme)
        assert appearance == "light"

    def test_dark_cyberpunk(self) -> None:
        theme = _parse_fixture(CYBERPUNK)
        appearance, _ = detect_appearance(theme)
        assert appearance == "dark"

    def test_dark_black_highlights(self) -> None:
        theme = _parse_fixture(BLACK_HIGHLIGHTS)
        appearance, _ = detect_appearance(theme)
        assert appearance == "dark"

    def test_fallback_to_buffer_background(self) -> None:
        theme = HalloyTheme()
        theme.buffer.background = "#E6E9EF"
        appearance, source = detect_appearance(theme)
        assert appearance == "light"
        assert source == TokenSource.DERIVED

    def test_no_background_raises(self) -> None:
        theme = HalloyTheme()
        with pytest.raises(Exception):
            detect_appearance(theme)


class TestTranslateTheme:
    def test_produces_complete_theme(self) -> None:
        result = translate_theme(_parse_fixture(CATPPUCCIN_MOCHA))
        assert isinstance(result, ThemeTranslationResult)
        assert isinstance(result.theme, AinewsTheme)
        assert result.theme.appearance == "dark"

    def test_all_fields_are_hex(self) -> None:
        result = translate_theme(_parse_fixture(CATPPUCCIN_MOCHA))
        theme = result.theme
        hex_fields = [
            "bg_primary", "bg_secondary", "bg_tertiary", "bg_subtle",
            "bg_input", "bg_hover", "bg_selected",
            "border", "border_light", "border_focus",
            "text_primary", "text_secondary", "text_muted", "text_dim", "text_inverse",
            "accent", "accent_hover", "accent_active", "link", "link_hover", "focus_ring",
            "success", "warning", "error", "info",
            "category_ai", "category_privacy", "category_security",
            "category_programming", "category_hardware", "category_other",
            "skeleton_base", "skeleton_shine", "selection", "overlay",
        ]
        for field in hex_fields:
            val = getattr(theme, field)
            assert isinstance(val, str), f"{field} is not a string"
            assert val.startswith("#"), f"{field}={val} does not start with #"

    def test_direct_mapping_text_primary(self) -> None:
        result = translate_theme(_parse_fixture(CATPPUCCIN_MOCHA))
        assert result.theme.text_primary == "#cdd6f4"

    def test_direct_mapping_bg_primary(self) -> None:
        result = translate_theme(_parse_fixture(CATPPUCCIN_MOCHA))
        assert result.theme.bg_primary == "#11111b"

    def test_direct_mapping_accent(self) -> None:
        result = translate_theme(_parse_fixture(CATPPUCCIN_MOCHA))
        assert result.theme.accent == "#89b4fa"

    def test_derived_text_inverse(self) -> None:
        result = translate_theme(_parse_fixture(CATPPUCCIN_MOCHA))
        assert result.theme.text_inverse != result.theme.text_primary

    def test_light_appearance_latte(self) -> None:
        result = translate_theme(_parse_fixture(CATPPUCCIN_LATTE))
        assert result.theme.appearance == "light"

    def test_dark_appearance_mocha(self) -> None:
        result = translate_theme(_parse_fixture(CATPPUCCIN_MOCHA))
        assert result.theme.appearance == "dark"

    def test_provenance_populated(self) -> None:
        result = translate_theme(_parse_fixture(CATPPUCCIN_MOCHA))
        assert len(result.provenance) > 0
        assert "bg_primary" in result.provenance
        assert result.provenance["bg_primary"].source == TokenSource.DIRECT

    def test_warnings_contain_diagnostics(self) -> None:
        result = translate_theme(_parse_fixture(CATPPUCCIN_MOCHA))
        assert isinstance(result.warnings, tuple)
        for w in result.warnings:
            assert hasattr(w, "severity")
            assert hasattr(w, "field")
            assert hasattr(w, "code")

    def test_five_fixtures_translate(self) -> None:
        for fixture in [CATPPUCCIN_MOCHA, CATPPUCCIN_LATTE, FERRA_LIGHT, BLACK_HIGHLIGHTS, CYBERPUNK]:
            result = translate_theme(_parse_fixture(fixture))
            assert isinstance(result.theme, AinewsTheme)


class TestCssVariables:
    def test_contains_root_block(self) -> None:
        result = translate_theme(_parse_fixture(CATPPUCCIN_MOCHA))
        css = to_css_variables(result.theme)
        assert css.startswith(":root {")
        assert css.endswith("}")

    def test_deterministic_output(self) -> None:
        result = translate_theme(_parse_fixture(CATPPUCCIN_MOCHA))
        css1 = to_css_variables(result.theme)
        css2 = to_css_variables(result.theme)
        assert css1 == css2

    def test_contains_required_palette_variables(self) -> None:
        result = translate_theme(_parse_fixture(CATPPUCCIN_MOCHA))
        css = to_css_variables(result.theme)
        required_vars = [
            "--bg-primary", "--bg-secondary", "--bg-tertiary", "--bg-subtle",
            "--bg-input", "--bg-hover", "--bg-selected",
            "--border", "--border-light", "--border-focus",
            "--text-primary", "--text-secondary", "--text-muted", "--text-dim", "--text-inverse",
            "--accent", "--accent-hover", "--accent-active",
            "--link", "--link-hover", "--focus-ring",
            "--success", "--warning", "--error", "--info",
            "--category-ai", "--category-privacy", "--category-security",
            "--category-programming", "--category-hardware", "--category-other",
            "--skeleton-base", "--skeleton-shine", "--selection", "--overlay",
        ]
        for var in required_vars:
            assert var in css, f"Missing required variable: {var}"

    def test_contains_alpha_variants(self) -> None:
        result = translate_theme(_parse_fixture(CATPPUCCIN_MOCHA))
        css = to_css_variables(result.theme)
        alpha_vars = [
            "--accent-alpha-08", "--accent-alpha-10", "--accent-alpha-25",
            "--green-alpha-10", "--green-alpha-15", "--green-alpha-25",
            "--orange-alpha-10", "--orange-alpha-15", "--orange-alpha-25",
            "--red-alpha-08", "--red-alpha-10", "--red-alpha-15", "--red-alpha-25",
            "--purple-alpha-10", "--purple-alpha-25",
            "--category-ai-alpha-15", "--category-ai-alpha-40",
            "--category-privacy-alpha-15", "--category-privacy-alpha-40",
            "--category-security-alpha-15", "--category-security-alpha-40",
            "--category-programming-alpha-15", "--category-programming-alpha-40",
            "--category-hardware-alpha-15", "--category-hardware-alpha-40",
        ]
        for var in alpha_vars:
            assert var in css, f"Missing alpha variable: {var}"

    def test_alpha_uses_rgba_format(self) -> None:
        result = translate_theme(_parse_fixture(CATPPUCCIN_MOCHA))
        css = to_css_variables(result.theme)
        rgba_pattern = re.compile(r"rgba\(\d+,\d+,\d+,\d+\.\d+\)")
        matches = rgba_pattern.findall(css)
        assert len(matches) == 25

    def test_alpha_values_match_variables_css_contract(self) -> None:
        result = translate_theme(_parse_fixture(CATPPUCCIN_MOCHA))
        css = to_css_variables(result.theme)
        expected_alphas = {
            "--accent-alpha-08": "0.0800",
            "--accent-alpha-10": "0.1000",
            "--accent-alpha-25": "0.2500",
            "--green-alpha-10": "0.1000",
            "--green-alpha-15": "0.1500",
            "--green-alpha-25": "0.2500",
            "--orange-alpha-10": "0.1000",
            "--orange-alpha-15": "0.1500",
            "--orange-alpha-25": "0.2500",
            "--red-alpha-08": "0.0800",
            "--red-alpha-10": "0.1000",
            "--red-alpha-15": "0.1500",
            "--red-alpha-25": "0.2500",
            "--purple-alpha-10": "0.1000",
            "--purple-alpha-25": "0.2500",
            "--category-ai-alpha-15": "0.1500",
            "--category-ai-alpha-40": "0.4000",
            "--category-privacy-alpha-15": "0.1500",
            "--category-privacy-alpha-40": "0.4000",
            "--category-security-alpha-15": "0.1500",
            "--category-security-alpha-40": "0.4000",
            "--category-programming-alpha-15": "0.1500",
            "--category-programming-alpha-40": "0.4000",
            "--category-hardware-alpha-15": "0.1500",
            "--category-hardware-alpha-40": "0.4000",
        }
        for var, alpha in expected_alphas.items():
            pattern = rf"{re.escape(var)}: rgba\(\d+,\d+,\d+,{re.escape(alpha)}\);"
            assert re.search(pattern, css), f"Missing or wrong alpha for {var} (expected {alpha})"

    def test_byte_stable(self) -> None:
        result = translate_theme(_parse_fixture(CATPPUCCIN_MOCHA))
        css1 = to_css_variables(result.theme)
        css2 = to_css_variables(result.theme)
        assert css1.encode() == css2.encode()

    def test_two_space_indent(self) -> None:
        result = translate_theme(_parse_fixture(CATPPUCCIN_MOCHA))
        css = to_css_variables(result.theme)
        lines = css.strip().split("\n")
        assert lines[0] == ":root {"
        for line in lines[1:-1]:
            assert line.startswith("  --"), f"Bad indent: {line}"

    def test_variable_order(self) -> None:
        result = translate_theme(_parse_fixture(CATPPUCCIN_MOCHA))
        css = to_css_variables(result.theme)
        lines = [l.strip() for l in css.strip().split("\n") if l.strip().startswith("--")]
        assert lines[0] == "--bg-primary: #11111b;"
        assert lines[1] == "--bg-secondary: #181825;"
        assert lines[2] == "--bg-tertiary: #1e1e2e;"


class TestContrastFindings:
    def test_dark_theme_no_critical(self) -> None:
        result = translate_theme(_parse_fixture(CATPPUCCIN_MOCHA))
        errors = [w for w in result.warnings if w.severity == Severity.ERROR]
        assert len(errors) == 0

    def test_light_theme_no_critical(self) -> None:
        result = translate_theme(_parse_fixture(CATPPUCCIN_LATTE))
        errors = [w for w in result.warnings if w.severity == Severity.ERROR]
        assert len(errors) == 0

    def test_classify_contrast(self) -> None:
        result = translate_theme(_parse_fixture(CATPPUCCIN_MOCHA))
        findings = classify_contrast_findings(result.theme)
        for f in findings:
            assert f.severity in (Severity.ERROR, Severity.WARNING)
            assert f.code.startswith("contrast.")


class TestCriticalContrastFailure:
    def test_raises_on_critical_contrast(self) -> None:
        toml = """\
[general]
background = "#FFFFFF"
border = "#CCCCCC"

[text]
primary = "#EEEEEE"
secondary = "#999999"
tertiary = "#FF0000"
success = "#00FF00"
error = "#FF0000"

[buffer]
action = "#FFFF00"
background = "#FFFFFF"
background_text_input = "#F5F5F5"
background_title_bar = "#F0F0F0"
border = "#CCCCCC"
border_selected = "#AAAAAA"
code = "#000000"
highlight = "#E0E0E0"
nickname = "#0000FF"
selection = "#D0D0D0"
timestamp = "#888888"
topic = "#777777"
url = "#0000EE"
"""
        with pytest.raises(ThemeContrastError):
            translate_theme(_parse_fixture(toml))
