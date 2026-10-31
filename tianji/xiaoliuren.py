"""小六壬（大安/留连/速喜/赤口/小吉/空亡）。"""

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

from .sxtwl_compat import ZHI
from .bazi import _cn_month, _cn_day


ZHI_WX = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火",
    "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水",
}
WX_ORDER = ("木", "火", "土", "金", "水")

# 小六壬六宫
XLR_PALACES = [
    ("大安", "吉", "木", "东方", "身不动时，事事昌盛，求谋顺利，失物未远，病者无妨。"),
    ("留连", "凶", "水", "北方", "卒未归时，凡事拖延，事难成就，宜静待时机，不宜强求。"),
    ("速喜", "吉", "火", "南方", "人便至时，喜事临门，求财得财，谋事可成，宜主动出击。"),
    ("赤口", "凶", "金", "西方", "官事凶时，口舌是非，谨防争执，宜守不宜进。"),
    ("小吉", "吉", "木", "东方", "人来喜时，凡事和合，多吉多利，所谋皆遂，宜和不宜争。"),
    ("空亡", "凶", "土", "中央", "音信稀时，谋事落空，劳而无成，宜缓不宜急，静待转机。"),
]


def _zhi_index_from_text(text: str) -> int:
    """'午时' / '午' / '15' / '15:00' -> 时支索引(0-11)。"""
    text = (text or "").strip()
    for i, z in enumerate(ZHI):
        if text == z or text.startswith(z + "时"):
            return i
    m = re.search(r"(\d{1,2})", text)
    if m:
        return ((int(m.group(1)) + 1) // 2) % 12
    raise ValueError("无法识别时辰（可用 子时/午时 或 0-23 小时）")


def _split_tokens(arg: str):
    return [t for t in re.split(r"[\s,，、]+", arg.strip()) if t]


def xiaoliuren(arg: str = "") -> str:
    """小六壬起课。无参数用当前时间；支持 '3 5 午' 或 '2026-10-17 15:00'。"""
    now = datetime.now()
    now_lunar = Solar.fromDate(now).getLunar()
    lmonth = abs(now_lunar.getMonth())
    lday = now_lunar.getDay()
    used_desc = "现在"
    hour_index = ((now.hour + 1) // 2) % 12
    arg = (arg or "").strip()

    if arg:
        # 1) 公历日期（可带时间）
        m = re.search(r"(\d{4})\s*[-/年.]\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})", arg)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            hm = re.search(r"(\d{1,2})\s*:\s*(\d{1,2})", arg)
            hh, mi = (int(hm.group(1)), int(hm.group(2))) if hm else (now.hour, now.minute)
            if not (0 <= hh <= 23 and 0 <= mi <= 59):
                raise ValueError("时间超出范围")
            solar = Solar.fromYmdHms(y, mo, d, hh, mi, 0)
            lunar = solar.getLunar()
            lmonth, lday = abs(lunar.getMonth()), lunar.getDay()
            hour_index = ((hh + 1) // 2) % 12
            used_desc = f"{y}-{mo:02d}-{d:02d} {hh:02d}:{mi:02d}"
        else:
            # 2) 农历月 日 [时辰]
            tokens = _split_tokens(arg)
            if len(tokens) < 2:
                raise ValueError("用法: 小六壬 / 小六壬 3 5 午 / 小六壬 农历三月初五 午时")
            month = _cn_month(tokens[0].rstrip("月"))
            day = _cn_day(tokens[1].rstrip("日号"))
            if not (1 <= month <= 12):
                raise ValueError("农历月份需在 1-12 之间")
            if not (1 <= day <= 30):
                raise ValueError("农历日期需在 1-30 之间")
            if len(tokens) >= 3:
                hour_index = _zhi_index_from_text(tokens[2])
            lmonth, lday = month, day
            used_desc = f"农历{month}月{day}日 {ZHI[hour_index]}时"

    # 月: 大安起正月顺数; 日: 月落宫起初一顺数; 时: 日落宫起子时顺数
    idx = (lmonth - 1) % 6
    idx = (idx + lday - 1) % 6
    idx = (idx + hour_index) % 6

    name, luck, wx, direction, desc = XLR_PALACES[idx]
    return "\n".join([
        f"【小六壬 · {name}】",
        f"起课：农历{lmonth}月{lday}日 {ZHI[hour_index]}时（{used_desc}）",
        f"落宫：{name}（{luck}）　五行：{wx}　方位：{direction}",
        f"断语：{desc}",
        "提示：一事一占，心诚则灵；结果仅供传统文化参考。",
    ])
