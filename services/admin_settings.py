"""Read and write the operator configuration from the admin panel.

The three files this service edits -- ``providers.yaml``, ``pipeline.yaml``
and ``topics.yaml`` -- are the same files the operator CLI edits. They are
read and written in the shape the application reads them in, which for
``providers.yaml`` is a *list* of provider definitions.

That shape matters. The CLI normalises the list into a mapping keyed by
provider id when it loads the file, and writes the mapping back out again.
The application, on the other hand, reads a list. A ``providers.yaml``
written by the CLI is therefore a file the application cannot load. This
service reads and writes the list shape directly so that the admin panel
and the application always agree, whichever tool made the change.

Writes go through the configuration transaction engine, so every change is
validated, backed up and reversible.
"""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

# The pipeline roles an operator can point at a different provider or model.
PIPELINE_ROLES = ("selector", "researcher", "writer", "editor")

# The provider types that speak the OpenAI HTTP API and can therefore serve
# a local inference endpoint as well as a hosted one.
API_PROVIDER_TYPES = ("openai", "anthropic", "gemini", "ollama")


class SettingsError(Exception):
    """Raised when a settings change cannot be applied."""


@dataclass(frozen=True)
class ProviderView:
    """A provider as the admin panel shows it.

    The credential is never carried in this view. ``api_key_ref`` holds the
    reference as written in the file -- ``${OPENAI_API_KEY}`` or empty --
    and ``has_api_key`` says whether a credential is configured. The value
    itself is never read out of the environment and never rendered.
    """

    id: str
    type: str
    enabled: bool
    is_default: bool
    model: str
    endpoint: str
    api_key_ref: str
    has_api_key: bool
    local: bool
    timeout_seconds: int
    retry_attempts: int
    # Custom request headers the provider declares. They are resolved from the
    # environment when the provider is tested, because a gateway may require
    # a routing header and reject a request without it. The values are never
    # rendered on the page.
    headers: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class RoleView:
    """A pipeline role and the provider and model it uses."""

    role: str
    provider: str
    model: str
    enabled: bool


@dataclass(frozen=True)
class IdentityView:
    """The name the site attributes its summaries to."""

    global_agent_name: str
    topics: tuple[tuple[str, str, str], ...] = ()


@dataclass(frozen=True)
class ProviderProbe:
    """The result of testing a provider."""

    provider_id: str
    ok: bool
    detail: str
    models: tuple[str, ...] = ()
    latency_ms: int = 0


@dataclass(frozen=True)
class TopicView:
    """A topic the site follows, as the admin panel shows it."""

    id: str
    display_name: str
    description: str
    color: str
    icon: str
    query: str
    agent_name: str
    # How many sources still follow this topic. A topic that no source
    # follows collects nothing, which is worth showing.
    source_count: int = 0


@dataclass(frozen=True)
class ScheduleView:
    """The pipeline schedule, as the admin panel shows it."""

    crawl_interval_minutes: int = 30
    retry_stuck_interval_minutes: int = 60
    publish_scheduled_interval_minutes: int = 5
    auto_approve_interval_minutes: int = 1
    generate_newsletters_hour: int = 8

    def __getitem__(self, key: str) -> int:
        """Read a field by name, so a template can loop over the settings."""
        try:
            return int(getattr(self, key))
        except AttributeError as e:
            raise KeyError(key) from e

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and hasattr(self, key)


@dataclass(frozen=True)
class ReviewView:
    """The review behaviour, as the admin panel shows it."""

    enabled: bool = False
    auto_approve: bool = False
    auto_publish_threshold: Optional[int] = None


@dataclass(frozen=True)
class RuntimeView:
    max_concurrent_llm_requests: int = 2


# The schedule settings the admin panel exposes, with the bounds each one
# accepts. The bounds match the configuration validator, so a value the panel
# accepts is a value the validator accepts.
SCHEDULE_FIELDS: tuple[tuple[str, str, int, int], ...] = (
    ("crawl_interval_minutes", "Crawl every (minutes)", 1, 1440),
    ("retry_stuck_interval_minutes", "Retry stuck articles every (minutes)", 1, 1440),
    ("publish_scheduled_interval_minutes", "Check for scheduled articles every (minutes)", 1, 1440),
    ("auto_approve_interval_minutes", "Auto-approve pass every (minutes)", 1, 1440),
    ("generate_newsletters_hour", "Send the newsletter at (hour, UTC)", 0, 23),
)

# The colours a topic badge can use. They are the category colours the theme
# system defines.
TOPIC_COLORS = (
    "blue",
    "purple",
    "orange",
    "red",
    "green",
    "pink",
    "cyan",
    "yellow",
)


def _sources_path() -> Path:
    from schemas.common import BASE_DIR

    return Path(BASE_DIR) / "sources.yaml"


def _providers_path() -> Path:
    from schemas.llm import default_providers_path

    return default_providers_path()


def _pipeline_path() -> Path:
    from schemas.common import BASE_DIR

    return Path(BASE_DIR) / "pipeline.yaml"


def _topics_path() -> Path:
    from schemas.common import BASE_DIR

    return Path(BASE_DIR) / "topics.yaml"


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return raw if isinstance(raw, dict) else {}


def _write_yaml(data: dict[str, Any]) -> bytes:
    return yaml.safe_dump(
        data,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=100,
    ).encode("utf-8")


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return min(maximum, max(minimum, number))


def _require_int(value: Any, label: str, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise SettingsError(f"{label} must be a whole number") from exc
    if isinstance(value, bool) or not minimum <= number <= maximum:
        raise SettingsError(f"{label} must be between {minimum} and {maximum}")
    return number


def _transaction_paths():
    """Return the resolved paths the configuration transaction expects.

    The transaction is pointed at the files the application actually reads,
    which are not always the files the CLI resolves: the application reads
    its configuration from its own directory unless an environment variable
    says otherwise.
    """
    from ainews_config.paths import resolve_paths

    paths = resolve_paths()
    return dataclasses.replace(
        paths,
        providers_file=dataclasses.replace(paths.providers_file, path=_providers_path()),
        pipeline_file=dataclasses.replace(paths.pipeline_file, path=_pipeline_path()),
        topics_file=dataclasses.replace(paths.topics_file, path=_topics_path()),
        sources_file=dataclasses.replace(paths.sources_file, path=_sources_path()),
    )


def _endpoint_of(provider: dict[str, Any]) -> str:
    config = provider.get("config") or {}
    for key in ("base_url", "host", "endpoint", "url"):
        value = config.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def read_providers() -> list[ProviderView]:
    """Return every configured provider, in the order the file lists them."""
    raw = _read_yaml(_providers_path())
    default_id = raw.get("default_provider") or ""
    entries = raw.get("providers") or []

    views: list[ProviderView] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        provider_id = str(entry.get("id") or "")
        if not provider_id:
            continue
        config = entry.get("config") or {}
        if not isinstance(config, dict):
            config = {}
        api_key_ref = config.get("api_key")
        api_key_ref = api_key_ref if isinstance(api_key_ref, str) else ""
        raw_headers = config.get("headers") or {}
        headers: tuple[tuple[str, str], ...] = ()
        if isinstance(raw_headers, dict):
            headers = tuple(
                (str(k), str(v))
                for k, v in raw_headers.items()
                if isinstance(v, str) and v
            )
        views.append(
            ProviderView(
                id=provider_id,
                type=str(entry.get("type") or ""),
                enabled=bool(entry.get("enabled", True)),
                is_default=provider_id == default_id,
                model=str(config.get("model") or ""),
                endpoint=_endpoint_of(entry),
                api_key_ref=api_key_ref,
                has_api_key=bool(api_key_ref),
                local=bool(config.get("local", False)),
                timeout_seconds=_bounded_int(
                    config.get("timeout_seconds"), 900 if config.get("local") else 120, 1, 1800,
                ),
                retry_attempts=_bounded_int(
                    config.get("retry_attempts"), 1 if config.get("local") else 3, 1, 5,
                ),
                headers=headers,
            )
        )
    return views


def read_roles() -> list[RoleView]:
    """Return the pipeline roles and the provider and model each uses."""
    raw = _read_yaml(_pipeline_path())
    pipeline = raw.get("pipeline") or {}
    if not isinstance(pipeline, dict):
        pipeline = {}

    roles: list[RoleView] = []
    for role in PIPELINE_ROLES:
        entry = pipeline.get(role)
        if not isinstance(entry, dict):
            continue
        roles.append(
            RoleView(
                role=role,
                provider=str(entry.get("provider") or ""),
                model=str(entry.get("model") or ""),
                enabled=bool(entry.get("enabled", True)),
            )
        )
    return roles


def read_identity() -> IdentityView:
    """Return the agent name the site uses, globally and per topic."""
    raw = _read_yaml(_topics_path())
    site = raw.get("site") or {}
    if not isinstance(site, dict):
        site = {}
    global_name = site.get("agent_name")
    global_name = global_name.strip() if isinstance(global_name, str) else ""

    topics = raw.get("topics") or {}
    if not isinstance(topics, dict):
        topics = {}

    rows: list[tuple[str, str, str]] = []
    for key, entry in topics.items():
        if not isinstance(entry, dict):
            continue
        agent_name = entry.get("agent_name")
        agent_name = agent_name.strip() if isinstance(agent_name, str) else ""
        display = entry.get("display_name")
        display = display.strip() if isinstance(display, str) else ""
        rows.append((str(key), display, agent_name))
    rows.sort()
    return IdentityView(global_agent_name=global_name, topics=tuple(rows))


def update_providers(changes: dict[str, dict[str, Any]]) -> list[str]:
    """Apply changes to the provider list and return the ids that changed.

    ``changes`` maps a provider id to the fields to change: ``enabled``,
    ``model``, ``endpoint``, ``local`` and ``make_default``. The endpoint is
    written to ``base_url`` for an API provider and to ``host`` for Ollama,
    so the file keeps the shape that provider type expects.
    """
    path = _providers_path()
    raw = _read_yaml(path)
    entries = raw.get("providers")
    if not isinstance(entries, list):
        raise SettingsError("providers.yaml does not contain a provider list")

    changed: list[str] = []
    for provider_id, fields in changes.items():
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("id") != provider_id:
                continue
            config = entry.get("config")
            if not isinstance(config, dict):
                config = {}
            if "enabled" in fields:
                entry["enabled"] = bool(fields["enabled"])
            if "model" in fields:
                model = str(fields["model"] or "").strip()
                if not model:
                    raise SettingsError(f"{provider_id}: a model name is required")
                config["model"] = model
            if "endpoint" in fields:
                endpoint = str(fields["endpoint"] or "").strip()
                if endpoint:
                    key = "host" if entry.get("type") == "ollama" else "base_url"
                    config[key] = endpoint
            if "local" in fields:
                config["local"] = bool(fields["local"])
            if "timeout_seconds" in fields:
                config["timeout_seconds"] = _require_int(
                    fields["timeout_seconds"], f"{provider_id} request timeout", 1, 1800,
                )
            if "retry_attempts" in fields:
                config["retry_attempts"] = _require_int(
                    fields["retry_attempts"], f"{provider_id} request attempts", 1, 5,
                )
            entry["config"] = config
            changed.append(provider_id)
            break
        else:
            raise SettingsError(f"unknown provider: {provider_id}")

    if any(fields.get("make_default") for fields in changes.values()):
        default_id = next(
            pid for pid, fields in changes.items() if fields.get("make_default")
        )
        raw["default_provider"] = default_id

    from ainews_config.transaction import transaction

    with transaction(_transaction_paths()) as txn:
        txn.modify_file(path, _write_yaml(raw))
    return changed


def read_runtime() -> RuntimeView:
    raw = _read_yaml(_pipeline_path())
    runtime = raw.get("runtime")
    if not isinstance(runtime, dict):
        runtime = {}
    return RuntimeView(
        max_concurrent_llm_requests=_bounded_int(
            runtime.get("max_concurrent_llm_requests"), 2, 1, 32,
        ),
    )


def update_runtime(max_concurrent_llm_requests: Any) -> list[str]:
    number = _require_int(max_concurrent_llm_requests, "maximum parallel LLM requests", 1, 32)

    path = _pipeline_path()
    raw = _read_yaml(path)
    runtime = raw.get("runtime")
    if not isinstance(runtime, dict):
        runtime = {}
    runtime["max_concurrent_llm_requests"] = number
    raw["runtime"] = runtime
    from ainews_config.transaction import transaction

    with transaction(_transaction_paths()) as txn:
        txn.modify_file(path, _write_yaml(raw))
    return ["max_concurrent_llm_requests"]


def update_roles(updates: dict[str, dict[str, Any]]) -> list[str]:
    """Apply changes to the pipeline roles and return the roles that changed."""
    path = _pipeline_path()
    raw = _read_yaml(path)
    pipeline = raw.get("pipeline")
    if not isinstance(pipeline, dict):
        raise SettingsError("pipeline.yaml does not contain a pipeline section")

    changed: list[str] = []
    for role, fields in updates.items():
        entry = pipeline.get(role)
        if not isinstance(entry, dict):
            raise SettingsError(f"unknown pipeline role: {role}")
        if "provider" in fields:
            provider = str(fields["provider"] or "").strip()
            if not provider:
                raise SettingsError(f"{role}: a provider is required")
            entry["provider"] = provider
        if "model" in fields:
            model = str(fields["model"] or "").strip()
            if not model:
                raise SettingsError(f"{role}: a model name is required")
            entry["model"] = model
        if "enabled" in fields:
            entry["enabled"] = bool(fields["enabled"])
        changed.append(role)

    from ainews_config.transaction import transaction

    with transaction(_transaction_paths()) as txn:
        txn.modify_file(path, _write_yaml(raw))
    return changed


def update_identity(
    global_agent_name: str,
    topic_agent_names: dict[str, str],
) -> None:
    """Set the site-wide agent name and the per-topic overrides."""
    path = _topics_path()
    raw = _read_yaml(path)
    topics = raw.get("topics")
    if not isinstance(topics, dict):
        raise SettingsError("topics.yaml does not contain a topics section")

    name = global_agent_name.strip()
    if name:
        site = raw.get("site")
        if not isinstance(site, dict):
            site = {}
        site["agent_name"] = name
        raw["site"] = site
    else:
        site = raw.get("site")
        if isinstance(site, dict):
            site.pop("agent_name", None)
            if site:
                raw["site"] = site
            else:
                raw.pop("site", None)

    for topic_key, agent_name in topic_agent_names.items():
        entry = topics.get(topic_key)
        if not isinstance(entry, dict):
            raise SettingsError(f"unknown topic: {topic_key}")
        value = agent_name.strip()
        if value:
            entry["agent_name"] = value
        else:
            entry.pop("agent_name", None)

    from ainews_config.transaction import transaction

    with transaction(_transaction_paths()) as txn:
        txn.modify_file(path, _write_yaml(raw))


def _source_topic_usage() -> dict[str, list[str]]:
    """Return, for each topic, the sources that still follow it."""
    raw = _read_yaml(_sources_path())
    entries = raw.get("sources") or []
    usage: dict[str, list[str]] = {}
    if not isinstance(entries, list):
        return usage
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        source_id = str(entry.get("id") or "")
        if not source_id:
            continue
        topics = entry.get("topics")
        if not isinstance(topics, dict):
            continue
        include = topics.get("include")
        if not isinstance(include, list):
            continue
        for topic_id in include:
            if isinstance(topic_id, str):
                usage.setdefault(topic_id, []).append(source_id)
    return usage


def read_topics() -> list[TopicView]:
    """Return the topics the site follows."""
    raw = _read_yaml(_topics_path())
    topics = raw.get("topics")
    if not isinstance(topics, dict):
        return []

    usage = _source_topic_usage()

    views: list[TopicView] = []
    for key, entry in topics.items():
        if not isinstance(entry, dict):
            continue
        views.append(
            TopicView(
                id=str(key),
                display_name=str(entry.get("display_name") or ""),
                description=str(entry.get("description") or ""),
                color=str(entry.get("color") or "blue"),
                icon=str(entry.get("icon") or ""),
                query=str(entry.get("query") or ""),
                agent_name=str(entry.get("agent_name") or ""),
                source_count=len(usage.get(str(key), [])),
            )
        )
    views.sort(key=lambda v: v.id)
    return views


def _write_topics(raw: dict[str, Any], path: Path, sources_raw: dict[str, Any] | None = None) -> None:
    from ainews_config.transaction import transaction

    with transaction(_transaction_paths()) as txn:
        txn.modify_file(path, _write_yaml(raw))
        if sources_raw is not None:
            txn.modify_file(_sources_path(), _write_yaml(sources_raw))


def update_topics(updates: dict[str, dict[str, Any]]) -> list[str]:
    """Change the topics that already exist. Returns the ids that changed.

    ``updates`` maps a topic id to the fields to change: ``display_name``,
    ``description``, ``color``, ``icon`` and ``query``.
    """
    path = _topics_path()
    raw = _read_yaml(path)
    topics = raw.get("topics")
    if not isinstance(topics, dict):
        raise SettingsError("topics.yaml does not contain a topics section")

    changed: list[str] = []
    for topic_id, fields in updates.items():
        entry = topics.get(topic_id)
        if not isinstance(entry, dict):
            raise SettingsError(f"unknown topic: {topic_id}")
        if "display_name" in fields:
            display_name = str(fields["display_name"] or "").strip()
            if not display_name:
                raise SettingsError(f"{topic_id}: a display name is required")
            entry["display_name"] = display_name
        if "description" in fields:
            entry["description"] = str(fields["description"] or "").strip()
        if "color" in fields:
            color = str(fields["color"] or "").strip().lower()
            if color not in TOPIC_COLORS:
                raise SettingsError(
                    f"{topic_id}: unknown colour {color!r}; choose one of {', '.join(TOPIC_COLORS)}",
                )
            entry["color"] = color
        if "icon" in fields:
            icon = str(fields["icon"] or "").strip()
            if icon:
                entry["icon"] = icon
            else:
                entry.pop("icon", None)
        if "query" in fields:
            query = str(fields["query"] or "").strip()
            if query:
                entry["query"] = query
            else:
                # An empty query means "use the default keywords", which is
                # the topic's absence from the file rather than an empty
                # string in it.
                entry.pop("query", None)
        changed.append(topic_id)

    _write_topics(raw, path)
    return changed


def add_topic(
    topic_id: str,
    display_name: str,
    description: str = "",
    color: str = "blue",
    query: str = "",
) -> str:
    """Add a topic the site follows. Returns the topic id that was created."""
    key = _normalize_topic_id(topic_id or display_name)
    if not key:
        raise SettingsError("a topic id is required")

    path = _topics_path()
    raw = _read_yaml(path)
    topics = raw.get("topics")
    if not isinstance(topics, dict):
        raise SettingsError("topics.yaml does not contain a topics section")
    if key in topics:
        raise SettingsError(f"topic {key!r} already exists")

    color = (color or "blue").strip().lower()
    if color not in TOPIC_COLORS:
        raise SettingsError(
            f"unknown colour {color!r}; choose one of {', '.join(TOPIC_COLORS)}",
        )

    name = display_name.strip() or key
    entry: dict[str, Any] = {
        "display_name": name,
        "description": description.strip(),
        "color": color,
    }
    if query.strip():
        entry["query"] = query.strip()

    topics[key] = entry
    _write_topics(raw, path)
    return key


def remove_topic(topic_id: str) -> list[str]:
    """Remove a topic, and every source reference to it.

    A source that still listed a deleted topic would leave the configuration
    invalid -- the validator rejects a source that follows a topic that does
    not exist -- so the references are removed in the same transaction. The
    ids of the sources that were changed are returned.
    """
    path = _topics_path()
    raw = _read_yaml(path)
    topics = raw.get("topics")
    if not isinstance(topics, dict):
        raise SettingsError("topics.yaml does not contain a topics section")
    if topic_id not in topics:
        raise SettingsError(f"unknown topic: {topic_id}")

    del topics[topic_id]

    sources_path = _sources_path()
    sources_raw = _read_yaml(sources_path)
    entries = sources_raw.get("sources")
    touched: list[str] = []
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            source_topics = entry.get("topics")
            if not isinstance(source_topics, dict):
                continue
            include = source_topics.get("include")
            if not isinstance(include, list) or topic_id not in include:
                continue
            source_topics["include"] = [t for t in include if t != topic_id]
            touched.append(str(entry.get("id") or ""))

    _write_topics(raw, path, sources_raw if touched else None)
    return touched


def _normalize_topic_id(name: str) -> str:
    """Turn a display name into a stable topic id."""
    import re

    tid = (name or "").lower().strip()
    tid = re.sub(r"[^a-z0-9]+", "_", tid)
    tid = re.sub(r"_+", "_", tid).strip("_")
    return tid[:64]


def read_schedule() -> ScheduleView:
    """Return the pipeline schedule."""
    raw = _read_yaml(_pipeline_path())
    schedule = raw.get("schedule")
    if not isinstance(schedule, dict):
        schedule = {}

    def _int(name: str, default: int) -> int:
        value = schedule.get(name)
        if isinstance(value, bool) or not isinstance(value, int):
            return default
        return value

    return ScheduleView(
        crawl_interval_minutes=_int("crawl_interval_minutes", 30),
        retry_stuck_interval_minutes=_int("retry_stuck_interval_minutes", 60),
        publish_scheduled_interval_minutes=_int("publish_scheduled_interval_minutes", 5),
        auto_approve_interval_minutes=_int("auto_approve_interval_minutes", 1),
        generate_newsletters_hour=_int("generate_newsletters_hour", 8),
    )


def update_schedule(values: dict[str, int]) -> list[str]:
    """Change the pipeline schedule. Returns the names of the fields changed."""
    path = _pipeline_path()
    raw = _read_yaml(path)
    schedule = raw.get("schedule")
    if not isinstance(schedule, dict):
        schedule = {}

    bounds = {name: (low, high) for name, _label, low, high in SCHEDULE_FIELDS}

    changed: list[str] = []
    for name, value in values.items():
        if name not in bounds:
            raise SettingsError(f"unknown schedule setting: {name}")
        low, high = bounds[name]
        try:
            number = int(value)
        except (TypeError, ValueError) as e:
            raise SettingsError(f"{name}: a whole number is required") from e
        if not (low <= number <= high):
            raise SettingsError(f"{name}: must be between {low} and {high}, got {number}")
        schedule[name] = number
        changed.append(name)

    if not changed:
        return []

    raw["schedule"] = schedule

    from ainews_config.transaction import transaction

    with transaction(_transaction_paths()) as txn:
        txn.modify_file(path, _write_yaml(raw))
    return changed


def read_review() -> ReviewView:
    """Return the review behaviour."""
    raw = _read_yaml(_pipeline_path())
    pipeline = raw.get("pipeline")
    if not isinstance(pipeline, dict):
        pipeline = {}
    review = pipeline.get("review")
    if not isinstance(review, dict):
        review = {}

    threshold = review.get("auto_publish_threshold")
    if isinstance(threshold, bool) or not isinstance(threshold, int):
        threshold = None

    return ReviewView(
        enabled=bool(review.get("enabled", False)),
        auto_approve=bool(review.get("auto_approve", False)),
        auto_publish_threshold=threshold,
    )


def update_review(
    enabled: bool | None = None,
    auto_approve: bool | None = None,
    auto_publish_threshold: int | None = None,
    clear_threshold: bool = False,
) -> list[str]:
    """Change the review behaviour. Returns the names of the fields changed."""
    path = _pipeline_path()
    raw = _read_yaml(path)
    pipeline = raw.get("pipeline")
    if not isinstance(pipeline, dict):
        raise SettingsError("pipeline.yaml does not contain a pipeline section")

    review = pipeline.get("review")
    if not isinstance(review, dict):
        review = {}

    changed: list[str] = []
    if enabled is not None:
        review["enabled"] = bool(enabled)
        changed.append("enabled")
    if auto_approve is not None:
        review["auto_approve"] = bool(auto_approve)
        changed.append("auto_approve")
    if clear_threshold:
        review.pop("auto_publish_threshold", None)
        changed.append("auto_publish_threshold")
    elif auto_publish_threshold is not None:
        if not (0 <= auto_publish_threshold <= 100):
            raise SettingsError(
                f"auto_publish_threshold: must be between 0 and 100, got {auto_publish_threshold}",
            )
        review["auto_publish_threshold"] = int(auto_publish_threshold)
        changed.append("auto_publish_threshold")

    if not changed:
        return []

    pipeline["review"] = review
    raw["pipeline"] = pipeline

    from ainews_config.transaction import transaction

    with transaction(_transaction_paths()) as txn:
        txn.modify_file(path, _write_yaml(raw))
    return changed


def _probe_values(provider: ProviderView) -> dict[str, Any]:
    """Build the values the provider adapter probes with.

    The adapter is the CLI's, because it already knows how to talk to each
    provider type and how to reach its model list.

    The credential is resolved from the environment here and handed
    straight to the adapter. It is never stored on the view, never logged
    and never rendered: only whether one is configured reaches the page.
    """
    values: dict[str, Any] = {
        "id": provider.id,
        "enabled": provider.enabled,
        "is_default": provider.is_default,
    }
    if provider.type == "ollama":
        values["host"] = provider.endpoint
    else:
        values["base_url"] = provider.endpoint
        values["api_key"] = _resolve_credential(provider.api_key_ref)
        values["model"] = provider.model
        # A gateway may require a routing header of its own. The header
        # values can reference the environment, exactly like a credential.
        resolved_headers = {
            key: _resolve_credential(value) for key, value in provider.headers
        }
        if resolved_headers:
            values["headers"] = resolved_headers
    return values


def _resolve_credential(ref: str) -> str:
    """Resolve a credential reference such as ``${OPENAI_API_KEY}``.

    A literal value in the file is used as it stands. A reference to an
    environment variable resolves to that variable's value, or to an empty
    string when it is not set -- a local endpoint needs no credential, so
    an absent one is not an error here.
    """
    if not ref:
        return ""
    if ref.startswith("${") and ref.endswith("}"):
        import os

        return os.environ.get(ref[2:-1], "")
    return ref


def probe_provider(provider_id: str, *, timeout: float = 10.0) -> ProviderProbe:
    """Test that a provider works, and list the models it offers.

    The probe is a real request to the provider: it proves the endpoint is
    reachable, the credential works and the model exists. It never records
    the credential.
    """
    views = {v.id: v for v in read_providers()}
    view = views.get(provider_id)
    if view is None:
        return ProviderProbe(
            provider_id=provider_id,
            ok=False,
            detail=f"unknown provider: {provider_id}",
        )

    from ainews_cli.providers.registry import get_adapter

    values = _probe_values(view)

    # A hosted provider with no credential configured is not going to work,
    # even if its endpoint answers. Say so rather than reporting a green
    # tick on a provider that cannot serve a request.
    if view.type != "ollama" and not view.local and not values.get("api_key"):
        return ProviderProbe(
            provider_id=provider_id,
            ok=False,
            detail="no credential configured",
        )

    try:
        adapter = get_adapter(view.type)
        definition = adapter.build_definition(values)
        result = adapter.probe(definition, values)
    except Exception as e:  # noqa: BLE001
        logger.warning("Provider probe failed for %s: %s", provider_id, e)
        return ProviderProbe(provider_id=provider_id, ok=False, detail=str(e)[:300])

    models: tuple[str, ...] = ()
    if result.success:
        try:
            discovered = adapter.discover_models(definition, values)
            if discovered.success:
                models = tuple(m.id for m in discovered.models)
        except Exception as e:  # noqa: BLE001
            logger.info("Model discovery failed for %s: %s", provider_id, e)

    if not models and view.model:
        # The endpoint does not implement model discovery. The model the
        # provider is configured to use is still worth reporting.
        models = (view.model,)

    detail = "ok" if result.success else (result.error or "probe failed")
    return ProviderProbe(
        provider_id=provider_id,
        ok=result.success,
        detail=detail[:300],
        models=models,
        latency_ms=int(result.latency_ms or 0),
    )


def agent_name_for(topic: Optional[str]) -> str:
    """Return the agent name to show for a topic.

    A topic-specific name wins over the site-wide one. An empty string
    means the caller should fall back to the model that wrote the article.
    """
    identity = read_identity()
    if topic:
        for key, _display, agent_name in identity.topics:
            if key == topic and agent_name:
                return agent_name
    return identity.global_agent_name
