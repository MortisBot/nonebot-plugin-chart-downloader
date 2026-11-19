# nonebot-plugin-chart-downloader

> 同系列插件与部署/架构文档：[`MortisBot/qqbot-plugins`](https://github.com/MortisBot/qqbot-plugins)（索引与文档仓）

从**用户自备**的 AstroDX 版本包中查询谱面，提取单曲 `.adx` 并通过 OneBot v11 发送。
支持按曲目 ID、曲名、社区别名查询，多版本命中时回复序号选择。

本仓库不附带任何谱面、曲绘、`music_data` 或别名数据；请自行准备并遵守相应资源的使用条款。

## 安装

```bash
nb plugin install nonebot-plugin-chart-downloader
```

或在 `pyproject.toml` 中加入 `nonebot-plugin-chart-downloader` 后安装，并在 NoneBot 配置中加载插件。

## 资源库布局

`CHART_LIBRARY_DIR` 指向一个本地目录（默认 `data/chart_library`）：

```text
<CHART_LIBRARY_DIR>/
├── versions/
│   └── AstroDX/
│       ├── 01. maimai .adx      # AstroDX 导出的版本包（zip）
│       └── 02. maimai PLUS .adx
├── cache/                       # 单曲缓存，插件自动创建
├── index.json                   # 索引缓存（CHART_INDEX_CACHE）
├── aliases.json                 # 别名远程缓存（CHART_ALIAS_CACHE）
└── local_aliases.json           # 可选：本地别名 {"歌曲ID": ["别名", ...]}
```

`.adx` 是 zip 包，包内目录应为 `<版本目录>/<曲名目录>/...`。插件只认
`versions/AstroDX/` 下的 `*.adx`；首次查询或发送 `重新索引 确认` 时会扫描并生成
JSON 索引（不再使用 pickle）。索引结构：

```json
{
  "version": 1,
  "generated_at": "2026-01-01T00:00:00+00:00",
  "packs": ["01. maimai .adx"],
  "songs": {"曲名（小写 NFC）": [{"pack": "01. maimai .adx", "prefix": "01. maimai/曲名/"}]}
}
```

`CHART_MUSIC_DATA` 可选，指向 `music_data.json`（`[{"id": "8", "title": "..."}]`）。
配置后可用数字 ID 查询，本地别名也能补上曲名；不配置则可直接用曲名或别名。

## 配置

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `CHART_LIBRARY_DIR` | `data/chart_library` | 资源库根目录；其下需有 `versions/AstroDX/` |
| `CHART_CACHE_DIR` | `<资源库>/cache` | 提取后的单曲 `.adx` 缓存目录 |
| `CHART_INDEX_CACHE` | `<资源库>/index.json` | JSON 索引缓存路径 |
| `CHART_MUSIC_DATA` | 空 | 可选的 `music_data.json` 路径；空=不做 ID 映射 |
| `CHART_ALIAS_API` | 公开别名 API | 别名 API 地址；设为空字符串=完全禁用联网 |
| `CHART_ALIAS_CACHE` | `<资源库>/aliases.json` | 别名缓存路径 |
| `CHART_ALIAS_TIMEOUT` | `15` | 别名 API 超时（秒） |
| `CHART_NAPCAT_MOUNT` | 空 | 可选：NapCat 能看到缓存目录的挂载路径 |
| `CHART_PENDING_TTL` | `60` | 多结果待选的有效期（秒） |

`local_aliases.json` 固定放在资源库根目录，格式为 `{"歌曲ID": ["别名1", "别名2"]}`，
会覆盖/补充远程别名。

## 命令

| 命令 | 说明 |
|---|---|
| `谱面下载 <id/曲名/别名>` | 查询谱面；唯一命中直接发送，多条命中列出候选 |
| `<序号>` | 候选存在时回复 `1`、`2`… 选择；过期后需重新查询 |
| `重新索引 确认` | 重新扫描 `.adx` 并原子写回 JSON 索引 |
| `刷新别名` | 从 `CHART_ALIAS_API` 拉取别名并更新缓存；API 为空时直接提示已禁用 |

查询顺序：数字 ID / 精确曲名 → 社区别名 → 索引子串匹配。别名命中多首时先选曲，
再按版本包选择；选择状态默认 60 秒过期。

## 发送方式：`file://` 与 base64

- 未设置 `CHART_NAPCAT_MOUNT`：读取缓存文件并以内联 `base64://` 发送。
- 设置了 `CHART_NAPCAT_MOUNT`：仅当 `CHART_NAPCAT_MOUNT/<缓存文件名>` **真实存在**时，
  才用 `file://` 发送；否则仍回退 base64。

`CHART_NAPCAT_MOUNT` 必须指向 NapCat 进程能读到的同一目录（容器内路径或宿主路径，
取决于部署方式）。挂载不存在、权限不足或路径写错时，插件会自动回退 base64，
不会因此丢消息，但大文件会明显变慢。

## 隐私

- 插件只读取本地 `.adx`、`music_data.json`、别名缓存与本地别名文件。
- 默认只在**首次无缓存加载**或执行 `刷新别名` 时访问一次公开别名 API；请求只包含
  API 地址本身，不包含群号、用户、消息或图片。把 `CHART_ALIAS_API` 设为空即可完全离线。
- 没有遥测、统计上报或第三方上传；发送谱面只经过你配置的 OneBot 实现。

## 维护与排障

- 提示「谱面库未就绪」：检查 `CHART_LIBRARY_DIR`、`versions/AstroDX/*.adx` 是否存在且可读；
  改完配置后发送 `重新索引 确认`。
- 索引损坏或版本升级：直接删除 `index.json`，下次查询会自动重建；也可手动重建。
- 别名 API 超时/限流：插件保留旧缓存并提示失败；可调大 `CHART_ALIAS_TIMEOUT`，
  或设 `CHART_ALIAS_API=""` 改用 `local_aliases.json`。
- 需要临时停用：从 NoneBot 配置中移除插件并重启，或清空 `CHART_LIBRARY_DIR` 使其明确报错。
- 磁盘占用主要来自 `cache/` 与版本包；可安全删除 `cache/`，下次按需重新提取。

## License

MIT
