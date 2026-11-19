from __future__ import annotations

import base64
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest
from helpers import make_pack
from nonebot_plugin_chart_downloader import download as download_mod
from nonebot_plugin_chart_downloader.config import ChartConfig, load_config
from nonebot_plugin_chart_downloader.download import (
    PendingSelections,
    deliver_file,
    napcat_file_uri,
)
from nonebot_plugin_chart_downloader.index import ChartLibraryError


def _config(tmp_path: Path, **overrides) -> ChartConfig:
    base = load_config()
    defaults = dict(
        library_dir=tmp_path / "library",
        cache_dir=tmp_path / "cache",
        index_cache=tmp_path / "index.json",
        alias_cache=tmp_path / "aliases.json",
        alias_local=tmp_path / "local_aliases.json",
        alias_api="",
        napcat_mount="",
    )
    defaults.update(overrides)
    return replace(base, **defaults)


class FakeBot:
    def __init__(self, fail_first: bool = False) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.fail_first = fail_first

    async def call_api(self, action: str, **kwargs):
        self.calls.append((action, kwargs))
        if self.fail_first and len(self.calls) == 1:
            raise RuntimeError("file:// not readable")
        return {"message_id": 1}


class FakeEvent:
    group_id = 100000
    user_id = 100001


async def test_pending_ttl() -> None:
    now = [100.0]
    pending = PendingSelections(ttl=60, clock=lambda: now[0])
    pending.put("k", [{"pack": "p.adx", "prefix": "p/Song/"}])

    assert pending.peek("k") is not None
    assert len(pending) == 1
    now[0] = 159.9
    assert pending.pop("k") is not None

    pending.put("k", [{"pack": "p.adx", "prefix": "p/Song/"}])
    now[0] = 220.0
    assert pending.pop("k") is None
    assert len(pending) == 0


def test_napcat_uri_only_when_file_exists(tmp_path: Path) -> None:
    cache = tmp_path / "cache" / "Song_maimai.adx"
    cache.parent.mkdir()
    cache.write_bytes(b"payload")

    assert napcat_file_uri(cache, "") == ""
    assert napcat_file_uri(cache, str(tmp_path / "missing")) == ""

    mount = tmp_path / "mount"
    mount.mkdir()
    assert napcat_file_uri(cache, str(mount)) == ""
    (mount / cache.name).write_bytes(b"payload")
    assert napcat_file_uri(cache, str(mount)) == f"file://{mount / cache.name}"


async def test_deliver_without_mount_uses_base64(tmp_path: Path) -> None:
    cache = tmp_path / "cache" / "Song_maimai.adx"
    cache.parent.mkdir()
    payload = b"fake-adx-bytes"
    cache.write_bytes(payload)
    bot = FakeBot()

    await deliver_file(bot, FakeEvent(), cache, "Song.adx", _config(tmp_path))

    assert len(bot.calls) == 1
    action, kwargs = bot.calls[0]
    assert action == "upload_group_file"
    assert kwargs["group_id"] == 100000
    assert kwargs["name"] == "Song.adx"
    assert kwargs["file"].startswith("base64://")
    assert base64.b64decode(kwargs["file"].removeprefix("base64://")) == payload


async def test_deliver_prefers_mounted_file(tmp_path: Path) -> None:
    cache = tmp_path / "cache" / "Song_maimai.adx"
    cache.parent.mkdir()
    cache.write_bytes(b"payload")
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / cache.name).write_bytes(b"payload")
    bot = FakeBot()

    await deliver_file(
        bot,
        FakeEvent(),
        cache,
        "Song.adx",
        _config(tmp_path, napcat_mount=str(mount)),
    )

    assert bot.calls[0][1]["file"] == f"file://{mount / cache.name}"


async def test_deliver_falls_back_when_file_uri_fails(tmp_path: Path) -> None:
    cache = tmp_path / "cache" / "Song_maimai.adx"
    cache.parent.mkdir()
    cache.write_bytes(b"payload")
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / cache.name).write_bytes(b"payload")
    bot = FakeBot(fail_first=True)

    await deliver_file(
        bot,
        FakeEvent(),
        cache,
        "Song.adx",
        _config(tmp_path, napcat_mount=str(mount)),
    )

    assert len(bot.calls) == 2
    assert bot.calls[0][1]["file"].startswith("file://")
    assert bot.calls[1][1]["file"].startswith("base64://")


async def test_deliver_private_chat(tmp_path: Path) -> None:
    cache = tmp_path / "cache" / "Song.adx"
    cache.parent.mkdir()
    cache.write_bytes(b"payload")

    class PrivateEvent:
        user_id = 100002

    bot = FakeBot()
    await deliver_file(bot, PrivateEvent(), cache, "Song.adx", _config(tmp_path))
    assert bot.calls[0][0] == "upload_private_file"
    assert bot.calls[0][1]["user_id"] == 100002


def test_extract_single_song(tmp_path: Path) -> None:
    versions = tmp_path / "versions"
    pack = make_pack(versions / "01. maimai .adx", ["True Love Song", "Other"])
    out = tmp_path / "cache" / "True Love Song_maimai.adx"

    download_mod._do_extract(pack, "01. maimai/True Love Song/", out)

    with zipfile.ZipFile(out) as archive:
        assert sorted(archive.namelist()) == ["bg.png", "maidata.txt"]
    assert not list(out.parent.glob("*.tmp*"))


def test_extract_missing_prefix(tmp_path: Path) -> None:
    pack = make_pack(tmp_path / "p.adx", ["Song"])
    with pytest.raises(ChartLibraryError, match="找不到曲目目录"):
        download_mod._do_extract(pack, "01. maimai/Nope/", tmp_path / "out.adx")
