"""插件配置：所有路径与外部服务均由环境变量控制。

本模块只依赖标准库，方便单独测试，不需要初始化 NoneBot。

资源库布局（``CHART_LIBRARY_DIR`` 指向的目录）::

    <library>/
    ├── versions/AstroDX/*.adx   # 用户自备的 AstroDX 版本包（zip）
    ├── cache/                   # 单曲缓存（自动创建）
    ├── index.json               # 索引缓存（CHART_INDEX_CACHE）
    ├── aliases.json             # 别名远程缓存（CHART_ALIAS_CACHE）
    └── local_aliases.json       # 可选的本地别名（{song_id: [alias, ...]}）
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ALIAS_API = "https://www.yuzuchan.moe/api/maimaidx/maimaidxalias"
DEFAULT_PENDING_TTL = 60.0


def _env(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip()


def _env_path(name: str, default: Path) -> Path:
    raw = _env(name)
    return Path(raw).expanduser() if raw else default


def _env_ttl(name: str, default: float) -> float:
    raw = _env(name)
    if not raw:
        return default
    try:
        return max(1.0, float(raw))
    except ValueError:
        return default


@dataclass(frozen=True, slots=True)
class ChartConfig:
    """运行期配置（不可变）。"""

    library_dir: Path
    cache_dir: Path
    index_cache: Path
    alias_cache: Path
    alias_local: Path
    alias_api: str = ""
    alias_timeout: float = 15.0
    music_data: Path | None = None
    napcat_mount: str = ""
    pending_ttl: float = DEFAULT_PENDING_TTL

    @property
    def versions_dir(self) -> Path:
        return self.library_dir / "versions" / "AstroDX"


def load_config() -> ChartConfig:
    """从环境变量读取配置；空值表示禁用对应可选能力。"""
    library = _env_path("CHART_LIBRARY_DIR", Path("data") / "chart_library")
    alias_api = _env("CHART_ALIAS_API", DEFAULT_ALIAS_API)
    music_raw = _env("CHART_MUSIC_DATA")
    try:
        alias_timeout = max(1.0, float(_env("CHART_ALIAS_TIMEOUT") or 15.0))
    except ValueError:
        alias_timeout = 15.0
    return ChartConfig(
        library_dir=library,
        cache_dir=_env_path("CHART_CACHE_DIR", library / "cache"),
        index_cache=_env_path("CHART_INDEX_CACHE", library / "index.json"),
        alias_cache=_env_path("CHART_ALIAS_CACHE", library / "aliases.json"),
        alias_local=library / "local_aliases.json",
        alias_api=alias_api,
        alias_timeout=alias_timeout,
        music_data=Path(music_raw).expanduser() if music_raw else None,
        napcat_mount=_env("CHART_NAPCAT_MOUNT"),
        pending_ttl=_env_ttl("CHART_PENDING_TTL", DEFAULT_PENDING_TTL),
    )
