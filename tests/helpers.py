"""合成 AstroDX 版本包的工具（不依赖 NoneBot）。"""

from __future__ import annotations

import zipfile
from pathlib import Path


def make_pack(path: Path, songs: list[str], root: str = "01. maimai") -> Path:
    """生成一个最小版本包：<root>/<song>/maidata.txt。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for song in songs:
            archive.writestr(f"{root}/{song}/maidata.txt", f"&title={song}\n")
            archive.writestr(f"{root}/{song}/bg.png", b"not-a-real-image")
    return path
