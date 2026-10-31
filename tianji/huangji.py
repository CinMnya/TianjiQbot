"""皇极经世（元会运世 · 值年卦）。"""

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

from .gua import gua_info, gua_symbol


# ---------------------------------------------------------------------------
# 皇极经世 · 值年卦
# ---------------------------------------------------------------------------
# 一元 = 12 会 = 360 运 = 4320 世 = 129600 年
# 1 会 = 30 运 = 10800 年 | 1 运 = 12 世 = 360 年 | 1 世 = 30 年
_HJ_EPOCH = 67017          # 一元起始：公元前 67017 年（通行推演值）
_HJ_HUI_ZHI = "子丑寅卯辰巳午未申酉戌亥"
_CN_ORD = ("一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
           "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八",
           "十九", "二十", "廿一", "廿二", "廿三", "廿四", "廿五", "廿六",
           "廿七", "廿八", "廿九", "三十")

# 十二会配十二辟卦
_HJ_HUI_GUA = [
    "地雷复", "地泽临", "地天泰", "雷天大壮", "泽天夬", "乾为天",
    "天风姤", "天山遁", "天地否", "风地观", "山地剥", "坤为地",
]

# 值年卦 60 卦序列：先天圆图去坎离震兑四正，自复卦起顺行
_HJ_YEAR_SEQ = [
    "地雷复", "山雷颐", "水雷屯", "风雷益", "火雷噬嗑", "泽雷随",
    "天雷无妄", "地火明夷", "山火贲", "水火既济", "风火家人", "雷火丰",
    "泽火革", "天火同人", "地泽临", "山泽损", "水泽节", "风泽中孚",
    "雷泽归妹", "火泽睽", "天泽履", "地天泰", "山天大畜", "水天需",
    "风天小畜", "雷天大壮", "火天大有", "泽天夬", "乾为天", "天风姤",
    "泽风大过", "火风鼎", "雷风恒", "巽为风", "水风井", "山风蛊",
    "地风升", "天水讼", "泽水困", "火水未济", "雷水解", "风水涣",
    "山水蒙", "地水师", "天山遁", "泽山咸", "火山旅", "雷山小过",
    "风山渐", "水山蹇", "艮为山", "地山谦", "天地否", "泽地萃",
    "火地晋", "雷地豫", "风地观", "水地比", "山地剥", "坤为地",
]


def huangji(arg: str = "") -> str:
    """皇极经世值年卦。参数: 年份（默认今年）。"""
    text = (arg or "").strip()
    now = datetime.now()
    m = re.search(r"(-?\d{3,4})", text)
    year = int(m.group(1)) if m else now.year
    if not (1 <= year <= 9999):
        raise ValueError("年份需在 1-9999 之间")

    idx = year + _HJ_EPOCH - 1
    hui = idx // 10800 % 12
    yun = idx % 10800 // 360
    shi = idx % 360 // 30
    nian = idx % 30

    hui_gua = _HJ_HUI_GUA[hui]
    year_gua = _HJ_YEAR_SEQ[(year - 1984) % 60]
    hg = gua_info(hui_gua)
    yg = gua_info(year_gua)

    try:
        ganzhi = Solar.fromYmd(year, 6, 1).getLunar().getYearInGanZhi()
    except Exception:
        ganzhi = ""

    lines = [
        f"【皇极经世 · 值年卦】{year}{ganzhi and ' ' + ganzhi + '年'}",
        f"元会运世：第{_CN_ORD[hui]}会（{_HJ_HUI_ZHI[hui]}会）· 第{_CN_ORD[yun]}运"
        f" · 第{_CN_ORD[shi]}世 · 第{_CN_ORD[nian]}年",
        f"会卦：{hui_gua}（{gua_symbol(hui_gua)}）",
        f"　　卦意：{hg['meaning']}",
        f"值年卦：{year_gua}（{gua_symbol(year_gua)}）",
        f"　　卦意：{yg['meaning']}",
        f"　　卦宫：{yg['palace']}宫（{yg['palace_wx']}）",
        "合参：会卦看大势，年卦看当年；两者相参，不以单卦定吉凶。",
        "※ 算法：一元十二会（129600 年），运 360 年、世 30 年递进；"
        "值年卦取先天圆图六十卦（去坎离震兑四正），甲子年配复卦，六十年一周。"
        "此为通行简化法，仅供传统文化参考。",
    ]
    return "\n".join(lines)
