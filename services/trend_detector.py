import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_FALLBACK_PATTERNS = {
    "ai": [
        r"\bai\b",
        r"\bartificial intelligence\b",
        r"\bmachine learning\b",
        r"\bllm\b",
        r"\bgpt\b",
        r"\bclaude\b",
        r"\bgemini\b",
        r"\bopenai\b",
        r"\bdeep learning\b",
        r"\bneural net",
        r"\btransformer",
        r"\blanguage model\b",
        r"\bdeepseek\b",
        r"\bllama\b",
        r"\bmistral\b",
        r"\bembedding\b",
        r"\bfine.?tun",
    ],
    "privacy": [
        r"\bprivacy\b",
        r"\bsurveillance\b",
        r"\bencrypt",
        r"\bgdpr\b",
        r"\btracking\b",
        r"\bdata breach\b",
        r"\btor\b",
        r"\bvpn\b",
    ],
    "security": [
        r"\bcve-\d",
        r"\bvulnerabilit",
        r"\bexploit\b",
        r"\bmalware\b",
        r"\bransomware\b",
        r"\bzero.?day\b",
        r"\bcybersec",
    ],
    "programming": [
        r"\brust\b",
        r"\bpython\b",
        r"\bgolang\b",
        r"\bjavascript\b",
        r"\btypescript\b",
        r"\bc\+\+\b",
        r"\bopen.?source\b",
        r"\bgithub\b",
    ],
    "hardware": [
        r"\bgpu\b",
        r"\bchip\b",
        r"\bsemiconductor\b",
        r"\bnvidia\b",
        r"\bamd\b",
        r"\bapple\b",
    ],
}

_COMPILED_PATTERNS: dict[str, list[re.Pattern]] = {
    topic: [re.compile(p, re.I) for p in pats]
    for topic, pats in _FALLBACK_PATTERNS.items()
}
_COMPILED_CACHE: dict[str, list[re.Pattern]] = {}


def _load_patterns_from_file() -> dict[str, list[str]]:
    try:
        import yaml

        topics_path = Path(__file__).parent.parent / "topics.yaml"
        if topics_path.exists():
            raw = yaml.safe_load(topics_path.read_text()) or {}
            topic_keys = list((raw.get("topics") or {}).keys())
            patterns = {k: _FALLBACK_PATTERNS.get(k, []) for k in topic_keys}
            for k, v in _FALLBACK_PATTERNS.items():
                if k not in patterns:
                    patterns[k] = v
            return patterns
    except (ImportError, KeyError, AttributeError, ValueError) as e:
        logger.debug("Failed to load patterns from file: %s", e)
        pass
    return dict(_FALLBACK_PATTERNS)


def _load_patterns() -> dict[str, list[str]]:
    try:
        from services.config_cache import get_config_cache

        result: dict[str, list[str]] = get_config_cache().get(
            key="trend_patterns",
            loader_fn=_load_patterns_from_file,
            ttl=300,
        )
        return result
    except Exception as e:
        logger.debug("Config cache failed for trend patterns: %s", e)
        return _load_patterns_from_file()


def _get_compiled_patterns() -> dict[str, list[re.Pattern]]:
    global _COMPILED_CACHE
    if not _COMPILED_CACHE:
        string_patterns = _load_patterns()
        _COMPILED_CACHE = {
            topic: [re.compile(p, re.I) for p in pats]
            for topic, pats in string_patterns.items()
        }
    return _COMPILED_CACHE


def classify(title: str, text: str = "") -> list[str]:
    patterns = _get_compiled_patterns()
    combined = f"{title} {text}".lower()
    matched = [
        topic
        for topic, pats in patterns.items()
        if any(p.search(combined) for p in pats)
    ]
    return matched or ["other"]


def compute_velocity(score: int, timestamp_unix: float) -> float:
    import time

    age_hours = max((time.time() - timestamp_unix) / 3600, 0.1)
    return score / age_hours
