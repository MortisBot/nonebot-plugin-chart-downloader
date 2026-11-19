"""谱面索引：扫描 AstroDX 版本包，构建 / 读写 JSON 索引。

索引格式（版本 1）::

    {
      "version": 1,
      "generated_at": "2026-01-01T00:00:00+00:00",
      "packs": ["01. maimai .adx"],
      "songs": {
        "true love song": [
          {"pack": "01. maimai .adx", "prefix": "01. maimai/True Love Song/"}
        ]
      }
    }

本模块只依赖标准库；不读环境变量、不依赖 NoneBot，方便离线测试。
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INDEX_VERSION = 1
INDEX_SUFFIX = ".adx"


class ChartLibraryError(RuntimeError):
    """谱面库不可用（目录不存在 / 没有可读版本包）。"""


def pack_label(filename: str) -> str:
    """``'01. maimai .adx'`` -> ``'maimai'``。"""
    name = filename.rsplit(".", 1)[0]
    return re.sub(r"^\d+[A-Z]?\.\s*", "", name).strip()


def clean_title(folder_name: str) -> str:
    """去掉曲绘文件夹的 ``[tag]`` 前缀并统一 NFC。"""
    name = re.sub(r"^\[.*?\]\s*", "", folder_name)
    return unicodedata.normalize("NFC", name)


def normalize_title(value: str) -> str:
    return unicodedata.normalize("NFC", value).strip().lower()


def _scan_pack(pack_path: Path) -> dict[str, list[dict[str, str]]]:
    songs: dict[str, list[dict[str, str]]] = {}
    with zipfile.ZipFile(pack_path, "r") as archive:
        seen: set[str] = set()
        for entry in archive.namelist():
            parts = entry.rstrip("/").split("/")
            if len(parts) < 2:
                continue
            folder = parts[1]
            if folder in seen:
                continue
            seen.add(folder)

            title = normalize_title(clean_title(folder))
            if not title:
                continue

            item = {
                "pack": pack_path.name,
                "prefix": f"{parts[0]}/{folder}/",
            }
            bucket = songs.setdefault(title, [])
            if item not in bucket:
                bucket.append(item)
    return songs


def build(versions_dir: str | Path) -> dict[str, Any]:
    """扫描目录内所有 ``.adx`` 并返回索引。

    Raises:
        ChartLibraryError: 目录不存在、没有 ``.adx`` 或全部无法读取。
    """
    root = Path(versions_dir)
    if not root.is_dir():
        raise ChartLibraryError(
            f"谱面库目录不存在：{root}。请设置 CHART_LIBRARY_DIR，"
            "并在其下的 versions/AstroDX/ 放置 AstroDX 导出的 .adx 版本包。"
        )

    pack_paths = sorted(
        (p for p in root.iterdir() if p.is_file() and p.suffix.lower() == INDEX_SUFFIX),
        key=lambda p: p.name,
    )
    if not pack_paths:
        raise ChartLibraryError(
            f"谱面库为空：{root} 下没有 .adx 版本包。"
            "请把 AstroDX 导出的 .adx 放进该目录（可用子目录布局见 README）。"
        )

    songs: dict[str, list[dict[str, str]]] = {}
    packs: list[str] = []
    for pack_path in pack_paths:
        try:
            scanned = _scan_pack(pack_path)
        except (OSError, zipfile.BadZipFile):
            continue
        if not scanned:
            continue
        packs.append(pack_path.name)
        for title, entries in scanned.items():
            bucket = songs.setdefault(title, [])
            for item in entries:
                if item not in bucket:
                    bucket.append(item)

    if not songs:
        raise ChartLibraryError(
            f"谱面库中没有可读曲目：{root}。请确认 .adx 是 AstroDX 版本包（zip），"
            "且包内目录结构为 <版本>/<曲名>/...。"
        )

    return {
        "version": INDEX_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "packs": packs,
        "songs": songs,
    }


def is_valid(index: Any) -> bool:
    if not isinstance(index, dict) or index.get("version") != INDEX_VERSION:
        return False
    songs = index.get("songs")
    if not isinstance(songs, dict):
        return False
    for title, entries in songs.items():
        if not isinstance(title, str) or not isinstance(entries, list):
            return False
        for entry in entries:
            if not isinstance(entry, dict):
                return False
            if not isinstance(entry.get("pack"), str) or not isinstance(entry.get("prefix"), str):
                return False
    return isinstance(index.get("packs"), list)


def save(index: dict[str, Any], cache_path: str | Path) -> None:
    """原子写 JSON（临时文件 + ``os.replace``）。"""
    path = Path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    data = json.dumps(index, ensure_ascii=False, indent=2) + "\n"
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def load(cache_path: str | Path, versions_dir: str | Path) -> dict[str, Any]:
    """读取 JSON 索引；缺失或损坏时扫描谱面库重建并回写缓存。"""
    path = Path(cache_path)
    if path.is_file():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cached = None
        if is_valid(cached):
            return cached

    index = build(versions_dir)
    try:
        save(index, path)
    except OSError:
        pass
    return index


def search(index: dict[str, Any], query: str) -> list[dict[str, str]]:
    """先精确匹配、再子串匹配；返回 ``[{pack, prefix}, ...]``。"""
    songs = index.get("songs") if isinstance(index, dict) else None
    if not isinstance(songs, dict):
        return []
    q = normalize_title(query)
    if not q:
        return []

    exact = songs.get(q)
    if isinstance(exact, list):
        return list(exact)

    results: list[dict[str, str]] = []
    for title, entries in songs.items():
        if q in title:
            results.extend(entries)
    return results


def stats(index: dict[str, Any]) -> str:
    songs = index.get("songs") if isinstance(index, dict) else None
    packs = index.get("packs") if isinstance(index, dict) else None
    song_count = len(songs) if isinstance(songs, dict) else 0
    pack_count = len(packs) if isinstance(packs, list) else 0
    return f"{song_count} songs across {pack_count} packs"
