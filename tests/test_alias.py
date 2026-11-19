from __future__ import annotations

import json
from pathlib import Path

import httpx
from nonebot_plugin_chart_downloader.alias import AliasStore


def _write_cache(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "updated_at": "2026-01-01T00:00:00+00:00",
                "aliases": [
                    {"SongID": 8, "Name": "True Love Song", "Alias": ["TLS", "真爱"]},
                    {"SongID": 9, "Name": "Other Song", "Alias": ["OTHER"]},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


async def test_load_cache_and_search(tmp_path: Path) -> None:
    cache = tmp_path / "aliases.json"
    _write_cache(cache)

    def no_network(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected network call: {request.url}")

    store = AliasStore(
        cache,
        api_url="https://api.example.invalid/aliases",
        transport=httpx.MockTransport(no_network),
    )
    await store.load()

    assert store.is_loaded()
    assert store.by_alias("tls") == [
        {"song_id": "8", "title": "True Love Song", "alias": "TLS"}
    ]
    assert store.by_alias("真")[0]["song_id"] == "8"
    assert store.by_alias("") == []
    assert store.by_alias("nothing") == []
    assert store.by_id(9) == ["OTHER"]


async def test_substring_deduplicates_song(tmp_path: Path) -> None:
    cache = tmp_path / "aliases.json"
    cache.write_text(
        json.dumps(
            {
                "aliases": [
                    {"SongID": 1, "Name": "A", "Alias": ["abc", "abd"]},
                    {"SongID": 2, "Name": "B", "Alias": ["abe"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    store = AliasStore(cache, api_url="")
    await store.load()

    results = store.by_alias("ab")
    assert [item["song_id"] for item in results] == ["1", "2"]


async def test_local_aliases_need_song_db_for_title(tmp_path: Path) -> None:
    cache = tmp_path / "aliases.json"
    cache.write_text(json.dumps({"aliases": [{"SongID": 8, "Name": "X", "Alias": ["ex"]}]}))
    (tmp_path / "local_aliases.json").write_text(
        json.dumps({"9": ["新曲别名"], "8": ["ex", "重复"]}, ensure_ascii=False),
        encoding="utf-8",
    )

    store = AliasStore(cache, api_url="")
    store.set_song_db({"9": {"title": "New Song"}, "8": {"title": "X"}})
    await store.load()

    hit = store.by_alias("新曲别名")
    assert hit == [{"song_id": "9", "title": "New Song", "alias": "新曲别名"}]
    assert len(store.by_alias("ex")) == 1


async def test_refresh_success_writes_cache(tmp_path: Path) -> None:
    cache = tmp_path / "nested" / "aliases.json"
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "code": 0,
                "content": [{"SongID": 42, "Name": "Fetched", "Alias": ["F"]}],
            },
        )

    store = AliasStore(
        cache,
        api_url="https://api.example.invalid/aliases",
        timeout=3,
        transport=httpx.MockTransport(handler),
    )
    await store.load()

    assert len(requests) == 1
    assert store.by_alias("f")[0]["song_id"] == "42"
    payload = json.loads(cache.read_text("utf-8"))
    assert payload["aliases"][0]["SongID"] == 42

    ok, message = await store.refresh()
    assert ok is True
    assert message == ""
    assert len(requests) == 2


async def test_refresh_timeout_keeps_cache(tmp_path: Path) -> None:
    cache = tmp_path / "aliases.json"
    _write_cache(cache)

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated timeout", request=request)

    store = AliasStore(
        cache,
        api_url="https://api.example.invalid/aliases",
        timeout=1,
        transport=httpx.MockTransport(timeout),
    )
    await store.load()
    assert store.size == 3
    ok, message = await store.refresh()

    assert ok is False
    assert "超时" in message
    assert store.size == 3


async def test_api_disabled_never_requests(tmp_path: Path) -> None:
    def no_network(request: httpx.Request) -> httpx.Response:
        raise AssertionError("network must stay disabled")

    store = AliasStore(
        tmp_path / "aliases.json",
        api_url="",
        transport=httpx.MockTransport(no_network),
    )
    await store.load()
    ok, message = await store.refresh()

    assert ok is False
    assert "未配置" in message
    assert store.size == 0
