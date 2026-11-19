"""社区曲目别名：缓存优先，可显式刷新，可完全关闭。

别名来源是第三方公开 API（默认值见 ``config.DEFAULT_ALIAS_API``），
只在调用 ``refresh()`` 时访问网络；``CHART_ALIAS_API=""`` 时永不联网。
本模块不依赖 NoneBot；测试可注入 ``httpx.MockTransport``。
"""

from __future__ import annotations

import asyncio
import json
import logging
import unicodedata
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15.0


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFC", value).strip().lower()


class AliasStore:
    """别名索引：``alias -> [{song_id, title, alias}, ...]``。"""

    def __init__(
        self,
        cache_path: str | Path,
        *,
        api_url: str = "",
        timeout: float = DEFAULT_TIMEOUT,
        local_path: str | Path | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.cache_path = Path(cache_path)
        self.local_path = Path(local_path) if local_path else self.cache_path.with_name("local_aliases.json")
        self.api_url = (api_url or "").strip()
        try:
            self.timeout = max(1.0, float(timeout))
        except (TypeError, ValueError):
            self.timeout = DEFAULT_TIMEOUT
        self._transport = transport
        self._alias_index: dict[str, list[dict[str, Any]]] = {}
        self._song_db: dict[str, dict[str, Any]] = {}
        self._loaded = False
        self._last_error = ""
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ state
    def set_song_db(self, db: Mapping[str, Mapping[str, Any]]) -> None:
        """共享 ``music_data`` 曲目表，用于给本地别名补标题。"""
        self._song_db = {str(k): dict(v) for k, v in db.items()}
        if self._loaded:
            self._merge_local()

    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def last_error(self) -> str:
        return self._last_error

    @property
    def size(self) -> int:
        return len(self._alias_index)

    # ------------------------------------------------------------------- read
    def by_alias(self, query: str) -> list[dict[str, Any]]:
        """先精确、后子串匹配；子串结果按 song_id 去重。"""
        q = _normalize(query)
        if not q:
            return []
        exact = self._alias_index.get(q)
        if exact:
            return [dict(item) for item in exact]

        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        for alias, entries in self._alias_index.items():
            if q not in alias:
                continue
            for item in entries:
                song_id = str(item.get("song_id", ""))
                if song_id in seen:
                    continue
                seen.add(song_id)
                results.append(dict(item))
        return results

    def by_id(self, song_id: str | int) -> list[str]:
        target = str(song_id)
        aliases = {
            str(item["alias"])
            for entries in self._alias_index.values()
            for item in entries
            if str(item.get("song_id", "")) == target
        }
        return sorted(aliases)

    # ------------------------------------------------------------------ load
    async def load(self) -> None:
        """缓存优先加载；无缓存且 API 已配置时拉取一次。"""
        async with self._lock:
            if self._loaded:
                return
            if self.cache_path.is_file():
                self._load_from_file(self.cache_path)
            elif self.api_url:
                await self._refresh_locked()
            else:
                self._merge_local()
            self._loaded = True
            logger.info("chart alias: loaded %s keys (api=%s)", len(self._alias_index), bool(self.api_url))

    async def refresh(self) -> tuple[bool, str]:
        """强制从 API 刷新；返回 ``(是否成功, 给用户看的说明)``。"""
        async with self._lock:
            if not self.api_url:
                self._loaded = True
                return False, "别名 API 未配置（CHART_ALIAS_API 为空），已跳过刷新。"
            ok = await self._refresh_locked()
            self._loaded = True
            return ok, self._last_error

    # ---------------------------------------------------------------- internals
    def _load_from_file(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("chart alias: failed to read %s: %r", path, exc)
            self._merge_local()
            return

        if isinstance(data, dict) and isinstance(data.get("aliases"), list):
            self._merge_remote(data["aliases"])
        elif isinstance(data, list):
            self._merge_remote(data)
        else:
            logger.warning("chart alias: unexpected cache format in %s", path)
            self._merge_local()

    async def _refresh_locked(self) -> bool:
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout, connect=min(10.0, self.timeout)),
                transport=self._transport,
                follow_redirects=True,
            ) as client:
                response = await client.get(self.api_url)
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as exc:
            self._last_error = f"别名 API 请求超时（>{self.timeout:.0f}s）：{exc.__class__.__name__}"
            logger.warning("chart alias: %s", self._last_error)
            return False
        except (httpx.HTTPError, OSError, ValueError) as exc:
            self._last_error = f"别名 API 请求失败：{exc.__class__.__name__}: {exc}"
            logger.warning("chart alias: %s", self._last_error)
            return False

        content = self._extract_content(data)
        if content is None:
            self._last_error = "别名 API 返回了无法识别的数据。"
            logger.warning("chart alias: %s", self._last_error)
            return False
        if not content:
            self._last_error = "别名 API 返回空列表，保留现有数据。"
            return False

        self._write_cache(content)
        self._merge_remote(content)
        self._last_error = ""
        logger.info("chart alias: refreshed %s keys from API", len(self._alias_index))
        return True

    @staticmethod
    def _extract_content(data: Any) -> list[Any] | None:
        if isinstance(data, list):
            return data
        if not isinstance(data, Mapping):
            return None
        code = data.get("code")
        if code is not None and code != 0:
            logger.warning("chart alias: API returned code %s", code)
            return None
        content = data.get("content")
        return content if isinstance(content, list) else None

    def _write_cache(self, content: list[Any]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.cache_path.with_name(f".{self.cache_path.name}.tmp")
        payload = {"updated_at": _now_iso(), "aliases": content}
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False)
                handle.flush()
            tmp.replace(self.cache_path)
        except OSError as exc:
            logger.warning("chart alias: failed to write cache: %r", exc)
            tmp.unlink(missing_ok=True)

    def _merge_remote(self, entries: list[Any]) -> None:
        self._alias_index.clear()
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            song_id = entry.get("SongID", entry.get("song_id"))
            if song_id is None:
                continue
            title = str(entry.get("Name", entry.get("title", "")) or "")
            aliases = entry.get("Alias", entry.get("alias", []))
            if isinstance(aliases, str):
                aliases = [aliases]
            if not isinstance(aliases, (list, tuple)):
                continue
            for alias in aliases:
                key = _normalize(str(alias))
                if not key:
                    continue
                self._alias_index.setdefault(key, []).append(
                    {"song_id": str(song_id), "title": title, "alias": str(alias)}
                )
        self._merge_local()

    def _merge_local(self) -> None:
        if not self.local_path.is_file():
            return
        try:
            local = json.loads(self.local_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("chart alias: failed to read local aliases: %r", exc)
            return
        if not isinstance(local, Mapping):
            logger.warning("chart alias: local aliases must be an object")
            return

        for raw_song_id, aliases in local.items():
            song_id = str(raw_song_id)
            title = str(self._song_db.get(song_id, {}).get("title", "") or "")
            if isinstance(aliases, str):
                aliases = [aliases]
            if not isinstance(aliases, (list, tuple)):
                continue
            for alias in aliases:
                key = _normalize(str(alias))
                if not key:
                    continue
                existing = {item["song_id"] for item in self._alias_index.get(key, [])}
                if song_id in existing:
                    continue
                self._alias_index.setdefault(key, []).append(
                    {"song_id": song_id, "title": title, "alias": str(alias)}
                )


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")
