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


# ---------------------------------------------------------------------------
# Prior-version migration fixtures (0.9.0 -> 1.0.0)
# These demonstrate the migration interface pattern for testing.
# ---------------------------------------------------------------------------


class ConfigV090ToV100Migration(ConfigSchemaMigration):
    """Stub migration: config schema 0.9.0 -> 1.0.0.

    In a real migration, this would transform config files from
    the old format to the new format (e.g., rename fields, add
    required sections, update validation rules).
    """

    @property
    def id(self) -> str:
        return "config_0.9.0_to_1.0.0"

    @property
    def from_version(self) -> str:
        return "0.9.0"

    @property
    def to_version(self) -> str:
        return "1.0.0"

    @property
    def reversible(self) -> bool:
        return False

    def apply(
        self, staging_root: Path, context: dict[str, Any]
    ) -> MigrationReport:
        logger.info("Applying config migration 0.9.0 -> 1.0.0 (stub)")
        return MigrationReport(
            migration_id=self.id,
            success=True,
            message="Config schema migrated from 0.9.0 to 1.0.0",
            from_version=self.from_version,
            to_version=self.to_version,
        )

    def rollback(
        self, staging_root: Path, context: dict[str, Any]
    ) -> MigrationReport:
        return MigrationReport(
            migration_id=self.id,
            success=False,
            message="Rollback not supported for config 0.9.0 -> 1.0.0",
            from_version=self.to_version,
            to_version=self.from_version,
        )


class InstallMetadataV090ToV100Migration(InstallMetadataMigration):
    """Stub migration: install metadata schema 0.9.0 -> 1.0.0.

    In a real migration, this would transform the install-metadata.json
    format from the old schema to the new schema.
    """

    @property
    def id(self) -> str:
        return "install_metadata_0.9.0_to_1.0.0"

    @property
    def from_version(self) -> str:
        return "0.9.0"

    @property
    def to_version(self) -> str:
        return "1.0.0"

    @property
    def reversible(self) -> bool:
        return False

    def apply(
        self, staging_root: Path, context: dict[str, Any]
    ) -> MigrationReport:
        logger.info("Applying install metadata migration 0.9.0 -> 1.0.0 (stub)")
        return MigrationReport(
            migration_id=self.id,
            success=True,
            message="Install metadata schema migrated from 0.9.0 to 1.0.0",
            from_version=self.from_version,
            to_version=self.to_version,
        )

    def rollback(
        self, staging_root: Path, context: dict[str, Any]
    ) -> MigrationReport:
        return MigrationReport(
            migration_id=self.id,
            success=False,
            message="Rollback not supported for install metadata 0.9.0 -> 1.0.0",
            from_version=self.to_version,
            to_version=self.from_version,
        )


class ManifestV090ToV100Migration(ManifestSchemaMigration):
    """Stub migration: manifest schema 0.9.0 -> 1.0.0.

    In a real migration, this would transform the manifest.json
    format from the old schema to the new schema (e.g., add new
    section types, update checksum format).
    """

    @property
    def id(self) -> str:
        return "manifest_0.9.0_to_1.0.0"

    @property
    def from_version(self) -> str:
        return "0.9.0"

    @property
    def to_version(self) -> str:
        return "1.0.0"

    @property
    def reversible(self) -> bool:
        return False

    def apply(
        self, staging_root: Path, context: dict[str, Any]
    ) -> MigrationReport:
        logger.info("Applying manifest migration 0.9.0 -> 1.0.0 (stub)")
        return MigrationReport(
            migration_id=self.id,
            success=True,
            message="Manifest schema migrated from 0.9.0 to 1.0.0",
            from_version=self.from_version,
            to_version=self.to_version,
        )

    def rollback(
        self, staging_root: Path, context: dict[str, Any]
    ) -> MigrationReport:
        return MigrationReport(
            migration_id=self.id,
            success=False,
            message="Rollback not supported for manifest 0.9.0 -> 1.0.0",
            from_version=self.to_version,
            to_version=self.from_version,
        )


# Register the prior-version fixtures
CONFIG_MIGRATIONS.append(ConfigV090ToV100Migration())
INSTALL_METADATA_MIGRATIONS.append(InstallMetadataV090ToV100Migration())
MANIFEST_MIGRATIONS.append(ManifestV090ToV100Migration())


def get_all_migrations() -> list[BaseMigration]:
    """Return all registered migrations across all schema types."""
    all_migrations: list[BaseMigration] = []
    all_migrations.extend(CONFIG_MIGRATIONS)
    all_migrations.extend(INSTALL_METADATA_MIGRATIONS)
    all_migrations.extend(MANIFEST_MIGRATIONS)
    return all_migrations
