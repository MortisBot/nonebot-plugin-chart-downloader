"""nonebot-plugin-chart-downloader：AstroDX 谱面查询、索引与单曲下载。"""

from nonebot.plugin import PluginMetadata

from . import download as download  # noqa: F401  （导入即注册 matcher）
from .config import ChartConfig, load_config

__plugin_meta__ = PluginMetadata(
    name="谱面下载",
    description=(
        "从本地的 AstroDX 版本包（.adx）中按 ID、曲名或社区别名查找谱面，"
        "提取单曲并用 file:// 或 base64 发送。"
    ),
    usage=(
        "谱面下载 <id/曲名/别名>：查找并发送谱面\n"
        "重新索引 确认：重建 JSON 索引\n"
        "刷新别名：从已配置的别名 API 更新缓存\n"
        "多结果时直接回复序号选择。"
    ),
    type="application",
    homepage="https://github.com/MortisBot/nonebot-plugin-chart-downloader",
    supported_adapters={"~onebot.v11"},
)

__all__ = ["ChartConfig", "load_config", "__plugin_meta__"]
