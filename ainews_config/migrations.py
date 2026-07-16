"""Stub migration implementations for config, install-metadata, and manifest schemas.

These demonstrate the migration interface pattern for each schema type.
Concrete migrations should be added here when schema versions change.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ainews_config.backup import BaseMigration, MigrationReport

logger = logging.getLogger(__name__)

# Current schema versions — bump these when making breaking changes
CURRENT_CONFIG_SCHEMA_VERSION = "1.0.0"
CURRENT_INSTALL_METADATA_SCHEMA_VERSION = "1.0.0"
CURRENT_MANIFEST_SCHEMA_VERSION = "1.0.0"

# Minimum supported source version for restore compatibility
MIN_SUPPORTED_SOURCE_VERSION = "1.0.0"


class ConfigSchemaMigration(BaseMigration):
    """Base class for configuration schema migrations.

    Config schema changes occur when new config fields are added,
    existing fields are renamed/removed, or validation rules change.
    """

    @property
    def id(self) -> str:
        raise NotImplementedError

    @property
    def from_version(self) -> str:
        raise NotImplementedError

    @property
    def to_version(self) -> str:
        raise NotImplementedError

    def apply(
        self, staging_root: Path, context: dict[str, Any]
    ) -> MigrationReport:
        raise NotImplementedError

    def rollback(
        self, staging_root: Path, context: dict[str, Any]
    ) -> MigrationReport:
        return super().rollback(staging_root, context)


class InstallMetadataMigration(BaseMigration):
    """Base class for install metadata schema migrations.

    Install metadata schema changes occur when the metadata JSON
    format changes (new required fields, renamed fields, etc.).
    """

    @property
    def id(self) -> str:
        raise NotImplementedError

    @property
    def from_version(self) -> str:
        raise NotImplementedError

    @property
    def to_version(self) -> str:
        raise NotImplementedError

    def apply(
        self, staging_root: Path, context: dict[str, Any]
    ) -> MigrationReport:
        raise NotImplementedError

    def rollback(
        self, staging_root: Path, context: dict[str, Any]
    ) -> MigrationReport:
        return super().rollback(staging_root, context)


class ManifestSchemaMigration(BaseMigration):
    """Base class for backup manifest schema migrations.

    Manifest schema changes occur when new fields are added to
    manifest.json or existing fields change format.
    """

    @property
    def id(self) -> str:
        raise NotImplementedError

    @property
    def from_version(self) -> str:
        raise NotImplementedError

    @property
    def to_version(self) -> str:
        raise NotImplementedError

    def apply(
        self, staging_root: Path, context: dict[str, Any]
    ) -> MigrationReport:
        raise NotImplementedError

    def rollback(
        self, staging_root: Path, context: dict[str, Any]
    ) -> MigrationReport:
        return super().rollback(staging_root, context)


# ---------------------------------------------------------------------------
# Concrete migration registry
# ---------------------------------------------------------------------------

# Registry of all known migrations, ordered by schema type and version.
# When adding a new migration, append it to the appropriate list.
CONFIG_MIGRATIONS: list[ConfigSchemaMigration] = []
INSTALL_METADATA_MIGRATIONS: list[InstallMetadataMigration] = []
MANIFEST_MIGRATIONS: list[ManifestSchemaMigration] = []


def get_all_migrations() -> list[BaseMigration]:
    """Return all registered migrations across all schema types."""
    all_migrations: list[BaseMigration] = []
    all_migrations.extend(CONFIG_MIGRATIONS)
    all_migrations.extend(INSTALL_METADATA_MIGRATIONS)
    all_migrations.extend(MANIFEST_MIGRATIONS)
    return all_migrations
