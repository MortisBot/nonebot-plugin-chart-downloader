# nonebot-plugin-chart-downloader

_✨ 从自备的 AstroDX 版本包中查找谱面并发送 `.adx` 文件。 ✨_

<a href="./LICENSE"><img src="https://img.shields.io/github/license/MortisBot/nonebot-plugin-chart-downloader.svg" alt="license"></a>
<a href="https://pypi.python.org/pypi/nonebot-plugin-chart-downloader"><img src="https://img.shields.io/pypi/v/nonebot-plugin-chart-downloader.svg" alt="pypi"></a>
<img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="python">

## 安装

在 NoneBot2 项目根目录下执行：

```bash
nb plugin install nonebot-plugin-chart-downloader
```

或手动安装：

```bash
pip install nonebot-plugin-chart-downloader
```

并在 `pyproject.toml` 的 `[tool.nonebot]` 中追加：

```toml
plugins = ["nonebot_plugin_chart_downloader"]
```

## 配置

在 `.env` 中配置（环境变量名即配置项大写）：

| 配置项 | 必填 | 默认值 | 说明 |
|:---:|:---:|:---:|:---|
| `CHART_LIBRARY_DIR` | 是 | 空 | 谱面资源库根目录（内含 `versions/AstroDX/*.adx`） |
| `CHART_CACHE_DIR` | 否 | `<库>/cache` | 提取缓存目录 |
| `CHART_MUSIC_DATA` | 否 | 无 | `music_data.json`，用于按 ID 搜索 |
| `CHART_NAPCAT_MOUNT` | 否 | 无 | 设置且可用时走 `file://`，否则 base64 发送 |
| `CHART_ALIAS_API` | 否 | 无 | 社区别名 API（可关闭） |
| `CHART_PENDING_TTL` | 否 | `60` | 多结果选择的超时秒数 |

## 使用

| 命令 | 说明 |
|:---:|:---|
| `谱面下载 <ID/曲名/别名>` | 查找谱面；多个结果时回复序号选择 |
| `重新索引 确认` | 扫描资源库重建 JSON 索引 |
| `刷新别名` | 从配置的别名 API 更新缓存 |

资源库（`.adx`、曲绘、`music_data.json`）需自备，本仓库不附带任何游戏数据。

## 适配器

OneBot v11（`supported_adapters={"~onebot.v11"}`）。

## License

[MIT](./LICENSE)

> 维护模式：原项目已停止运营，本插件按 best-effort 维护，无 SLA。
