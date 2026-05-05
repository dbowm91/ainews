from __future__ import annotations

import re


_MARKDOWN_JSON_RE = re.compile(r'```(?:json)?\s*([\s\S]+?)\s*```', re.MULTILINE)
_BRACE_JSON_RE = re.compile(r'\{[\s\S]*\}')


def extract_json(raw: str) -> str:
    """Extract JSON from response that may contain markdown."""
    import json as json_mod
    raw = raw.strip()
    if not raw:
        raise ValueError("LLM returned empty response")

    try:
        json_mod.loads(raw)
        return raw
    except json_mod.JSONDecodeError:
        pass

    match = _MARKDOWN_JSON_RE.search(raw)
    if match:
        candidate = match.group(1).strip()
        try:
            json_mod.loads(candidate)
            return candidate
        except json_mod.JSONDecodeError:
            pass

    match = _BRACE_JSON_RE.search(raw)
    if match:
        candidate = match.group(0).strip()
        try:
            json_mod.loads(candidate)
            return candidate
        except json_mod.JSONDecodeError:
            pass

    return raw