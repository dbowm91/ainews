"""Deterministic narration rendering for finalized, server-owned content."""
from __future__ import annotations

import hashlib
import html
import json
import re
from typing import Any

RENDERER_VERSION = "tts-script-v1"
MAX_SCRIPT_CHARS = 16_000
_URL = re.compile(r"https?://\S+|www\.\S+", re.I)
_CITATION = re.compile(r"\[(?:\^?\d+|source|citation)[^\]]*\]", re.I)


def _plain(value: Any, aliases: dict[str, str] | None = None) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]*>", " ", text)
    text = re.sub(r"!?(\[[^\]]*\])\([^)]*\)", r"\1", text)
    text = re.sub(r"`{1,3}([^`]+)`{1,3}", r"\1", text)
    text = re.sub(r"[*_~>#]", " ", text)
    def remove_url(match: re.Match[str]) -> str:
        raw = match.group(0)
        punctuation = raw[len(raw.rstrip(".,!?;:)")):]
        return " " + punctuation

    text = _URL.sub(remove_url, text)
    text = _CITATION.sub("", text)
    text = re.sub(r"\b(?:at|from|via|see|source|read|here)\s+(?=[,.!?;:]|$)", "", text, flags=re.I)
    text = re.sub(r"(?<=\d),(?=\d{3}(?:\D|$))", "", text)
    text = re.sub(r"(?<=\d)\s*%", " percent", text)
    text = text.replace("&", " and ").replace("—", " — ").replace("–", " — ")
    for source, spoken in sorted((aliases or {}).items(), key=lambda pair: len(pair[0]), reverse=True):
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+-]{0,31}", source):
            def replace_alias(_match: re.Match[str], alias: str = spoken) -> str:
                return alias

            text = re.sub(rf"(?<!\w){re.escape(source)}(?!\w)", replace_alias, text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip(" \t\r\n")


def render_article_script(final_article: str, *, summary: str = "", max_chars: int = MAX_SCRIPT_CHARS,
                          aliases: dict[str, str] | None = None) -> str:
    try:
        data = json.loads(final_article)
    except (TypeError, json.JSONDecodeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    sections: list[str] = []
    fields = (("headline", data.get("headline")), ("TL;DR", data.get("tldr") or summary),
              ("Why it matters", data.get("why_it_matters")), ("Key takeaways", data.get("key_points") or data.get("key_takeaways")))
    seen: set[str] = set()
    for label, value in fields:
        if isinstance(value, list):
            value = ". ".join(str(x) for x in value)
        cleaned = _plain(value, aliases)
        if cleaned and cleaned.casefold() not in seen:
            sections.append(f"{label}. {cleaned}" if label != "headline" else cleaned)
            seen.add(cleaned.casefold())
    body = data.get("body") or data.get("condensed_body")
    if isinstance(body, list):
        body = " ".join(str(x) for x in body)
    cleaned_body = _plain(body, aliases)
    if cleaned_body:
        sections.append(cleaned_body)
    watch = _plain(data.get("what_to_watch"), aliases)
    if watch and watch.casefold() not in seen:
        sections.append(f"What to watch. {watch}")
    result = "\n\n".join(sections)
    if not result or len(result) > max_chars:
        raise ValueError("Narration script is empty or exceeds the configured character limit")
    return result


def render_edition_script(subject: str, summary: str, items: list[dict[str, Any]], *, max_chars: int = MAX_SCRIPT_CHARS,
                          aliases: dict[str, str] | None = None) -> str:
    sections = [x for x in (_plain(subject, aliases), _plain(summary, aliases)) if x]
    for item in sorted(items, key=lambda row: int(row.get("position", 0))):
        story = ". ".join(x for x in (_plain(item.get("headline"), aliases), _plain(item.get("why_it_matters"), aliases), _plain(item.get("paragraph"), aliases)) if x)
        if story:
            sections.append(story)
    result = "\n\n".join(sections)
    if not result or len(result) > max_chars:
        raise ValueError("Narration script is empty or exceeds the configured character limit")
    return result


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def split_script(script: str, *, max_chars: int = 1200) -> list[str]:
    """Split deterministically at paragraph/sentence boundaries."""
    if max_chars < 100:
        raise ValueError("max_chars must be at least 100")
    sentences = re.split(r"(?<=[.!?])\s+", script.strip())
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        while len(sentence) > max_chars:
            if current:
                chunks.append(current); current = ""
            cut = sentence.rfind(" ", 0, max_chars + 1)
            cut = cut if cut > 0 else max_chars
            chunks.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(current); current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks
