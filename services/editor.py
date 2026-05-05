import json
import logging

from utils.text import esc_xml_attr, esc_xml_text

logger = logging.getLogger(__name__)


def get_editor_system_prompt(article=None) -> str:
    """Get editor system prompt, optionally using experiment variant.

    Args:
        article: Optional article object with experiment_group attribute.
                 If provided and experiment_group is set, uses the variant prompt.
    """
    from schemas.pipeline import get_config, get_role_config
    from services.prompts import get_system_prompt

    rc = get_role_config("editor")
    config = get_config()

    # Check for experiment variant
    if article and hasattr(article, 'experiment_group') and article.experiment_group:
        experiments = config.get("experiments", {})
        if experiments.get("enabled", False):
            prompt_variants = experiments.get("prompt_variants", {})
            editor_variants = prompt_variants.get("editor", {})
            variant_prompt = editor_variants.get(article.experiment_group)
            if variant_prompt:
                return get_system_prompt("editor", variant_prompt)

    return get_system_prompt("editor", rc.system_prompt)


def build_editor_prompt(
    draft_json: str,
    research_brief: str,
    existing_tags: list[str] | None = None,
    max_tags: int = 3,
) -> str:
    try:
        draft = json.loads(draft_json)
        brief = json.loads(research_brief)
    except (json.JSONDecodeError, TypeError):
        draft = draft_json
        brief = research_brief

    parts = []

    if isinstance(draft, dict):
        parts.append("<draft_article>")
        parts.append(
            f"  <headline>{esc_xml_text(draft.get('headline', ''))}</headline>",
        )
        parts.append(f"  <tldr>{esc_xml_text(draft.get('tldr', ''))}</tldr>")
        parts.append(
            f"  <why_it_matters>{esc_xml_text(draft.get('why_it_matters', ''))}</why_it_matters>",
        )
        parts.append(f"  <body>\n{esc_xml_text(draft.get('body', ''))}\n  </body>")
        if draft.get("key_points"):
            parts.append("  <key_points>")
            for kp in draft["key_points"]:
                parts.append(f"    <point>{esc_xml_text(kp)}</point>")
            parts.append("  </key_points>")
        parts.append(
            f"  <what_to_watch>{esc_xml_text(draft.get('what_to_watch', ''))}</what_to_watch>",
        )
        if draft.get("citations"):
            parts.append("  <citations>")
            for c in draft["citations"]:
                parts.append(
                    f"    <citation title='{esc_xml_attr(c.get('title', ''))}' "
                    f"url='{esc_xml_attr(c.get('url', ''))}' />",
                )
            parts.append("  </citations>")
        parts.append("</draft_article>")
    else:
        parts.append(f"<draft_article>\n{esc_xml_text(draft)}\n</draft_article>")

    parts.append("")

    if isinstance(brief, dict):
        parts.append("<research_brief>")
        parts.append(
            f"  <source_summary>{esc_xml_text(brief.get('source_summary', ''))}</source_summary>",
        )
        if brief.get("key_claims"):
            parts.append("  <key_claims>")
            for kc in brief["key_claims"]:
                parts.append(
                    f"    <claim "
                    f"source='{esc_xml_attr(kc.get('source', ''))}' "
                    f"confidence='{esc_xml_attr(kc.get('confidence', ''))}'>"
                    f"{esc_xml_text(kc.get('claim', ''))}</claim>",
                )
            parts.append("  </key_claims>")
        if brief.get("direct_quotes"):
            parts.append("  <quotes>")
            for q in brief["direct_quotes"]:
                parts.append(
                    f'    <quote attribution="{esc_xml_attr(q.get("attribution", ""))}">'
                    f"{esc_xml_text(q.get('quote', ''))}</quote>",
                )
            parts.append("  </quotes>")
        parts.append("</research_brief>")
    else:
        parts.append(f"<research_brief>\n{esc_xml_text(brief)}\n</research_brief>")

    parts.append("")

    # Tagging section
    tag_str = (
        ", ".join(existing_tags)
        if existing_tags
        else "(none yet — this is a fresh install)"
    )
    parts.append(f"<existing_tags>{esc_xml_text(tag_str)}</existing_tags>")
    parts.append(
        f"Assign 1-{max_tags} tags. Use existing tags if they fit, otherwise create new ones. "
        "Tags must be lowercase, alphanumeric with hyphens (e.g., 'machine-learning', 'zero-day').",
    )
    parts.append("")

    parts.append(
        "Review and improve this draft. Return the corrected version in the same format. "
        "Preserve the headline unless it needs fixing. Fix factual errors, "
        "missing attributions, and clarity issues. "
        "Ensure 'why_it_matters' and 'what_to_watch' sections are present and sharp.",
    )

    return "\n".join(parts)


def build_editor_prompt_with_context(
    draft_json: str,
    research_brief: str,
    existing_tags: list[str] | None = None,
    max_tags: int = 3,
    contextualization: str = "",
) -> str:
    base_prompt = build_editor_prompt(
        draft_json=draft_json,
        research_brief=research_brief,
        existing_tags=existing_tags,
        max_tags=max_tags,
    )

    if contextualization:
        base_prompt += "\n\n<contextualization>\n"
        base_prompt += esc_xml_text(contextualization)
        base_prompt += "\n</contextualization>\n"
        base_prompt += (
            "\nUse this contextualization to identify gaps in the draft, "
            "missing attribution, and claims that need additional support."
        )

    return base_prompt
