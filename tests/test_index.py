from __future__ import annotations

import json
from pathlib import Path

import pytest
from helpers import make_pack
from nonebot_plugin_chart_downloader import index as chart_index
from nonebot_plugin_chart_downloader.index import (
    ChartLibraryError,
    build,
    is_valid,
    load,
    normalize_title,
    pack_label,
    save,
    search,
    stats,
)


def _versions(tmp_path: Path) -> Path:
    versions = tmp_path / "versions" / "AstroDX"
    versions.mkdir(parents=True)
    make_pack(versions / "01. maimai .adx", ["True Love Song", "[DX] ガラクタ"])
    make_pack(versions / "02. DX .adx", ["True Love Song", "Oshama Scramble"], root="02. DX")
    return versions


def test_build_index_schema(tmp_path: Path) -> None:
    versions = _versions(tmp_path)
    index = build(versions)

    assert index["version"] == 1
    assert index["generated_at"]
    assert index["packs"] == ["01. maimai .adx", "02. DX .adx"]
    assert set(index["songs"]) == {
        "true love song",
        "ガラクタ",
        "oshama scramble",
    }
    assert index["songs"]["true love song"] == [
        {"pack": "01. maimai .adx", "prefix": "01. maimai/True Love Song/"},
        {"pack": "02. DX .adx", "prefix": "02. DX/True Love Song/"},
    ]
    assert index["songs"]["ガラクタ"][0]["prefix"] == "01. maimai/[DX] ガラクタ/"
    assert stats(index) == "3 songs across 2 packs"


def test_json_roundtrip_and_atomic_save(tmp_path: Path) -> None:
    versions = _versions(tmp_path)
    cache = tmp_path / "cache" / "index.json"
    index = build(versions)

    save(index, cache)
    assert json.loads(cache.read_text("utf-8"))["version"] == 1
    assert not list(cache.parent.glob("*.tmp*"))

    loaded = load(cache, versions)
    assert loaded == index
    assert is_valid(loaded)


def test_load_rebuilds_missing_or_corrupt_cache(tmp_path: Path) -> None:
    versions = _versions(tmp_path)
    cache = tmp_path / "index.json"

    rebuilt = load(cache, versions)
    assert cache.is_file()
    assert set(rebuilt["songs"]) == {"true love song", "ガラクタ", "oshama scramble"}

    cache.write_text("{ broken", encoding="utf-8")
    repaired = load(cache, versions)
    assert repaired["version"] == 1
    assert json.loads(cache.read_text("utf-8"))["version"] == 1


def test_load_uses_valid_cache_without_library(tmp_path: Path) -> None:
    versions = _versions(tmp_path)
    cache = tmp_path / "index.json"
    save(build(versions), cache)

    # 库被移走但缓存仍有效：不扫描、不报错
    loaded = load(cache, tmp_path / "missing")
    assert loaded["packs"] == ["01. maimai .adx", "02. DX .adx"]


def test_search_exact_and_substring() -> None:
    index = {
        "version": 1,
        "generated_at": "",
        "packs": ["p.adx"],
        "songs": {
            "true love song": [{"pack": "p.adx", "prefix": "p/True Love Song/"}],
            "true love song (dx)": [{"pack": "p.adx", "prefix": "p/True Love Song DX/"}],
            "other": [{"pack": "p.adx", "prefix": "p/Other/"}],
        },
    }

    assert search(index, "True Love Song") == [{"pack": "p.adx", "prefix": "p/True Love Song/"}]
    assert len(search(index, "true love")) == 2
    assert len(search(index, "  TRUE LOVE SONG  ")) == 1
    assert search(index, "  ") == []
    assert search(index, "") == []
    assert search({"songs": []}, "x") == []


def test_normalize_and_pack_label() -> None:
    assert normalize_title("  True Love  ") == "true love"
    assert pack_label("14. DX .adx") == "DX"
    assert pack_label("plain.adx") == "plain"


def test_missing_and_empty_library_errors(tmp_path: Path) -> None:
    with pytest.raises(ChartLibraryError, match="CHART_LIBRARY_DIR"):
        build(tmp_path / "nope")

    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ChartLibraryError, match="没有 .adx"):
        build(empty)

    with pytest.raises(ChartLibraryError, match="CHART_LIBRARY_DIR"):
        load(tmp_path / "index.json", tmp_path / "missing")


def test_corrupt_pack_is_skipped(tmp_path: Path) -> None:
    versions = tmp_path / "versions" / "AstroDX"
    versions.mkdir(parents=True)
    make_pack(versions / "01. maimai .adx", ["Good Song"])
    (versions / "02. broken .adx").write_bytes(b"not a zip")

    index = build(versions)
    assert index["packs"] == ["01. maimai .adx"]
    assert chart_index.search(index, "good song")
