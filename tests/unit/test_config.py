"""Unit tests for Config - storage path safety and writability probing.

Covers the 2026-06-02 fixes:
- storage_path must create the dir ONCE and never recreate it (so an unmounted
  external volume isn't silently re-created on the boot drive).
- is_storage_writable() must actually probe write access (catches read-only /
  unmounted / permission-revoked volumes that still report healthy disk usage).
"""

import pytest
import yaml

from nvr.core.config import Config


def _write_config(tmp_path, storage_path):
    """Create a minimal config.yaml pointing at the given storage_path."""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml.dump({
        'recording': {'storage_path': str(storage_path)},
        'cameras': [],
    }))
    return Config(config_path=str(cfg_file))


@pytest.mark.unit
class TestStorageWritability:
    """is_storage_writable() probe."""

    def test_writable_path_returns_true(self, tmp_path):
        storage = tmp_path / "recordings"
        storage.mkdir()
        config = _write_config(tmp_path, storage)

        assert config.is_storage_writable() is True
        # Probe must clean up after itself
        assert not (storage / ".nvr_write_test").exists()

    def test_missing_path_returns_false(self, tmp_path):
        # Parent does not exist -> write_text raises FileNotFoundError (OSError)
        storage = tmp_path / "does_not_exist" / "deeper"
        config = _write_config(tmp_path, storage)

        assert config.is_storage_writable() is False

    def test_probe_does_not_create_directory(self, tmp_path):
        # is_storage_writable must not mkdir; a missing volume stays missing
        storage = tmp_path / "ghost"
        config = _write_config(tmp_path, storage)

        config.is_storage_writable()

        assert not storage.exists()


@pytest.mark.unit
class TestStoragePathMountSafety:
    """storage_path must not re-create the mountpoint on every access."""

    def test_creates_directory_on_first_access(self, tmp_path):
        storage = tmp_path / "recordings"
        config = _write_config(tmp_path, storage)

        result = config.storage_path

        assert result == storage
        assert storage.exists()

    def test_does_not_recreate_after_unmount(self, tmp_path):
        """Simulate the external volume unmounting: once the dir is gone, a
        subsequent storage_path access must NOT recreate it on the boot drive."""
        storage = tmp_path / "recordings"
        config = _write_config(tmp_path, storage)

        # First access creates it
        _ = config.storage_path
        assert storage.exists()

        # Volume "unmounts" -> directory disappears
        storage.rmdir()
        assert not storage.exists()

        # Subsequent access returns the path but must NOT recreate it
        result = config.storage_path
        assert result == storage
        assert not storage.exists(), "storage_path silently recreated the mountpoint"


@pytest.mark.unit
class TestConfigRobustness:
    """Malformed YAML must not crash startup; save must be atomic."""

    def test_malformed_yaml_does_not_crash(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("cameras: [unterminated\n  bad: : :\n")  # invalid YAML
        config = Config(config_path=str(cfg))  # must not raise
        assert isinstance(config._config, dict)

    def test_save_is_atomic_and_valid(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("recording:\n  storage_path: /tmp/x\ncameras: []\n")
        config = Config(config_path=str(cfg))
        config.set('web.port', 9999)
        config.save()

        # File is valid YAML with the new value, and no temp file was left behind
        reloaded = yaml.safe_load(cfg.read_text())
        assert reloaded['web']['port'] == 9999
        leftovers = [p.name for p in tmp_path.iterdir() if p.name != 'config.yaml']
        assert leftovers == [], f"temp files left behind: {leftovers}"
