"""谱面下载：索引查询、别名解析、单曲 .adx 提取与发送。"""

from __future__ import annotations

import asyncio
import base64
import html
import re
import time
import unicodedata
from collections.abc import Callable
from pathlib import Path
from typing import Any

from nonebot import get_driver, on_command, on_regex
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent
from nonebot.log import logger
from nonebot.params import CommandArg, RegexGroup

from . import alias as alias_mod
from . import index as chart_index
from .config import ChartConfig, load_config

CFG = load_config()

# ---------------------------------------------------------------------------
# 全局状态：索引与 music_data 只在首次使用时于线程中加载
# ---------------------------------------------------------------------------

_index: dict[str, Any] | None = None
_song_db: dict[str, dict[str, Any]] = {}
_load_error = ""
_load_lock: asyncio.Lock | None = None

_alias = alias_mod.AliasStore(
    CFG.alias_cache,
    api_url=CFG.alias_api,
    timeout=CFG.alias_timeout,
    local_path=CFG.alias_local,
)


class PendingSelections:
    """带 TTL 的待选列表，避免过期选择长期占用内存。"""

    def __init__(self, ttl: float = CFG.pending_ttl, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.ttl = max(1.0, float(ttl))
        self._clock = clock
        self._data: dict[str, tuple[float, list[dict[str, Any]]]] = {}

    def _prune(self, now: float) -> None:
        expired = [key for key, (expires, _items) in self._data.items() if expires <= now]
        for key in expired:
            self._data.pop(key, None)

    def put(self, key: str, items: list[dict[str, Any]]) -> None:
        now = self._clock()
        self._prune(now)
        self._data[key] = (now + self.ttl, list(items))

    def pop(self, key: str) -> list[dict[str, Any]] | None:
        self._prune(self._clock())
        item = self._data.pop(key, None)
        return item[1] if item else None

    def peek(self, key: str) -> list[dict[str, Any]] | None:
        self._prune(self._clock())
        item = self._data.get(key)
        return item[1] if item else None

    def __len__(self) -> int:
        self._prune(self._clock())
        return len(self._data)


_pending = PendingSelections(CFG.pending_ttl)
_alias_pending = PendingSelections(CFG.pending_ttl)


# ---------------------------------------------------------------------------
# 加载
# ---------------------------------------------------------------------------


def _load_music_data(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    if not path.is_file():
        logger.warning("chart: CHART_MUSIC_DATA 不存在：%s（按无 ID 映射运行）", path)
        return {}
    import json

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("chart: 读取 music_data 失败：%r", exc)
        return {}
    if isinstance(raw, dict):
        raw = raw.get("songs", [])
    if not isinstance(raw, list):
        logger.warning("chart: music_data 格式不是列表，已忽略")
        return {}
    database: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        song_id = item.get("id")
        title = item.get("title")
        if song_id is None or not isinstance(title, str) or not title:
            continue
        database[str(song_id)] = item
    return database


def _load_blocking(cfg: ChartConfig) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    index = chart_index.load(cfg.index_cache, cfg.versions_dir)
    return index, _load_music_data(cfg.music_data)


async def ensure_loaded(cfg: ChartConfig = CFG) -> str:
    """确保索引已加载（在线程中读盘）；返回空字符串表示成功。"""
    global _index, _song_db, _load_error, _load_lock

    if _index is not None:
        return ""
    if _load_lock is None:
        _load_lock = asyncio.Lock()
    async with _load_lock:
        if _index is not None:
            return ""
        try:
            index, songs = await asyncio.to_thread(_load_blocking, cfg)
        except chart_index.ChartLibraryError as exc:
            _load_error = str(exc)
            logger.warning("chart: 谱面库不可用：%s", exc)
            return _load_error
        except Exception as exc:  # pragma: no cover - 防御性兜底
            _load_error = f"谱面索引加载失败：{exc.__class__.__name__}: {exc}"
            logger.exception("chart: failed to load index")
            return _load_error

        _index = index
        _song_db = songs
        _load_error = ""
        _alias.set_song_db(_song_db)
        logger.info("chart: index ready — %s", chart_index.stats(index))
        if songs:
            logger.info("chart: loaded %s songs from music_data", len(songs))
    return ""


def _song_title(query: str) -> str | None:
    """数字 ID / 精确曲名 -> 曲名。"""
    q = unicodedata.normalize("NFC", query).strip()
    if not q:
        return None
    if q.isdigit() and q in _song_db:
        return str(_song_db[q].get("title", "")) or None
    lowered = q.lower()
    for song in _song_db.values():
        title = str(song.get("title", ""))
        if unicodedata.normalize("NFC", title).lower() == lowered:
            return title
    return None


async def _ensure_alias() -> None:
    try:
        await _alias.load()
    except Exception:  # pragma: no cover - AliasStore 内部已吞掉网络错误
        logger.exception("chart: failed to load aliases")
    _alias.set_song_db(_song_db)


def _event_key(event: MessageEvent) -> str:
    group_id = event.group_id if isinstance(event, GroupMessageEvent) else 0
    return f"{event.user_id}:{group_id}"


# ---------------------------------------------------------------------------
# 文件发送：file:// 仅在配置了 NapCat 挂载且映射文件真实存在时使用
# ---------------------------------------------------------------------------


def napcat_file_uri(cache_path: Path, mount: str) -> str:
    """返回 NapCat 可读的 ``file://`` URI；不可用时返回空字符串。"""
    mount = (mount or "").strip()
    if not mount:
        return ""
    target = Path(mount).expanduser() / Path(cache_path).name
    if not target.is_file():
        return ""
    return f"file://{target}"


async def _upload(bot: Bot, event: MessageEvent, file: str, name: str) -> None:
    group_id = getattr(event, "group_id", None)
    if group_id is not None:
        await bot.call_api("upload_group_file", group_id=group_id, file=file, name=name)
    else:
        await bot.call_api("upload_private_file", user_id=event.user_id, file=file, name=name)


async def deliver_file(
    bot: Bot,
    event: MessageEvent,
    cache_path: Path,
    display_name: str,
    cfg: ChartConfig = CFG,
) -> None:
    """优先 file://，否则 base64；两者都失败时抛出最后一次异常。"""
    uri = napcat_file_uri(cache_path, cfg.napcat_mount)
    if uri:
        try:
            await _upload(bot, event, uri, display_name)
            logger.info("chart: sent %s via file://", cache_path.name)
            return
        except Exception as exc:
            logger.warning("chart: file:// 发送失败，回退 base64：%r", exc)

    raw = await asyncio.to_thread(cache_path.read_bytes)
    encoded = await asyncio.to_thread(base64.b64encode, raw)
    await _upload(bot, event, f"base64://{encoded.decode('ascii')}", display_name)
    logger.info("chart: sent %s via base64 (%.1f KB)", cache_path.name, len(raw) / 1024)


# ---------------------------------------------------------------------------
# 提取
# ---------------------------------------------------------------------------


def _do_extract(pack_path: Path, prefix: str, out_path: Path) -> None:
    import zipfile

    prefix = prefix if prefix.endswith("/") else f"{prefix}/"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_name(f".{out_path.name}.tmp.{os_pid()}")
    try:
        with zipfile.ZipFile(pack_path, "r") as archive:
            members = [n for n in archive.namelist() if n.startswith(prefix) and not n.endswith("/")]
            if not members:
                raise chart_index.ChartLibraryError(
                    f"版本包 {pack_path.name} 中找不到曲目目录 {prefix.rstrip('/')}"
                )
            with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as out:
                for member in members:
                    out.writestr(member[len(prefix):], archive.read(member))
        tmp_path.replace(out_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def os_pid() -> int:
    import os

    return os.getpid()


def _safe_name(value: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", value).strip() or "chart"


def _pack_display(pack_name: str) -> str:
    return chart_index.pack_label(pack_name)


async def _extract_and_send(
    bot: Bot,
    event: MessageEvent,
    match: dict[str, Any],
    alias_hint: str = "",
    cfg: ChartConfig = CFG,
) -> None:
    pack_name = str(match["pack"])
    prefix = str(match["prefix"])
    song_folder = prefix.rstrip("/").split("/")[-1]
    song_title = chart_index.clean_title(song_folder).strip() or song_folder
    pack_label = _pack_display(pack_name)
    hint = f"{alias_hint} " if alias_hint else ""

    pack_path = cfg.versions_dir / pack_name
    if not pack_path.is_file():
        await chart_download.finish(
            f"版本包 {pack_name} 不存在于 {cfg.versions_dir}。请检查谱面库是否完整。"
        )

    cache_path = cfg.cache_dir / f"{_safe_name(f'{song_title}_{pack_label}')}.adx"
    display_name = f"{_safe_name(song_title)}.adx"

    if cache_path.is_file():
        await chart_download.send(f"{hint}「{song_title}」({pack_label}) 缓存命中，正在发送...")
        try:
            await deliver_file(bot, event, cache_path, display_name, cfg)
        except Exception:
            logger.exception("chart: 发送缓存文件失败：%s", cache_path)
            await chart_download.finish("缓存文件发送失败，请稍后重试。")
        return

    await chart_download.send(f"{hint}「{song_title}」({pack_label}) 正在提取，约需数秒...")
    try:
        await asyncio.to_thread(_do_extract, pack_path, prefix, cache_path)
    except chart_index.ChartLibraryError as exc:
        await chart_download.finish(str(exc))
    except Exception:
        logger.exception("chart: extraction failed: %s in %s", prefix, pack_name)
        await chart_download.finish(f"提取「{song_title}」失败，请稍后重试。")

    size_mb = cache_path.stat().st_size / (1024 * 1024)
    await chart_download.send(
        f"{hint}「{song_title}」({pack_label}) 提取完成 ({size_mb:.1f} MB)，正在上传..."
    )
    try:
        await deliver_file(bot, event, cache_path, display_name, cfg)
    except Exception:
        logger.exception("chart: 上传失败：%s", cache_path)
        await chart_download.finish(
            f"「{song_title}」上传失败，请稍后重试。\n文件已缓存，下次请求会直接发送。"
        )


# ---------------------------------------------------------------------------
# matchers
# ---------------------------------------------------------------------------

chart_download = on_regex(r"^[/]?谱面下载\s*(.*)", priority=5, block=True)
rebuild_index = on_command("重新索引", priority=5, block=True)
refresh_alias = on_command("刷新别名", priority=5, block=True)
pick_choice = on_regex(r"^(\d{1,2})$", priority=4, block=False)


@chart_download.handle()
async def _handle(bot: Bot, event: MessageEvent, args: tuple = RegexGroup()):
    query = html.unescape(unicodedata.normalize("NFC", (args[0] or ""))).strip()
    if not query:
        await chart_download.finish("用法：谱面下载 <id / 曲名 / 别名>\n示例：谱面下载 8")

    error = await ensure_loaded()
    if error:
        await chart_download.finish(f"谱面库未就绪：\n{error}")

    title = _song_title(query)
    alias_hint = ""
    if not title:
        await _ensure_alias()
        results = _alias.by_alias(query)
        if len(results) == 1:
            title = str(results[0].get("title", "")) or None
            alias_hint = f"别名「{results[0].get('alias', query)}」→"
        elif len(results) > 1:
            key = _event_key(event)
            _alias_pending.put(key, results)
            lines = [f"别名「{query}」匹配到多首歌曲："]
            for number, item in enumerate(results, 1):
                lines.append(f"  {number}. {item.get('title') or '(未知曲名)'}  (id {item.get('song_id')})")
            lines.append(f"请回复序号选择（{int(CFG.pending_ttl)}s 内有效）。")
            await chart_download.finish("\n".join(lines))

    matches = chart_index.search(_index or {}, title or query)
    if not matches and title:
        matches = chart_index.search(_index or {}, query)
    if not matches:
        await chart_download.finish(f"未找到与「{query}」匹配的谱面。")

    if len(matches) == 1:
        await _extract_and_send(bot, event, matches[0], alias_hint)
        return

    key = _event_key(event)
    _pending.put(key, matches)
    display = f"{alias_hint}「{title or query}」" if alias_hint else f"「{title or query}」"
    lines = [f"{display} 在多个版本包中找到："]
    for number, item in enumerate(matches, 1):
        lines.append(f"  {number}. {_pack_display(str(item['pack']))}  ({item['pack']})")
    lines.append(f"请回复序号选择（{int(CFG.pending_ttl)}s 内有效）。")
    await chart_download.finish("\n".join(lines))


@rebuild_index.handle()
async def _rebuild(arg=CommandArg()):  # noqa: B008 - NoneBot dependency marker
    global _index, _load_error
    text = arg.extract_plain_text().strip()
    if text != "确认":
        await rebuild_index.finish("重建索引会扫描全部 .adx，可能耗时。\n确认请发送：/重新索引 确认")

    try:
        index = await asyncio.to_thread(chart_index.build, CFG.versions_dir)
        await asyncio.to_thread(chart_index.save, index, CFG.index_cache)
    except chart_index.ChartLibraryError as exc:
        await rebuild_index.finish(f"索引重建失败：\n{exc}")
    except Exception:
        logger.exception("chart: index rebuild failed")
        await rebuild_index.finish("索引重建失败，请检查日志与谱面库权限。")

    _index = index
    _load_error = ""
    _alias.set_song_db(_song_db)
    await rebuild_index.finish(f"索引重建完成 — {chart_index.stats(index)}")


@refresh_alias.handle()
async def _refresh_alias():
    _alias.set_song_db(_song_db)
    ok, message = await _alias.refresh()
    if ok:
        await refresh_alias.finish(f"别名数据已刷新（{_alias.size} 个别名键）。")
    await refresh_alias.finish(message or "别名刷新失败。")


@pick_choice.handle()
async def _pick(bot: Bot, event: MessageEvent, args: tuple = RegexGroup()):
    key = _event_key(event)
    try:
        number = int((args[0] or "").strip())
    except ValueError:
        return

    options = _pending.pop(key)
    if options is not None:
        index = number - 1
        if not 0 <= index < len(options):
            await pick_choice.finish(f"序号无效 (1–{len(options)})。请重新搜索。")
        error = await ensure_loaded()
        if error:
            await pick_choice.finish(f"谱面库未就绪：\n{error}")
        await _extract_and_send(bot, event, options[index])
        return

    alias_options = _alias_pending.pop(key)
    if alias_options is None:
        return

    index = number - 1
    if not 0 <= index < len(alias_options):
        await pick_choice.finish(f"序号无效 (1–{len(alias_options)})。请重新搜索。")

    chosen = alias_options[index]
    title = str(chosen.get("title", ""))
    hint = f"别名「{chosen.get('alias', '')}」→"
    error = await ensure_loaded()
    if error:
        await pick_choice.finish(f"谱面库未就绪：\n{error}")

    matches = chart_index.search(_index or {}, title)
    if not matches:
        await pick_choice.finish(f"{hint}「{title}」在谱面索引中未找到。")
    if len(matches) == 1:
        await _extract_and_send(bot, event, matches[0], hint)
        return

    _pending.put(key, matches)
    lines = [f"{hint}「{title}」在多个版本包中找到："]
    for number, item in enumerate(matches, 1):
        lines.append(f"  {number}. {_pack_display(str(item['pack']))}  ({item['pack']})")
    lines.append(f"请回复序号选择（{int(CFG.pending_ttl)}s 内有效）。")
    await pick_choice.finish("\n".join(lines))


# ---------------------------------------------------------------------------
# 启动预热
# ---------------------------------------------------------------------------

_driver = get_driver()


@_driver.on_startup
async def _warmup() -> None:
    error = await ensure_loaded()
    if error:
        logger.warning("chart: 启动预热未完成 — %s", error)


__all__ = [
    "PendingSelections",
    "deliver_file",
    "ensure_loaded",
    "napcat_file_uri",
]
