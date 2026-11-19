# nonebot-plugin-chart-downloader

从**你自己准备**的 AstroDX 版本包中查找谱面，并把单曲 `.adx` 发到群里。资源库不随仓库分发。

## 资源库长这样

```text
charts/
├── versions/AstroDX/01. maimai .adx   # 版本包（.adx 本质是 zip）
├── cache/                             # 提取缓存（插件写入）
└── music_data.json                    # 可选：按曲目 ID 搜索
```

把 `CHART_LIBRARY_DIR` 指到 `charts/` 即可。

## 命令

| 命令 | 说明 |
|:---:|:---|
| `谱面下载 <ID/曲名/别名>` | 查找谱面并发送；多结果时回复序号选择（60s 内有效） |
| `重新索引 确认` | 扫资源库重建 JSON 索引 |
| `刷新别名` | 从配置的别名 API 更新缓存 |

## 配置

| 变量 | 必填 | 默认 | 说明 |
|:---:|:---:|:---:|:---|
| `CHART_LIBRARY_DIR` | 是 | — | 资源库根目录 |
| `CHART_CACHE_DIR` | 否 | `<库>/cache` | 提取缓存 |
| `CHART_MUSIC_DATA` | 否 | 无 | `music_data.json` 路径 |
| `CHART_NAPCAT_MOUNT` | 否 | 无 | 设置且可用时用 `file://` 发送，否则 base64 |
| `CHART_ALIAS_API` | 否 | 无 | 别名 API，可关闭 |
| `CHART_PENDING_TTL` | 否 | `60` | 多结果选择超时秒数 |

## 发文件方式

- **推荐**：设置 `CHART_NAPCAT_MOUNT`（NapCat 容器里能看到的缓存目录），走 `file://`，快且不占 QPS
- 未设置时回退 `base64://`，大文件会慢

## 注意

- OneBot v11 + NapCat 文件上传接口
- 仓库**不含**任何谱面、曲绘、`music_data` 或别名数据；游戏数据的版权/使用条款请自行评估

## License

[MIT](./LICENSE)
