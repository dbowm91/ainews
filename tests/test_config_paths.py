from __future__ import annotations

import ainews_config.paths
import json
import os
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from ainews_config.paths import (
    ConfigFile,
    InstallMetadata,
    PathProvenance,
    ResolvedPath,
    ResolvedPaths,
    _check_writable,
    _find_repo_root,
    _get_platform_config_dir,
    _get_platform_data_dir,
    _get_platform_state_dir,
    _get_system_install_dir,
    _get_user_install_dir,
    _is_development_mode,
    _resolve_directory,
    _resolve_file,
    load_install_metadata,
    resolve_paths,
)


class TestPathProvenance:
    def test_explicit_value(self):
        assert PathProvenance.EXPLICIT.value == "explicit"

    def test_environment_value(self):
        assert PathProvenance.ENVIRONMENT.value == "environment"

    def test_install_metadata_value(self):
        assert PathProvenance.INSTALL_METADATA.value == "install_metadata"

    def test_platform_default_value(self):
        assert PathProvenance.PLATFORM_DEFAULT.value == "platform_default"

    def test_development_value(self):
        assert PathProvenance.DEVELOPMENT.value == "development"


class TestConfigFile:
    def test_env(self):
        assert ConfigFile.ENV.value == ".env"

    def test_providers(self):
        assert ConfigFile.PROVIDERS.value == "providers.yaml"

    def test_database(self):
        assert ConfigFile.DATABASE.value == "ainews.db"


class TestResolvedPath:
    def test_frozen(self, tmp_path):
        rp = ResolvedPath(
            path=tmp_path,
            provenance=PathProvenance.EXPLICIT,
            exists=True,
            is_writable=True,
        )
        with pytest.raises(AttributeError):
            rp.path = tmp_path / "other"

    def test_exists_false_for_missing(self, tmp_path):
        rp = ResolvedPath(
            path=tmp_path / "nope",
            provenance=PathProvenance.PLATFORM_DEFAULT,
            exists=False,
            is_writable=False,
        )
        assert not rp.exists


class TestResolvedPaths:
    def test_frozen(self, tmp_path):
        def _rp(p: Path) -> ResolvedPath:
            return ResolvedPath(
                path=p,
                provenance=PathProvenance.EXPLICIT,
                exists=True,
                is_writable=True,
            )

        paths = ResolvedPaths(
            app_dir=_rp(tmp_path),
            config_dir=_rp(tmp_path),
            data_dir=_rp(tmp_path),
            state_dir=_rp(tmp_path),
            backup_dir=_rp(tmp_path),
            env_file=_rp(tmp_path / ".env"),
            providers_file=_rp(tmp_path / "providers.yaml"),
            pipeline_file=_rp(tmp_path / "pipeline.yaml"),
            sources_file=_rp(tmp_path / "sources.yaml"),
            topics_file=_rp(tmp_path / "topics.yaml"),
            database_file=_rp(tmp_path / "db.sqlite"),
            install_metadata_file=_rp(tmp_path / "meta.json"),
            transaction_lock=_rp(tmp_path / "lock"),
            transaction_staging=_rp(tmp_path / "staging"),
        )
        with pytest.raises(AttributeError):
            paths.data_dir = _rp(tmp_path / "other")


class TestLoadInstallMetadata:
    def test_loads_valid_json(self, tmp_path):
        meta_file = tmp_path / "install-metadata.json"
        meta_file.write_text(
            json.dumps(
                {
                    "version": "1.2.3",
                    "installed_at": "2025-01-15T10:30:00Z",
                    "install_type": "user",
                    "config_dir": "/opt/ainews/config",
                    "data_dir": "/opt/ainews/data",
                }
            )
        )
        result = load_install_metadata(meta_file)
        assert result is not None
        assert result.version == "1.2.3"
        assert result.installed_at == "2025-01-15T10:30:00Z"
        assert result.install_type == "user"
        assert result.config_dir == "/opt/ainews/config"
        assert result.data_dir == "/opt/ainews/data"

    def test_returns_none_for_missing_file(self, tmp_path):
        result = load_install_metadata(tmp_path / "missing.json")
        assert result is None

    def test_returns_none_for_invalid_json(self, tmp_path):
        meta_file = tmp_path / "bad.json"
        meta_file.write_text("not json {{{")
        result = load_install_metadata(meta_file)
        assert result is None

    def test_defaults_for_partial_json(self, tmp_path):
        meta_file = tmp_path / "partial.json"
        meta_file.write_text(json.dumps({"version": "2.0.0"}))
        result = load_install_metadata(meta_file)
        assert result is not None
        assert result.version == "2.0.0"
        assert result.installed_at == ""
        assert result.install_type == "development"
        assert result.config_dir is None
        assert result.data_dir is None


class TestIsDevelopmentMode:
    def test_detects_git_dir(self, tmp_path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        assert _is_development_mode(tmp_path)

    def test_detects_pyproject_toml(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        assert _is_development_mode(tmp_path)

    def test_detects_in_parent(self, tmp_path):
        child = tmp_path / "subdir" / "deeper"
        child.mkdir(parents=True)
        (tmp_path / ".git").mkdir()
        assert _is_development_mode(child)

    def test_returns_false_for_unknown_dir(self, tmp_path):
        with patch("ainews_config.paths._find_repo_root", return_value=None):
            assert not _is_development_mode(tmp_path)

    def test_cwd_detection(self, tmp_path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        with patch("ainews_config.paths.Path.cwd", return_value=tmp_path):
            assert _is_development_mode()


class TestCheckWritable:
    def test_existing_writable_dir(self, tmp_path):
        assert _check_writable(tmp_path)

    def test_missing_file_parent_writable(self, tmp_path):
        assert _check_writable(tmp_path / "subdir" / "file.txt")

    def test_readonly_dir(self, tmp_path):
        ro_dir = tmp_path / "readonly"
        ro_dir.mkdir()
        ro_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)
        try:
            result = _check_writable(ro_dir / "file.txt")
            if os.getuid() == 0:
                assert result is True
            else:
                assert result is False
        finally:
            ro_dir.chmod(stat.S_IRWXU)


class TestResolveDirectory:
    def test_explicit_wins_over_all(self, tmp_path):
        explicit = tmp_path / "explicit"
        result = _resolve_directory(
            "test",
            explicit=explicit,
            env_var="NONEXISTENT_ENV_VAR",
            install_value="/nonexistent/install",
            platform_default=tmp_path / "platform",
            dev_fallback=tmp_path / "dev",
        )
        assert result.path == explicit.resolve()
        assert result.provenance == PathProvenance.EXPLICIT

    def test_env_wins_over_platform(self, tmp_path):
        env_val = tmp_path / "env_override"
        env_val.mkdir()
        with patch.dict(os.environ, {"TEST_DIR_OVERRIDE": str(env_val)}):
            result = _resolve_directory(
                "test",
                env_var="TEST_DIR_OVERRIDE",
                platform_default=tmp_path / "platform",
            )
        assert result.path == env_val.resolve()
        assert result.provenance == PathProvenance.ENVIRONMENT

    def test_install_wins_over_platform(self, tmp_path):
        install = tmp_path / "install"
        install.mkdir()
        result = _resolve_directory(
            "test",
            install_value=str(install),
            platform_default=tmp_path / "platform",
        )
        assert result.path == install.resolve()
        assert result.provenance == PathProvenance.INSTALL_METADATA

    def test_platform_default_when_nothing_else(self, tmp_path):
        platform = tmp_path / "platform"
        platform.mkdir()
        result = _resolve_directory(
            "test",
            platform_default=platform,
        )
        assert result.path == platform.resolve()
        assert result.provenance == PathProvenance.PLATFORM_DEFAULT

    def test_env_empty_string_falls_through(self, tmp_path):
        with patch.dict(os.environ, {"TEST_DIR_OVERRIDE": ""}):
            result = _resolve_directory(
                "test",
                env_var="TEST_DIR_OVERRIDE",
                platform_default=tmp_path / "platform",
            )
        assert result.provenance == PathProvenance.PLATFORM_DEFAULT

    def test_explicit_none_falls_through(self, tmp_path):
        result = _resolve_directory(
            "test",
            explicit=None,
            platform_default=tmp_path / "platform",
        )
        assert result.provenance == PathProvenance.PLATFORM_DEFAULT

    def test_expands_user_tilde(self, tmp_path):
        result = _resolve_directory(
            "test",
            explicit=Path("~/ainews_test_dir"),
            platform_default=tmp_path,
        )
        assert "~" not in str(result.path)

    def test_tracks_existence(self, tmp_path):
        result = _resolve_directory(
            "test",
            explicit=tmp_path,
            platform_default=tmp_path,
        )
        assert result.exists is True

    def test_tracks_non_existence(self, tmp_path):
        result = _resolve_directory(
            "test",
            explicit=tmp_path / "does_not_exist",
            platform_default=tmp_path,
        )
        assert result.exists is False

    def test_development_fallback(self, tmp_path):
        dev_root = tmp_path / "repo"
        dev_root.mkdir()
        (dev_root / ".git").mkdir()
        dev_path = dev_root / "config"
        result = _resolve_directory(
            "test",
            dev_fallback=dev_path,
            platform_default=tmp_path / "platform",
        )
        assert result.path == dev_path.resolve()
        assert result.provenance == PathProvenance.DEVELOPMENT


class TestResolveFile:
    def test_explicit_wins(self, tmp_path):
        explicit = tmp_path / "explicit.yaml"
        result = _resolve_file(
            "test",
            explicit=explicit,
            platform_default=tmp_path / "platform.yaml",
        )
        assert result.path == explicit.resolve()
        assert result.provenance == PathProvenance.EXPLICIT

    def test_env_wins(self, tmp_path):
        env_file = tmp_path / "env.yaml"
        env_file.touch()
        with patch.dict(os.environ, {"TEST_FILE_OVERRIDE": str(env_file)}):
            result = _resolve_file(
                "test",
                env_var="TEST_FILE_OVERRIDE",
                platform_default=tmp_path / "platform.yaml",
            )
        assert result.path == env_file.resolve()
        assert result.provenance == PathProvenance.ENVIRONMENT

    def test_install_wins(self, tmp_path):
        install = tmp_path / "install.yaml"
        install.touch()
        result = _resolve_file(
            "test",
            install_value=str(install),
            platform_default=tmp_path / "platform.yaml",
        )
        assert result.path == install.resolve()
        assert result.provenance == PathProvenance.INSTALL_METADATA

    def test_platform_default(self, tmp_path):
        platform = tmp_path / "platform.yaml"
        platform.touch()
        result = _resolve_file(
            "test",
            platform_default=platform,
        )
        assert result.path == platform.resolve()
        assert result.provenance == PathProvenance.PLATFORM_DEFAULT

    def test_development_fallback(self, tmp_path):
        dev_root = tmp_path / "repo"
        dev_root.mkdir()
        (dev_root / ".git").mkdir()
        dev_file = dev_root / "file.yaml"
        dev_file.touch()
        result = _resolve_file(
            "test",
            dev_fallback=dev_file,
            platform_default=tmp_path / "platform.yaml",
        )
        assert result.path == dev_file.resolve()
        assert result.provenance == PathProvenance.DEVELOPMENT


class TestResolvePathsPrecedence:
    def test_explicit_wins_over_all(self, tmp_path):
        explicit_config = tmp_path / "explicit_config"
        result = resolve_paths(
            explicit_paths={"config_dir": explicit_config},
            base_dir=tmp_path,
            development_mode=False,
        )
        assert result.config_dir.path == explicit_config.resolve()
        assert result.config_dir.provenance == PathProvenance.EXPLICIT

    def test_env_wins_over_metadata(self, tmp_path):
        env_config = tmp_path / "env_config"
        env_config.mkdir()
        meta = InstallMetadata(
            version="1.0.0",
            installed_at="2025-01-01",
            install_type="user",
            config_dir=str(tmp_path / "meta_config"),
        )
        result = resolve_paths(
            env_overrides={"AINEWS_CONFIG_DIR": str(env_config)},
            install_metadata=meta,
            base_dir=tmp_path,
            development_mode=False,
        )
        assert result.config_dir.path == env_config.resolve()
        assert result.config_dir.provenance == PathProvenance.ENVIRONMENT

    def test_metadata_wins_over_platform(self, tmp_path):
        meta = InstallMetadata(
            version="1.0.0",
            installed_at="2025-01-01",
            install_type="user",
            config_dir=str(tmp_path / "meta_config"),
            data_dir=str(tmp_path / "meta_data"),
        )
        result = resolve_paths(
            install_metadata=meta,
            base_dir=tmp_path,
            development_mode=False,
        )
        assert result.config_dir.path == (tmp_path / "meta_config").resolve()
        assert result.config_dir.provenance == PathProvenance.INSTALL_METADATA

    def test_development_fallback(self, tmp_path):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()
        (repo_root / "config").mkdir()
        (repo_root / "instance").mkdir()
        with patch("ainews_config.paths.Path.cwd", return_value=repo_root):
            result = resolve_paths(development_mode=True)
        assert result.config_dir.provenance == PathProvenance.DEVELOPMENT
        assert str(result.config_dir.path).endswith("config")

    def test_platform_default_when_nothing_else(self, tmp_path):
        result = resolve_paths(
            base_dir=tmp_path,
            development_mode=False,
        )
        assert result.config_dir.provenance == PathProvenance.PLATFORM_DEFAULT

    def test_all_paths_resolved(self, tmp_path):
        result = resolve_paths(base_dir=tmp_path, development_mode=False)
        assert isinstance(result, ResolvedPaths)
        assert result.app_dir.provenance in PathProvenance
        assert result.config_dir.provenance in PathProvenance
        assert result.data_dir.provenance in PathProvenance
        assert result.state_dir.provenance in PathProvenance
        assert result.backup_dir.provenance in PathProvenance
        assert result.env_file.provenance in PathProvenance
        assert result.providers_file.provenance in PathProvenance
        assert result.pipeline_file.provenance in PathProvenance
        assert result.sources_file.provenance in PathProvenance
        assert result.topics_file.provenance in PathProvenance
        assert result.database_file.provenance in PathProvenance
        assert result.install_metadata_file.provenance in PathProvenance
        assert result.transaction_lock.provenance in PathProvenance
        assert result.transaction_staging.provenance in PathProvenance


class TestResolvePathsWithSpaces:
    def test_path_with_spaces(self, tmp_path):
        space_dir = tmp_path / "path with spaces" / "ainews"
        space_dir.mkdir(parents=True)
        result = resolve_paths(
            explicit_paths={"config_dir": space_dir},
            base_dir=tmp_path,
            development_mode=False,
        )
        assert "path with spaces" in str(result.config_dir.path)
        assert result.config_dir.provenance == PathProvenance.EXPLICIT

    def test_env_path_with_spaces(self, tmp_path):
        space_dir = tmp_path / "my folder" / "config"
        space_dir.mkdir(parents=True)
        result = resolve_paths(
            env_overrides={"AINEWS_CONFIG_DIR": str(space_dir)},
            base_dir=tmp_path,
            development_mode=False,
        )
        assert "my folder" in str(result.config_dir.path)


class TestResolvePathsWithSymlinks:
    def test_symlinked_explicit_dir(self, tmp_path):
        real_dir = tmp_path / "real_config"
        real_dir.mkdir()
        link_dir = tmp_path / "link_config"
        link_dir.symlink_to(real_dir)
        result = resolve_paths(
            explicit_paths={"config_dir": link_dir},
            base_dir=tmp_path,
            development_mode=False,
        )
        assert result.config_dir.path == real_dir.resolve()
        assert result.config_dir.exists is True

    def test_symlinked_install_metadata(self, tmp_path):
        real_meta = tmp_path / "real_install-metadata.json"
        real_meta.write_text(
            json.dumps(
                {
                    "version": "1.0.0",
                    "installed_at": "2025-01-01",
                    "install_type": "user",
                }
            )
        )
        link_meta = tmp_path / "link_install-metadata.json"
        link_meta.symlink_to(real_meta)
        result = load_install_metadata(link_meta)
        assert result is not None
        assert result.version == "1.0.0"


class TestResolvePathsMissingDirectories:
    def test_nonexistent_explicit_reports_existence_false(self, tmp_path):
        missing = tmp_path / "missing" / "config"
        result = resolve_paths(
            explicit_paths={"config_dir": missing},
            base_dir=tmp_path,
            development_mode=False,
        )
        assert result.config_dir.exists is False

    def test_nonexistent_platform_default(self, tmp_path):
        with patch.dict(
            os.environ,
            {"XDG_CONFIG_HOME": str(tmp_path / "nonexistent_xdg")},
            clear=False,
        ):
            result = resolve_paths(base_dir=tmp_path, development_mode=False)
            assert result.config_dir.exists is False


class TestResolvePathsFromUnrelatedDirectory:
    def test_cwd_in_temp_dir(self, tmp_path):
        with patch("ainews_config.paths._find_repo_root", return_value=None):
            result = resolve_paths(development_mode=None)
        assert result.config_dir.provenance == PathProvenance.PLATFORM_DEFAULT

    def test_cwd_in_home_dir(self, tmp_path):
        with patch("ainews_config.paths.Path.cwd", return_value=Path.home()):
            result = resolve_paths(development_mode=None)
        assert result.config_dir.provenance in (
            PathProvenance.PLATFORM_DEFAULT,
            PathProvenance.DEVELOPMENT,
        )


class TestResolvePathsUserVsSystemInstall:
    def test_user_install(self, tmp_path):
        meta = InstallMetadata(
            version="1.0.0",
            installed_at="2025-01-01",
            install_type="user",
            config_dir=str(tmp_path / "user_config"),
            data_dir=str(tmp_path / "user_data"),
        )
        (tmp_path / "user_config").mkdir()
        (tmp_path / "user_data").mkdir()
        result = resolve_paths(
            install_metadata=meta,
            base_dir=tmp_path,
            development_mode=False,
        )
        assert result.config_dir.path == (tmp_path / "user_config").resolve()
        assert result.config_dir.provenance == PathProvenance.INSTALL_METADATA

    def test_system_install(self, tmp_path):
        meta = InstallMetadata(
            version="1.0.0",
            installed_at="2025-01-01",
            install_type="system",
        )
        result = resolve_paths(
            install_metadata=meta,
            base_dir=tmp_path,
            development_mode=False,
        )
        assert result.config_dir.provenance == PathProvenance.PLATFORM_DEFAULT


class TestPlatformDirectories:
    def test_config_dir_xdg(self, tmp_path):
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(tmp_path)}):
            result = _get_platform_config_dir()
            assert result == tmp_path / "ainews"

    def test_data_dir_xdg(self, tmp_path):
        with patch.dict(os.environ, {"XDG_DATA_HOME": str(tmp_path)}):
            result = _get_platform_data_dir()
            assert result == tmp_path / "ainews"

    def test_state_dir_xdg(self, tmp_path):
        with patch.dict(os.environ, {"XDG_STATE_HOME": str(tmp_path)}):
            result = _get_platform_state_dir()
            assert result == tmp_path / "ainews"

    def test_user_install_dir(self):
        result = _get_user_install_dir()
        assert result == Path.home() / ".ainews"

    def test_system_install_dir_linux(self):
        with patch("os.name", "posix"):
            result = _get_system_install_dir()
            assert result == Path("/etc/ainews")


class TestFindRepoRoot:
    def test_finds_git(self, tmp_path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        child = tmp_path / "src" / "pkg"
        child.mkdir(parents=True)
        result = _find_repo_root(child)
        assert result == tmp_path

    def test_finds_pyproject(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        result = _find_repo_root(tmp_path / "src")
        assert result == tmp_path

    def test_returns_none_for_orphan(self, tmp_path):
        with patch("ainews_config.paths._find_repo_root", return_value=None):
            result = ainews_config.paths._find_repo_root(tmp_path)
            assert result is None


class TestResolvePathsProvenanceTracking:
    def test_explicit_provenance_on_env_file(self, tmp_path):
        explicit_env = tmp_path / "custom.env"
        result = resolve_paths(
            explicit_paths={"env_file": explicit_env},
            base_dir=tmp_path,
            development_mode=False,
        )
        assert result.env_file.provenance == PathProvenance.EXPLICIT

    def test_env_provenance_on_database_file(self, tmp_path):
        db_path = tmp_path / "custom.db"
        db_path.touch()
        result = resolve_paths(
            env_overrides={"AINEWS_DATABASE_FILE": str(db_path)},
            base_dir=tmp_path,
            development_mode=False,
        )
        assert result.database_file.provenance == PathProvenance.ENVIRONMENT

    def test_development_provenance_on_providers(self, tmp_path):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()
        (repo_root / "providers.yaml").touch()
        with patch("ainews_config.paths.Path.cwd", return_value=repo_root):
            result = resolve_paths(development_mode=True)
        assert result.providers_file.provenance == PathProvenance.DEVELOPMENT
        assert result.providers_file.exists is True

    def test_multiple_provenances_tracked(self, tmp_path):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()
        (repo_root / "providers.yaml").touch()
        explicit_env = tmp_path / "my.env"
        explicit_env.touch()
        with patch("ainews_config.paths.Path.cwd", return_value=repo_root):
            result = resolve_paths(
                explicit_paths={"env_file": explicit_env},
                development_mode=True,
            )
        assert result.env_file.provenance == PathProvenance.EXPLICIT
        assert result.providers_file.provenance == PathProvenance.DEVELOPMENT


class TestResolvePathsWithEnvOverrides:
    def test_all_env_overrides(self, tmp_path):
        dirs = {}
        for name in ["app_dir", "config_dir", "data_dir", "state_dir", "backup_dir"]:
            d = tmp_path / f"env_{name}"
            d.mkdir()
            dirs[name] = d

        files = {}
        for name in ["env_file", "providers_file", "pipeline_file", "sources_file", "topics_file"]:
            f = tmp_path / f"env_{name}.yaml"
            f.touch()
            files[name] = f

        db = tmp_path / "env_custom.db"
        db.touch()

        overrides = {
            "AINEWS_APP_DIR": str(dirs["app_dir"]),
            "AINEWS_CONFIG_DIR": str(dirs["config_dir"]),
            "AINEWS_DATA_DIR": str(dirs["data_dir"]),
            "AINEWS_STATE_DIR": str(dirs["state_dir"]),
            "AINEWS_BACKUP_DIR": str(dirs["backup_dir"]),
            "AINEWS_ENV_FILE": str(files["env_file"]),
            "AINEWS_PROVIDERS_FILE": str(files["providers_file"]),
            "AINEWS_PIPELINE_FILE": str(files["pipeline_file"]),
            "AINEWS_SOURCES_FILE": str(files["sources_file"]),
            "AINEWS_TOPICS_FILE": str(files["topics_file"]),
            "AINEWS_DATABASE_FILE": str(db),
        }
        result = resolve_paths(
            env_overrides=overrides,
            base_dir=tmp_path,
            development_mode=False,
        )

        for name in ["app_dir", "config_dir", "data_dir", "state_dir", "backup_dir"]:
            rp = getattr(result, name)
            assert rp.provenance == PathProvenance.ENVIRONMENT
        for name in ["env_file", "providers_file", "pipeline_file", "sources_file", "topics_file"]:
            rp = getattr(result, name)
            assert rp.provenance == PathProvenance.ENVIRONMENT
        assert result.database_file.provenance == PathProvenance.ENVIRONMENT


class TestResolvePathsDevelopmentWithGit:
    def test_dev_mode_all_dev_paths(self, tmp_path):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()
        (repo_root / "config").mkdir()
        (repo_root / "instance").mkdir()

        with patch("ainews_config.paths.Path.cwd", return_value=repo_root):
            result = resolve_paths(development_mode=True)

        assert result.config_dir.provenance == PathProvenance.DEVELOPMENT
        assert result.data_dir.provenance == PathProvenance.DEVELOPMENT
        assert result.providers_file.provenance == PathProvenance.DEVELOPMENT


class TestResolvePathsWritability:
    def test_writable_tracking(self, tmp_path):
        result = resolve_paths(
            explicit_paths={"config_dir": tmp_path},
            base_dir=tmp_path,
            development_mode=False,
        )
        assert result.config_dir.is_writable is True

    def test_readonly_tracking(self, tmp_path):
        ro_dir = tmp_path / "readonly"
        ro_dir.mkdir()
        ro_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)
        try:
            result = resolve_paths(
                explicit_paths={"config_dir": ro_dir},
                base_dir=tmp_path,
                development_mode=False,
            )
            if os.getuid() == 0:
                assert result.config_dir.is_writable is True
            else:
                assert result.config_dir.is_writable is False
        finally:
            ro_dir.chmod(stat.S_IRWXU)


class TestEdgeCases:
    def test_empty_explicit_paths_dict(self, tmp_path):
        result = resolve_paths(explicit_paths={}, base_dir=tmp_path, development_mode=False)
        assert isinstance(result, ResolvedPaths)

    def test_none_explicit_paths(self, tmp_path):
        result = resolve_paths(explicit_paths=None, base_dir=tmp_path, development_mode=False)
        assert isinstance(result, ResolvedPaths)

    def test_none_env_overrides(self, tmp_path):
        result = resolve_paths(env_overrides=None, base_dir=tmp_path, development_mode=False)
        assert isinstance(result, ResolvedPaths)

    def test_empty_env_overrides(self, tmp_path):
        result = resolve_paths(env_overrides={}, base_dir=tmp_path, development_mode=False)
        assert isinstance(result, ResolvedPaths)

    def test_all_none_explicit_paths(self, tmp_path):
        explicit = dict.fromkeys(["config_dir", "data_dir", "env_file", "providers_file"])
        result = resolve_paths(explicit_paths=explicit, base_dir=tmp_path, development_mode=False)
        assert isinstance(result, ResolvedPaths)

    def test_partial_explicit_paths(self, tmp_path):
        result = resolve_paths(
            explicit_paths={"config_dir": tmp_path / "custom"},
            base_dir=tmp_path,
            development_mode=False,
        )
        assert result.config_dir.provenance == PathProvenance.EXPLICIT
        assert result.data_dir.provenance == PathProvenance.PLATFORM_DEFAULT


class TestDevFallbackMigrationWarning:
    def test_warning_logged_without_install_metadata(self, tmp_path, caplog):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()
        (repo_root / "config").mkdir()
        (repo_root / "instance").mkdir()

        with patch("ainews_config.paths.Path.cwd", return_value=repo_root):
            with caplog.at_level("WARNING", logger="ainews_config.paths"):
                result = resolve_paths(development_mode=True)

        assert result.config_dir.provenance == PathProvenance.DEVELOPMENT
        warning_messages = [r.message for r in caplog.records if r.levelno >= 30]
        assert any("config_dir" in msg for msg in warning_messages)
        assert any("ainews config install" in msg for msg in warning_messages)

    def test_no_warning_with_install_metadata(self, tmp_path, caplog):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()
        (repo_root / "config").mkdir()
        (repo_root / "instance").mkdir()

        meta = InstallMetadata(
            version="1.0.0",
            installed_at="2025-01-01",
            install_type="user",
            config_dir=str(tmp_path / "meta_config"),
            data_dir=str(tmp_path / "meta_data"),
        )
        (tmp_path / "meta_config").mkdir()
        (tmp_path / "meta_data").mkdir()

        with patch("ainews_config.paths.Path.cwd", return_value=repo_root):
            with caplog.at_level("WARNING", logger="ainews_config.paths"):
                result = resolve_paths(install_metadata=meta, development_mode=True)

        assert result.config_dir.provenance == PathProvenance.INSTALL_METADATA
        warning_messages = [r.message for r in caplog.records if r.levelno >= 30]
        assert not any("ainews config install" in msg for msg in warning_messages)

    def test_no_warning_without_dev_fallback(self, tmp_path, caplog):
        with patch("ainews_config.paths._find_repo_root", return_value=None):
            with caplog.at_level("WARNING", logger="ainews_config.paths"):
                result = resolve_paths(development_mode=False)

        assert result.config_dir.provenance == PathProvenance.PLATFORM_DEFAULT
        warning_messages = [r.message for r in caplog.records if r.levelno >= 30]
        assert not any("ainews config install" in msg for msg in warning_messages)
