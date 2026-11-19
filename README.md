<div align="center">
  <a href="https://v2.nonebot.dev/store">
    <img src="https://raw.githubusercontent.com/fllesser/nonebot-plugin-template/refs/heads/resource/.docs/NoneBotPlugin.svg" width="310" alt="NoneBotPlugin">
  </a>

# nonebot-plugin-chart-downloader

_✨ 从自备 AstroDX 资源库查找并发送音游谱面 ✨_

[![LICENSE](https://img.shields.io/github/license/MortisBot/nonebot-plugin-chart-downloader.svg)](./LICENSE)
[![pypi](https://img.shields.io/pypi/v/nonebot-plugin-chart-downloader.svg)](https://pypi.python.org/pypi/nonebot-plugin-chart-downloader)
![python](https://img.shields.io/badge/python-3.10+-blue.svg)

</div>

## 📖 介绍

从**你自己准备**的 AstroDX 版本包中按 ID / 曲名 / 社区别名查找谱面，把单曲 `.adx` 发到群里。资源库与游戏数据不随仓库分发。

## 💿 安装

<details open>
<summary>使用 nb-cli 安装</summary>

在 NoneBot2 项目根目录下执行：

```bash
nb plugin install nonebot-plugin-chart-downloader --upgrade
```

国内网络可换镜像源：

```bash
nb plugin install nonebot-plugin-chart-downloader --upgrade -i "https://pypi.tuna.tsinghua.edu.cn/simple"
```

</details>

<details>
<summary>使用包管理器安装</summary>

在 NoneBot2 项目根目录下执行其一：

```bash
uv add nonebot-plugin-chart-downloader
# 或
pdm add nonebot-plugin-chart-downloader
# 或
poetry add nonebot-plugin-chart-downloader
```

直接装仓库主分支（PyPI 包发布前可用）：

```bash
uv add git+https://github.com/MortisBot/nonebot-plugin-chart-downloader@main
```

然后在 `pyproject.toml` 的 `[tool.nonebot]` 中追加：

```toml
plugins = ["nonebot_plugin_chart_downloader"]
```

</details>

## ⚙️ 配置

在 NoneBot2 项目的 `.env` 中配置（配置项即环境变量名，大写）：

| 配置项 | 必填 | 默认值 | 说明 |
|:---:|:---:|:---:|:---|
| `CHART_LIBRARY_DIR` | 是 | — | 资源库根目录（含 `versions/AstroDX/*.adx`） |
| `CHART_CACHE_DIR` | 否 | `<库>/cache` | 提取缓存目录 |
| `CHART_MUSIC_DATA` | 否 | 无 | `music_data.json`，用于按 ID 搜索 |
| `CHART_NAPCAT_MOUNT` | 否 | 无 | 设置且可用时走 `file://`，否则 base64 发送 |
| `CHART_ALIAS_API` | 否 | 无 | 社区别名 API，可关闭 |
| `CHART_PENDING_TTL` | 否 | `60` | 多结果选择超时秒数 |

## 🎉 使用

| 命令 | 权限 | 需要 @ | 范围 | 说明 |
|:---:|:---:|:---:|:---:|:---|
| `谱面下载 <ID/曲名/别名>` | 群员 | 否 | 群聊 | 查找并发送谱面；多结果回复序号选择 |
| `重新索引 确认` | 管理员 | 否 | 群聊 | 重建 JSON 索引 |
| `刷新别名` | 管理员 | 否 | 群聊 | 更新别名缓存 |

## 🔌 适配器

OneBot v11（`supported_adapters={"~onebot.v11"}`）。推荐设置 `CHART_NAPCAT_MOUNT` 走 `file://`；未设置时回退 base64（大文件较慢）。

## 📄 License

[MIT](./LICENSE) · 维护模式（best-effort，无 SLA）
