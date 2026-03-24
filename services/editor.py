import logging
import json

logger = logging.getLogger(__name__)

DEFAULT_EDITOR_SYSTEM_PROMPT = (
    "You are a meticulous editor for a tech news publication that values "
    "brevity, clarity, and accuracy. Review the draft and improve it.\n\n"
    "EDITORIAL CHECKLIST:\n"
    "1. Factual accuracy — verify claims against the research brief.\n"
    "2. Attribution — ensure all quotes and claims have proper sources.\n"
    "3. Clarity — fix awkward phrasing, unclear sentences, jargon without explanation.\n"
    "4. Completeness — add missing context if obvious from the brief.\n"
    "5. Tone — professional, neutral, developer-friendly. No hype.\n"
    "6. Brevity — cut any sentence that doesn't earn its place.\n"
    "   Every word must inform. If it doesn't add signal, delete it.\n"
    "7. Structure — ensure the Smart Brevity format is followed:\n"
    "   headline → tldr → why it matters → body → what to watch.\n"
    "8. Tags — assign 1-3 concise tags describing the article's specific topics.\n\n"
    "Return the FULL corrected article in the same JSON schema format. "
    "Preserve all citations and attributions. Fix any issues you find."
)


def get_editor_system_prompt() -> str:
    from schemas.pipeline import get_role_config
    rc = get_role_config("editor")
    if rc.system_prompt:
        return rc.system_prompt
    return DEFAULT_EDITOR_SYSTEM_PROMPT


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
        parts.append("DRAFT ARTICLE:")
        parts.append(f"  HEADLINE: {draft.get('headline', '')}")
        parts.append(f"  TL;DR: {draft.get('tldr', '')}")
        parts.append(f"  WHY IT MATTERS: {draft.get('why_it_matters', '')}")
        parts.append(f"  BODY:\n{draft.get('body', '')}")
        if draft.get("key_points"):
            parts.append("  KEY POINTS:")
            for kp in draft["key_points"]:
                parts.append(f"  - {kp}")
        parts.append(f"  WHAT TO WATCH: {draft.get('what_to_watch', '')}")
        if draft.get("citations"):
            parts.append("  CITATIONS:")
            for c in draft["citations"]:
                parts.append(f"  - {c.get('title', '')}: {c.get('url', '')}")
    else:
        parts.append(f"DRAFT ARTICLE:\n{draft}")

    parts.append("")

    if isinstance(brief, dict):
        parts.append("RESEARCH BRIEF (for fact-checking):")
        parts.append(f"  SOURCE SUMMARY: {brief.get('source_summary', '')}")
        if brief.get("key_claims"):
            parts.append("  KEY CLAIMS:")
            for kc in brief["key_claims"]:
                parts.append(f"  - {kc.get('claim', '')} [{kc.get('source', '')}] (confidence: {kc.get('confidence', '')})")
        if brief.get("direct_quotes"):
            parts.append("  QUOTES:")
            for q in brief["direct_quotes"]:
                parts.append(f"  - \"{q.get('quote', '')}\" — {q.get('attribution', '')}")
    else:
        parts.append(f"RESEARCH BRIEF:\n{brief}")

    parts.append("")

    # Tagging section
    tag_str = ", ".join(existing_tags) if existing_tags else "(none yet — this is a fresh install)"
    parts.append(f"EXISTING TAGS IN OUR SYSTEM: {tag_str}")
    parts.append(f"Assign 1-{max_tags} tags. Use existing tags if they fit, otherwise create new ones.")
    parts.append("Tags must be lowercase, alphanumeric with hyphens (e.g., 'machine-learning', 'zero-day').")
    parts.append("")

    parts.append(
        "Review and improve this draft. Return the corrected version in the same format. "
        "Preserve the headline unless it needs fixing. Fix factual errors, "
        "missing attributions, and clarity issues. "
        "Ensure 'why_it_matters' and 'what_to_watch' sections are present and sharp."
    )

    return "\n".join(parts)
