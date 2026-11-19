"""测试用 NoneBot 初始化与合成谱面包工具。"""

from __future__ import annotations

import nonebot

# 插件在导入时注册 matcher，因此必须先初始化 NoneBot；不启动任何网络服务。
nonebot.init(driver="~none", command_start={"/"}, log_level="ERROR")
