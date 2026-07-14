from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ainews_config.fields import FIELD_REGISTRY, ConfigField, SecretClassification
from ainews_config.paths import ResolvedPaths

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


def load_dotenv(path: Path) -> tuple[dict[str, str], list[Diagnostic]]:
    env: dict[str, str] = {}
    diagnostics: list[Diagnostic] = []

    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return env, diagnostics
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
        return env, diagnostics

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

    return env, diagnostics


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
) -> dict[str, ValueProvenance]:
    provenance: dict[str, ValueProvenance] = {}
    for key, value in env.items():
        provenance[key] = ValueProvenance(
            key=key, source="env", raw_value=value
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


def load_all_configs(
    paths: ResolvedPaths,
    *,
    env_overrides: dict[str, str] | None = None,
) -> EffectiveConfiguration:
    all_diags: list[Diagnostic] = []
    all_provenance: dict[str, ValueProvenance] = {}

    env_file_path = paths.env_file.path
    dotenv, dotenv_diags = load_dotenv(env_file_path)
    all_diags.extend(dotenv_diags)

    merged_env = dict(dotenv)
    if env_overrides:
        merged_env.update(env_overrides)

    all_provenance.update(_build_provenance_from_env(dotenv))

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
        elif provenance_prefix == "pipeline" and isinstance(resolved_data, dict):
            pipeline_data = resolved_data
        elif provenance_prefix == "sources" and isinstance(resolved_data, list):
            sources_data = resolved_data
        elif provenance_prefix == "topics" and isinstance(resolved_data, dict):
            topics_data = resolved_data

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
