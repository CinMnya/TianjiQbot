# -*- coding: utf-8 -*-
"""配置：全部通过环境变量读取，不在代码中保存任何密钥。"""
import os

# QQ 开放平台机器人凭据（必填）
APPID = os.environ.get("TIANJI_APPID", "")
SECRET = os.environ.get("TIANJI_SECRET", "")

# 沙箱环境：QQ 开放平台沙箱机器人设为 1
IS_SANDBOX = os.environ.get("TIANJI_SANDBOX", "0") == "1"

# Markdown 回复：默认开启，失败自动回退纯文本
USE_MARKDOWN = os.environ.get("TIANJI_MARKDOWN", "1") == "1"
MARKDOWN_TEMPLATE_ID = os.environ.get("TIANJI_MARKDOWN_TEMPLATE", "")

# 群聊指令冷却（秒）
COOLDOWN_SECONDS = int(os.environ.get("TIANJI_COOLDOWN", "5"))
