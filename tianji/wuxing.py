"""五行缺口分析（四柱五行分布与补益建议）。"""

import calendar
import hashlib
import io
import json
import math
import os
import random
import sys
import types
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from difflib import SequenceMatcher
from typing import List, Optional, Tuple

from lunar_python import Solar, Lunar

from .bazi import cast_chart, parse_birth_info
from .scenecommon import *  # noqa: F401,F403


# =====================================================================
# 五行缺口 / 幸运植物 / 八字改运（共用五行建议表）
# =====================================================================
_CB_WX_ADVICE = {
    "木": ("绿、青", "东方", "3、8", "绿檀、竹饰", "文教、园艺、纺织、文创",
           ["富贵竹", "文竹", "绿萝"]),
    "火": ("红、紫、橙", "南方", "2、7", "红绳、石榴石", "能源、餐饮、电子、演艺",
           ["红掌", "鸿运当头", "长寿花"]),
    "土": ("黄、棕、米", "本地/西南", "5、10", "黄水晶、陶瓷", "地产、建筑、农业、仓储",
           ["多肉", "金钱树", "发财树"]),
    "金": ("白、金、银", "西方", "4、9", "金银饰、白水晶", "金融、机械、五金、法律",
           ["白掌", "银柳", "金桔"]),
    "水": ("黑、蓝、灰", "北方", "1、6", "黑曜石、蓝宝石", "贸易、物流、水产、传媒",
           ["绿萝（水培）", "水仙", "碗莲"]),
}

_CB_WX_NAME = {"木": "木", "火": "火", "土": "土", "金": "金", "水": "水"}


def _cb_wx_report(wx: str, label: str) -> str:
    color, fang, num, acc, career, plants = _CB_WX_ADVICE[wx]
    return (
        f"补{wx}行（{label}）：\n"
        f"· 颜色：{color}（衣着、手机壳、钱包朝这个色靠）\n"
        f"· 方位：{fang}（办公桌、床头朝向）\n"
        f"· 数字：{num}　· 饰品：{acc}\n"
        f"· 行业：{career}\n"
        f"· 植物：{'、'.join(plants)}（放{fang}位最灵）"
    )


def _cb_chart_or_err(arg: str):
    if not (arg or "").strip():
        raise ValueError("请提供出生信息，例如：1990-05-20 14:30 男 北京")
    return cast_chart(parse_birth_info(arg))


def wuxingque(arg: str = "") -> str:
    """五行缺口。参数: 出生信息。"""
    c = _cb_chart_or_err(arg)
    wx = c["wuxing"]
    day_el = c["day_master"]["day_element"]
    missing = [k for k, v in wx.items() if v <= 0.6]
    weak = sorted(wx, key=wx.get)[:2]
    focus = missing[0] if missing else weak[0]
    lines = [
        "【五行缺口】",
        f"四柱：{' '.join(p['gan'] + p['zhi'] for p in c['pillars'])}　日主{c['day_master']['day_gan']}（{day_el}）",
        "五行分布：" + "　".join(f"{k}{v:.1f}" for k, v in wx.items()),
        f"判定：" + (f"缺{'、'.join(missing)}" if missing
                    else f"无明显缺失，偏弱为{'、'.join(weak)}"),
        "",
        _cb_wx_report(focus, "缺" if focus in missing else "偏弱"),
        "提示：五行以「补喜用」为准，缺什么未必补什么；更精确请看「改运」指令。",
        _SC_NOTE,
    ]
    return "\n".join(lines)
