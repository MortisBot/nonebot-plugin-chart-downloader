from __future__ import annotations

from pathlib import Path

from nonebot_plugin_chart_downloader.config import DEFAULT_ALIAS_API, load_config

_KEYS = [
    "CHART_LIBRARY_DIR",
    "CHART_CACHE_DIR",
    "CHART_INDEX_CACHE",
    "CHART_MUSIC_DATA",
    "CHART_ALIAS_API",
    "CHART_ALIAS_CACHE",
    "CHART_ALIAS_TIMEOUT",
    "CHART_NAPCAT_MOUNT",
    "CHART_PENDING_TTL",
]


def _clear(monkeypatch) -> None:
    for key in _KEYS:
        monkeypatch.delenv(key, raising=False)


def test_defaults_and_derived_paths(monkeypatch, tmp_path: Path) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("CHART_LIBRARY_DIR", str(tmp_path / "library"))
    cfg = load_config()

    assert cfg.library_dir == tmp_path / "library"
    assert cfg.versions_dir == tmp_path / "library" / "versions" / "AstroDX"
    assert cfg.cache_dir == tmp_path / "library" / "cache"
    assert cfg.index_cache == tmp_path / "library" / "index.json"
    assert cfg.alias_cache == tmp_path / "library" / "aliases.json"
    assert cfg.alias_local == tmp_path / "library" / "local_aliases.json"
    assert cfg.alias_api == DEFAULT_ALIAS_API
    assert cfg.alias_timeout == 15.0
    assert cfg.music_data is None
    assert cfg.napcat_mount == ""
    assert cfg.pending_ttl == 60.0


def test_overrides_and_disable(monkeypatch, tmp_path: Path) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("CHART_LIBRARY_DIR", str(tmp_path / "library"))
    monkeypatch.setenv("CHART_CACHE_DIR", str(tmp_path / "custom-cache"))
    monkeypatch.setenv("CHART_INDEX_CACHE", str(tmp_path / "custom-index.json"))
    monkeypatch.setenv("CHART_ALIAS_CACHE", str(tmp_path / "custom-alias.json"))
    monkeypatch.setenv("CHART_ALIAS_API", "")
    monkeypatch.setenv("CHART_ALIAS_TIMEOUT", "2.5")
    monkeypatch.setenv("CHART_MUSIC_DATA", str(tmp_path / "music_data.json"))
    monkeypatch.setenv("CHART_NAPCAT_MOUNT", "/mnt/napcat/cache")
    monkeypatch.setenv("CHART_PENDING_TTL", "15")
    cfg = load_config()

    assert cfg.cache_dir == tmp_path / "custom-cache"
    assert cfg.index_cache == tmp_path / "custom-index.json"
    assert cfg.alias_cache == tmp_path / "custom-alias.json"
    assert cfg.alias_api == ""
    assert cfg.alias_timeout == 2.5
    assert cfg.music_data == tmp_path / "music_data.json"
    assert cfg.napcat_mount == "/mnt/napcat/cache"
    assert cfg.pending_ttl == 15.0


def test_invalid_numbers_fall_back(monkeypatch, tmp_path: Path) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("CHART_LIBRARY_DIR", str(tmp_path))
    monkeypatch.setenv("CHART_PENDING_TTL", "not-a-number")
    monkeypatch.setenv("CHART_ALIAS_TIMEOUT", "oops")
    cfg = load_config()

    assert cfg.pending_ttl == 60.0
    assert cfg.alias_timeout == 15.0
