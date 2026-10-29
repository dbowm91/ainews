"""Regression tests for the critical CSS build step.

The generator used to split the minified stylesheet on ``}`` and re-emit
exactly one closing brace per fragment. Every adjacent ``}}`` sequence --
the closing brace of a nested block directly following the closing brace of
its last child -- therefore lost one brace. The result was a stylesheet that
was no longer brace-balanced, so the browser truncated it at the first
unbalanced rule and silently discarded every later rule, including the whole
mobile navigation block and the reduced-motion safety net.

These tests assert on the generated artefact, because the defect was in the
generator and the committed output was faithfully reproducing it.
"""

import re
from pathlib import Path

import pytest

from scripts.build_critical_css import (
    CRITICAL_SRC,
    OUTPUT_PATH,
    build_critical_css,
    format_css,
    minify_css,
    split_top_level_rules,
    validate_generated_css,
)

ROOT = Path(__file__).resolve().parent.parent


class TestGeneratedCriticalCss:
    """The generated partial must be structurally identical to its source."""

    def test_generated_critical_css_is_brace_balanced(self):
        generated = build_critical_css()

        assert generated.count("{") == generated.count("}")

    def test_generated_critical_css_preserves_every_brace(self):
        minified = minify_css(CRITICAL_SRC.read_text())
        generated = build_critical_css()

        assert generated.count("{") == minified.count("{")
        assert generated.count("}") == minified.count("}")

    def test_generated_critical_css_matches_source_rule_count(self):
        minified = minify_css(CRITICAL_SRC.read_text())
        generated = build_critical_css()

        assert len(split_top_level_rules(minified)) == len(
            split_top_level_rules(generated)
        )

    def test_generated_critical_css_contains_mobile_media_block(self):
        generated = build_critical_css()

        assert "@media (max-width:640px)" in generated
        # The mobile rule that collapses the navigation.
        assert ".nav-links{display:none" in generated

    def test_generated_critical_css_contains_reduced_motion_block(self):
        generated = build_critical_css()

        assert "@media (prefers-reduced-motion:reduce)" in generated
        assert "animation-duration:0.01ms" in generated

    def test_build_script_is_idempotent(self):
        """The committed partial must match a fresh generation."""
        assert OUTPUT_PATH.read_text() == build_critical_css()

    def test_committed_partial_is_brace_balanced(self):
        committed = OUTPUT_PATH.read_text()

        assert committed.count("{") == committed.count("}")


class TestCssFormatter:
    """Unit tests for the formatter that replaced the brace-dropping one."""

    @pytest.mark.parametrize(
        "source",
        [
            "@keyframes spin{0%{opacity:0}100%{opacity:1}}",
            "@media (min-width:600px){.a{color:red}.b{color:blue}}",
            "@media (prefers-reduced-motion:reduce){*,*::before{opacity:0}}",
            "a{b:c}",
            "a{b:c}d{e:f}",
        ],
    )
    def test_format_css_preserves_brace_counts(self, source):
        formatted = format_css(minify_css(source))

        assert formatted.count("{") == source.count("{")
        assert formatted.count("}") == source.count("}")

    def test_format_css_keeps_nested_rules_intact(self):
        formatted = format_css(minify_css("@media (min-width:600px){.a{color:red}}"))

        assert ".a{color:red" in formatted
        # Two closing braces: one for the rule, one for the media block.
        assert formatted.count("}") == 2

    def test_minify_css_preserves_every_brace(self):
        source = "@keyframes spin{0%{opacity:0}100%{opacity:1}}"

        minified = minify_css(source)

        assert minified.count("{") == source.count("{")
        assert minified.count("}") == source.count("}")

    def test_minify_css_preserves_braces_without_trailing_semicolons(self):
        minified = minify_css("a{color:red;}")

        assert minified == "a{color:red}"

    def test_split_top_level_rules_counts_nested_blocks_once(self):
        rules = split_top_level_rules(
            minify_css("@import url('x.css');@media (min-width:600px){.a{color:red}}")
        )

        assert len(rules) == 2


class TestBuildAssertion:
    """The generator must refuse to write a structurally damaged stylesheet."""

    def test_validate_rejects_unbalanced_output(self):
        with pytest.raises(ValueError, match="brace-balanced"):
            validate_generated_css("a{b:c}", "a{b:c}", "a{b:c")

    def test_validate_rejects_dropped_brace(self):
        with pytest.raises(ValueError, match="number of"):
            validate_generated_css("a{b:c}}", "a{b:c}", "a{b:c }")

    def test_validate_rejects_rule_count_change(self):
        with pytest.raises(ValueError, match="rule count"):
            validate_generated_css("a{b:c};d", "a{b:c};d", "a{b:c }d")

    def test_validate_accepts_balanced_output(self):
        validate_generated_css("a{b:c}", "a{b:c}", "a{b:c }")


class TestCriticalCssSources:
    """The shipped source must not smuggle structure past the build step."""

    def test_critical_css_source_is_balanced(self):
        source = CRITICAL_SRC.read_text()

        assert source.count("{") == source.count("}")

    def test_committed_partial_has_no_import_statement(self):
        """The palette is not imported into the critical sheet any more."""
        committed = OUTPUT_PATH.read_text()

        assert "@import" not in committed

    def test_generated_partial_has_no_at_import(self):
        generated = build_critical_css()

        assert "@import" not in generated

    def test_partial_contains_no_layer_wrapper(self):
        """The layer wrapper is applied where the partial is included."""
        committed = OUTPUT_PATH.read_text()

        assert not re.search(r"@layer", committed)
