from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ainews_config.fields import FIELD_REGISTRY, ConfigField, SecretClassification
from ainews_config.paths import ResolvedPaths, resolve_paths

_ENV_VAR_PATTERN = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")


@dataclass(frozen=True)
class Diagnostic:
    severity: str
    code: str
    file: str | None
    key: str | None
    message: str
    remediation: str | None = None


@dataclass(frozen=True)
class ValueProvenance:
    key: str
    source: str
    file: str | None = None
    line: int | None = None
    raw_value: Any = None


@dataclass
class EffectiveConfiguration:
    paths: ResolvedPaths
    environment: dict[str, str]
    providers: dict[str, Any]
    pipeline: dict[str, Any]
    sources: list[dict[str, Any]]
    topics: dict[str, Any]
    provenance: dict[str, ValueProvenance]
    diagnostics: list[Diagnostic]
    dotenv: dict[str, str]


def load_dotenv(path: Path) -> tuple[dict[str, str], list[Diagnostic], dict[str, int]]:
    env: dict[str, str] = {}
    diagnostics: list[Diagnostic] = []
    line_numbers: dict[str, int] = {}

    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return env, diagnostics, line_numbers
    except OSError as exc:
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="DOTENV_READ_ERROR",
                file=str(path),
                key=None,
                message=f"Cannot read .env file: {exc}",
                remediation="Check file permissions.",
            )
        )
        return env, diagnostics, line_numbers

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[len("export "):].strip()

        if "=" not in line:
            diagnostics.append(
                Diagnostic(
                    severity="error",
                    code="DOTENV_MALFORMED_LINE",
                    file=str(path),
                    key=None,
                    message=f"Line {lineno}: no '=' found: {raw_line!r}",
                    remediation="Use KEY=value format.",
                )
            )
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            diagnostics.append(
                Diagnostic(
                    severity="error",
                    code="DOTENV_EMPTY_KEY",
                    file=str(path),
                    key=None,
                    message=f"Line {lineno}: empty key before '='.",
                    remediation="Provide a non-empty key.",
                )
            )
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] in ("'", '"') and value[-1] == value[0]:
            value = value[1:-1]
        elif value.startswith('"') or value.startswith("'"):
            diagnostics.append(
                Diagnostic(
                    severity="error",
                    code="DOTENV_UNMATCHED_QUOTE",
                    file=str(path),
                    key=key,
                    message=f"Line {lineno}: unmatched quote on value for '{key}'.",
                    remediation="Close the quote or remove the opening quote.",
                )
            )
            continue

        env[key] = value
        line_numbers[key] = lineno

    return env, diagnostics, line_numbers


def resolve_env_vars(value: Any, env: dict[str, str]) -> tuple[Any, list[Diagnostic]]:
    diagnostics: list[Diagnostic] = []

    if isinstance(value, str):
        def _replace(match: re.Match[str]) -> str:
            var_name = match.group(1)
            if var_name in env:
                return env[var_name]
            diagnostics.append(
                Diagnostic(
                    severity="warning",
                    code="ENV_VAR_UNRESOLVED",
                    file=None,
                    key=None,
                    message=f"Unresolved environment variable: ${{{var_name}}}.",
                    remediation=f"Set {var_name} in your environment or .env file.",
                )
            )
            return match.group(0)

        result = _ENV_VAR_PATTERN.sub(_replace, value)
        return result, diagnostics

    if isinstance(value, dict):
        merged_diags: list[Diagnostic] = []
        out = {}
        for k, v in value.items():
            resolved, diags = resolve_env_vars(v, env)
            out[k] = resolved
            merged_diags.extend(diags)
        return out, merged_diags

    if isinstance(value, list):
        merged_list_diags: list[Diagnostic] = []
        list_out: list[Any] = []
        for item in value:
            resolved, diags = resolve_env_vars(item, env)
            list_out.append(resolved)
            merged_list_diags.extend(diags)
        return list_out, merged_list_diags

    return value, diagnostics


def load_yaml(path: Path) -> tuple[Any, list[Diagnostic]]:
    diagnostics: list[Diagnostic] = []

    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, diagnostics
    except OSError as exc:
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="YAML_READ_ERROR",
                file=str(path),
                key=None,
                message=f"Cannot read YAML file: {exc}",
                remediation="Check file permissions.",
            )
        )
        return None, diagnostics

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="YAML_PARSE_ERROR",
                file=str(path),
                key=None,
                message=f"YAML parse error: {exc}",
                remediation="Fix YAML syntax.",
            )
        )
        return None, diagnostics

    return data, diagnostics


def _build_provenance_from_env(
    env: dict[str, str],
    line_numbers: dict[str, int] | None = None,
) -> dict[str, ValueProvenance]:
    provenance: dict[str, ValueProvenance] = {}
    for key, value in env.items():
        provenance[key] = ValueProvenance(
            key=key,
            source="env",
            line=(line_numbers or {}).get(key),
            raw_value=value,
        )
    return provenance


def _build_provenance_from_yaml(
    data: Any,
    prefix: str,
    file_name: str,
) -> dict[str, ValueProvenance]:
    provenance: dict[str, ValueProvenance] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            provenance[full_key] = ValueProvenance(
                key=full_key,
                source="yaml",
                file=file_name,
                raw_value=value,
            )
            if isinstance(value, dict):
                provenance.update(
                    _build_provenance_from_yaml(value, full_key, file_name)
                )
    return provenance


def _validate_providers_schema(
    data: dict[str, Any], file_name: str
) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    providers_val = data.get("providers")
    if providers_val is not None and not isinstance(providers_val, dict):
        diags.append(
            Diagnostic(
                severity="error",
                code="SCHEMA_VIOLATION",
                file=file_name,
                key="providers",
                message="Field 'providers' must be a dict.",
                remediation="Ensure providers.yaml has a 'providers' key mapping provider IDs to configs.",
            )
        )
    default_provider = data.get("default_provider")
    if default_provider is not None and not isinstance(default_provider, str):
        diags.append(
            Diagnostic(
                severity="error",
                code="SCHEMA_VIOLATION",
                file=file_name,
                key="default_provider",
                message="Field 'default_provider' must be a string.",
                remediation="Set default_provider to a provider ID string.",
            )
        )
    search_providers = data.get("search_providers")
    if search_providers is not None and not isinstance(search_providers, list):
        diags.append(
            Diagnostic(
                severity="error",
                code="SCHEMA_VIOLATION",
                file=file_name,
                key="search_providers",
                message="Field 'search_providers' must be a list.",
                remediation="Set search_providers to a list of search provider definitions.",
            )
        )
    return diags


def _validate_pipeline_schema(
    data: dict[str, Any], file_name: str
) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    pipeline_section = data.get("pipeline")
    if pipeline_section is None:
        return diags
    if not isinstance(pipeline_section, dict):
        diags.append(
            Diagnostic(
                severity="error",
                code="SCHEMA_VIOLATION",
                file=file_name,
                key="pipeline",
                message="Field 'pipeline' must be a dict.",
                remediation="Ensure pipeline.yaml has a 'pipeline' key with role configurations.",
            )
        )
        return diags

    expected_roles = ("selector", "researcher", "writer", "editor")
    for role in expected_roles:
        role_val = pipeline_section.get(role)
        if role_val is not None and not isinstance(role_val, dict):
            diags.append(
                Diagnostic(
                    severity="error",
                    code="SCHEMA_VIOLATION",
                    file=file_name,
                    key=f"pipeline.{role}",
                    message=f"Role '{role}' must be a dict.",
                    remediation=f"Set pipeline.{role} to a dict with role configuration.",
                )
            )

    for optional_key in ("schedule", "memory", "subagent"):
        optional_val = data.get(optional_key)
        if optional_val is not None and not isinstance(optional_val, dict):
            diags.append(
                Diagnostic(
                    severity="error",
                    code="SCHEMA_VIOLATION",
                    file=file_name,
                    key=optional_key,
                    message=f"Field '{optional_key}' must be a dict.",
                    remediation=f"Set {optional_key} to a dict with configuration.",
                )
            )

    return diags


def _validate_sources_schema(
    data: list[dict[str, Any]], file_name: str
) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            diags.append(
                Diagnostic(
                    severity="error",
                    code="SCHEMA_VIOLATION",
                    file=file_name,
                    key=f"sources[{idx}]",
                    message=f"Source at index {idx} must be a dict.",
                    remediation="Each source entry must be a dict with 'id', 'url', and 'type' keys.",
                )
            )
            continue
        for required_key in ("id", "url", "type"):
            if required_key not in item:
                diags.append(
                    Diagnostic(
                        severity="error",
                        code="SCHEMA_VIOLATION",
                        file=file_name,
                        key=f"sources[{idx}].{required_key}",
                        message=f"Source at index {idx} is missing required key '{required_key}'.",
                        remediation=f"Add '{required_key}' to source entry at index {idx}.",
                    )
                )
    return diags


def _validate_topics_schema(
    data: dict[str, Any], file_name: str
) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    for tid, tval in data.items():
        if not isinstance(tval, dict):
            diags.append(
                Diagnostic(
                    severity="error",
                    code="SCHEMA_VIOLATION",
                    file=file_name,
                    key=f"topics.{tid}",
                    message=f"Topic '{tid}' must be a dict.",
                    remediation=f"Set topics.{tid} to a dict with at least a 'query' key.",
                )
            )
            continue
        if "query" not in tval:
            diags.append(
                Diagnostic(
                    severity="error",
                    code="SCHEMA_VIOLATION",
                    file=file_name,
                    key=f"topics.{tid}.query",
                    message=f"Topic '{tid}' is missing required key 'query'.",
                    remediation=f"Add 'query' to topic '{tid}'.",
                )
            )
    return diags


def load_all_configs(
    paths: ResolvedPaths,
    *,
    env_overrides: dict[str, str] | None = None,
) -> EffectiveConfiguration:
    all_diags: list[Diagnostic] = []
    all_provenance: dict[str, ValueProvenance] = {}

    env_file_path = paths.env_file.path
    dotenv, dotenv_diags, dotenv_lines = load_dotenv(env_file_path)
    all_diags.extend(dotenv_diags)

    merged_env = dict(dotenv)
    if env_overrides:
        merged_env.update(env_overrides)

    all_provenance.update(_build_provenance_from_env(dotenv, dotenv_lines))

    providers_data: dict[str, Any] = {}
    pipeline_data: dict[str, Any] = {}
    sources_data: list[dict[str, Any]] = []
    topics_data: dict[str, Any] = {}

    for (
        file_path,
        provenance_prefix,
        _,
    ) in [
        (paths.providers_file.path, "providers", "providers"),
        (paths.pipeline_file.path, "pipeline", "pipeline"),
        (paths.sources_file.path, "sources", "sources"),
        (paths.topics_file.path, "topics", "topics"),
    ]:
        data, diags = load_yaml(file_path)
        all_diags.extend(diags)

        if data is not None:
            resolved_data, resolve_diags = resolve_env_vars(data, merged_env)
            all_diags.extend(resolve_diags)
        else:
            resolved_data = data

        if provenance_prefix == "providers" and isinstance(resolved_data, dict):
            providers_data = resolved_data
            all_diags.extend(
                _validate_providers_schema(resolved_data, file_path.name)
            )
        elif provenance_prefix == "pipeline" and isinstance(resolved_data, dict):
            pipeline_data = resolved_data
            all_diags.extend(
                _validate_pipeline_schema(resolved_data, file_path.name)
            )
        elif provenance_prefix == "sources" and isinstance(resolved_data, list):
            sources_data = resolved_data
            all_diags.extend(
                _validate_sources_schema(resolved_data, file_path.name)
            )
        elif provenance_prefix == "topics" and isinstance(resolved_data, dict):
            topics_data = resolved_data
            all_diags.extend(
                _validate_topics_schema(resolved_data, file_path.name)
            )

        if resolved_data is not None:
            yaml_prov = _build_provenance_from_yaml(
                resolved_data, provenance_prefix, file_path.name
            )
            all_provenance.update(yaml_prov)

    for fld in FIELD_REGISTRY.all_keys():
        field_obj = FIELD_REGISTRY.lookup(fld)
        if field_obj is None:
            continue
        if fld not in all_provenance:
            if field_obj.required:
                all_provenance[fld] = ValueProvenance(
                    key=fld, source="missing", raw_value=None
                )
            elif field_obj.default is not None:
                all_provenance[fld] = ValueProvenance(
                    key=fld, source="default", raw_value=field_obj.default
                )
        if field_obj.deprecated:
            all_diags.append(Diagnostic(
                severity="warning",
                code="FIELD_DEPRECATED",
                file=None,
                key=fld,
                message=f"Field '{fld}' is deprecated.",
                remediation=f"Remove '{fld}' from your configuration.",
            ))

    return EffectiveConfiguration(
        paths=paths,
        environment=merged_env,
        providers=providers_data,
        pipeline=pipeline_data,
        sources=sources_data,
        topics=topics_data,
        provenance=all_provenance,
        diagnostics=all_diags,
        dotenv=dotenv,
    )


def _providers_dict_to_list(providers_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert dict-format providers to list-format for validate_cross_file.

    The loader stores providers as a dict keyed by provider ID, but
    validate_cross_file expects a list of provider dicts with 'id' fields.
    """
    raw = providers_cfg.get("providers", {})
    if not isinstance(raw, dict):
        return []
    result: list[dict[str, Any]] = []
    for pid, pval in raw.items():
        if not isinstance(pval, dict):
            continue
        entry: dict[str, Any] = {"id": pid, **pval}
        result.append(entry)
    return result


def load_config_for_app(
    *,
    env_overrides: dict[str, str] | None = None,
    explicit_paths: dict[str, Path | None] | None = None,
) -> EffectiveConfiguration:
    """Load all configuration files and validate cross-file consistency.

    This is the bridge function between the shared ainews_config system and the
    Flask/Celery runtime. It resolves paths, loads all config files, and runs
    cross-file validation.

    Args:
        env_overrides: Optional environment variable overrides.
        explicit_paths: Optional explicit path overrides passed to
            ``resolve_paths()``. When ``None``, paths are resolved using
            the standard precedence chain (env vars, install metadata,
            dev fallback).

    Returns:
        EffectiveConfiguration with diagnostics. On failure, returns a config
        object with error diagnostics rather than raising.
    """
    from ainews_config.validation import validate_cross_file

    paths = resolve_paths(explicit_paths=explicit_paths)
    config = load_all_configs(paths, env_overrides=env_overrides)

    providers_for_validation = _providers_dict_to_list(config.providers)

    validation = validate_cross_file(
        {
            "providers": {
                "providers": providers_for_validation,
                "default_provider": config.providers.get("default_provider"),
            },
            "pipeline": config.pipeline,
            "sources": config.sources,
            "topics": config.topics,
            "environment": config.environment,
        }
    )

    for err in validation.errors:
        config.diagnostics.append(
            Diagnostic(
                severity=err.severity,
                code=err.code,
                file=err.file,
                key=err.key,
                message=err.message,
                remediation=err.remediation,
            )
        )

    return config


def redact_value(
    key: str, value: Any, fld: ConfigField | None = None
) -> Any:
    if fld is None:
        fld = FIELD_REGISTRY.lookup(key)

    if fld is None or fld.secret == SecretClassification.PUBLIC:
        return value
    if fld.secret == SecretClassification.SECRET:
        return "***REDACTED***"
    if fld.secret == SecretClassification.SENSITIVE:
        s = str(value)
        if len(s) <= 4:
            return "***"
        return "***" + s[-4:]
    return value


def _resolve_dotted(
    data: dict[str, Any], key: str
) -> tuple[Any, bool]:
    parts = key.split(".")
    current: Any = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None, False
    return current, True


def get_effective_value(
    config: EffectiveConfiguration, key: str
) -> Any:
    if "." not in key:
        if key in config.environment:
            return config.environment[key]
        for _, section in [
            ("providers", config.providers),
            ("pipeline", config.pipeline),
            ("topics", config.topics),
        ]:
            if key in section:
                return section[key]
        return None

    top_level = key.split(".")[0]
    sections: list[dict[str, Any]] = []
    if top_level == "providers":
        sections = [config.providers]
    elif top_level == "pipeline":
        sections = [config.pipeline]
    elif top_level == "topics":
        sections = [config.topics]
    elif top_level == "sources":
        return None
    else:
        if key in config.environment:
            return config.environment[key]
        sections = [config.providers, config.pipeline, config.topics]

    for section in sections:
        found, ok = _resolve_dotted(section, key)
        if ok:
            return found

    return None


def set_effective_value(
    config: EffectiveConfiguration,
    key: str,
    value: Any,
) -> None:
    parts = key.split(".")

    if len(parts) == 1:
        if key in config.environment:
            config.environment[key] = value
            return
        config.providers[key] = value
        return

    target: dict[str, Any]
    top_level = parts[0]
    if top_level == "providers":
        target = config.providers
    elif top_level == "pipeline":
        target = config.pipeline
    elif top_level == "topics":
        target = config.topics
    else:
        target = config.providers

    current = target
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


def unset_effective_value(
    config: EffectiveConfiguration,
    key: str,
) -> None:
    parts = key.split(".")

    if len(parts) == 1:
        config.environment.pop(key, None)
        config.providers.pop(key, None)
        config.pipeline.pop(key, None)
        config.topics.pop(key, None)
        return

    top_level = parts[0]
    if top_level == "providers":
        target = config.providers
    elif top_level == "pipeline":
        target = config.pipeline
    elif top_level == "topics":
        target = config.topics
    else:
        return

    current = target
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            return
        current = current[part]

    if isinstance(current, dict):
        current.pop(parts[-1], None)
