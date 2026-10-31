"""梅花易数：数字起卦与时间起卦。"""

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
from .xiaoliuren import _split_tokens, _zhi_index_from_text
from .bazi import _cn_month, _cn_day


# ---------------------------------------------------------------------------
# 梅花易数（时间起卦）
# ---------------------------------------------------------------------------
_MEIHUA_TRIGRAMS = {1: "乾", 2: "兑", 3: "离", 4: "震", 5: "巽", 6: "坎", 7: "艮", 8: "坤"}
_TRIGRAM_SYMBOL = {"乾": "☰", "兑": "☱", "离": "☲", "震": "☳",
                   "巽": "☴", "坎": "☵", "艮": "☶", "坤": "☷"}
_TRIGRAM_WX = {"乾": "金", "兑": "金", "离": "火", "震": "木",
               "巽": "木", "坎": "水", "艮": "土", "坤": "土"}
_TRIGRAM_BITS = {
    "乾": (1, 1, 1), "兑": (1, 1, 0), "离": (1, 0, 1), "震": (1, 0, 0),
    "巽": (0, 1, 1), "坎": (0, 1, 0), "艮": (0, 0, 1), "坤": (0, 0, 0),
}
_BITS_TRIGRAM = {v: k for k, v in _TRIGRAM_BITS.items()}
_TRIGRAM_ORDER = ["乾", "兑", "离", "震", "巽", "坎", "艮", "坤"]
_MEIHUA_NAMES = {
    "乾": ["乾为天", "天泽履", "天火同人", "天雷无妄", "天风姤", "天水讼", "天山遁", "天地否"],
    "兑": ["泽天夬", "兑为泽", "泽火革", "泽雷随", "泽风大过", "泽水困", "泽山咸", "泽地萃"],
    "离": ["火天大有", "火泽睽", "离为火", "火雷噬嗑", "火风鼎", "火水未济", "火山旅", "火地晋"],
    "震": ["雷天大壮", "雷泽归妹", "雷火丰", "震为雷", "雷风恒", "雷水解", "雷山小过", "雷地豫"],
    "巽": ["风天小畜", "风泽中孚", "风火家人", "风雷益", "巽为风", "风水涣", "风山渐", "风地观"],
    "坎": ["水天需", "水泽节", "水火既济", "水雷屯", "水风井", "坎为水", "水山蹇", "水地比"],
    "艮": ["山天大畜", "山泽损", "山火贲", "山雷颐", "山风蛊", "山水蒙", "艮为山", "山地剥"],
    "坤": ["地天泰", "地泽临", "地火明夷", "地雷复", "地风升", "地水师", "地山谦", "坤为地"],
}
_MEIHUA_64 = {
    (up, low): _MEIHUA_NAMES[up][i]
    for up in _TRIGRAM_ORDER
    for i, low in enumerate(_TRIGRAM_ORDER)
}
_SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
_KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}


def _wx_relation(ti_wx: str, yong_wx: str) -> tuple:
    if ti_wx == yong_wx:
        return "体用比和，吉", "吉"
    if _SHENG.get(yong_wx) == ti_wx:
        return "用生体，进益之象", "吉"
    if _SHENG.get(ti_wx) == yong_wx:
        return "体生用，泄气之象", "小凶"
    if _KE.get(ti_wx) == yong_wx:
        return "体克用，事在掌控", "小吉"
    if _KE.get(yong_wx) == ti_wx:
        return "用克体，防外压", "凶"
    return "体用平和", "平"


def meihua(arg: str = "") -> str:
    """梅花易数 · 时间起卦。无参数用现在；支持 '3 5 午' 或 '2026-10-17 15:00'。"""
    now = datetime.now()
    solar = Solar.fromDate(now)
    hour_index = ((now.hour + 1) // 2) % 12
    used_desc = "现在"
    arg = (arg or "").strip()

    if arg:
        m = re.search(r"(\d{4})\s*[-/年.]\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})", arg)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            hm = re.search(r"(\d{1,2})\s*:\s*(\d{1,2})", arg)
            hh, mi = (int(hm.group(1)), int(hm.group(2))) if hm else (now.hour, now.minute)
            if not (0 <= hh <= 23 and 0 <= mi <= 59):
                raise ValueError("时间超出范围")
            solar = Solar.fromYmdHms(y, mo, d, hh, mi, 0)
            hour_index = ((hh + 1) // 2) % 12
            used_desc = f"{y}-{mo:02d}-{d:02d} {hh:02d}:{mi:02d}"
        else:
            tokens = _split_tokens(arg)
            if len(tokens) < 2:
                raise ValueError("用法: 梅花 / 梅花 3 5 午 / 梅花 2026-10-17 15:00")
            month = _cn_month(tokens[0].rstrip("月"))
            day = _cn_day(tokens[1].rstrip("日号"))
            if len(tokens) >= 3:
                hour_index = _zhi_index_from_text(tokens[2])
            try:
                solar = Lunar.fromYmd(now.year, month, day).getSolar()
            except Exception:
                raise ValueError(f"农历日期不存在: {month}月{day}日")
            used_desc = f"农历{month}月{day}日 {ZHI[hour_index]}时"

    lunar = solar.getLunar()
    yz = lunar.getYearZhi()
    year_num = (yz if isinstance(yz, int) else ZHI.index(str(yz)[0])) + 1
    month_num = abs(lunar.getMonth())
    day_num = lunar.getDay()
    hour_num = hour_index + 1

    upper_i = (year_num + month_num + day_num) % 8 or 8
    lower_i = (year_num + month_num + day_num + hour_num) % 8 or 8
    moving = (year_num + month_num + day_num + hour_num) % 6 or 6

    upper = _MEIHUA_TRIGRAMS[upper_i]
    lower = _MEIHUA_TRIGRAMS[lower_i]
    ben = _MEIHUA_64[(upper, lower)]

    bits = list(_TRIGRAM_BITS[lower]) + list(_TRIGRAM_BITS[upper])
    hu_lower = _BITS_TRIGRAM[tuple(bits[1:4])]
    hu_upper = _BITS_TRIGRAM[tuple(bits[2:5])]
    hu = _MEIHUA_64[(hu_upper, hu_lower)]

    changed = bits[:]
    changed[moving - 1] = 1 - changed[moving - 1]
    bian_lower = _BITS_TRIGRAM[tuple(changed[0:3])]
    bian_upper = _BITS_TRIGRAM[tuple(changed[3:6])]
    bian = _MEIHUA_64[(bian_upper, bian_lower)]

    if moving <= 3:
        yong, ti = lower, upper
    else:
        yong, ti = upper, lower
    ti_wx, yong_wx = _TRIGRAM_WX[ti], _TRIGRAM_WX[yong]
    rel_text, rel_level = _wx_relation(ti_wx, yong_wx)
    advice = {
        "吉": "所问之事有助力，宜顺势推进；急事可成，缓事稳步向前。",
        "小吉": "事情在掌控中，但需主动争取；别拖太久。",
        "小凶": "易有耗泄，出力多而回报慢；先稳住基本盘。",
        "凶": "外部压力较大，宜守不宜攻；重要决定缓一缓。",
        "平": "体用平和，事在人为；按部就班即可。",
    }[rel_level]

    return "\n".join([
        "【梅花易数 · 时间起卦】",
        f"起卦：农历{month_num}月{day_num}日 {ZHI[hour_index]}时（{used_desc}）",
        f"上卦：{upper}{_TRIGRAM_SYMBOL[upper]}　下卦：{lower}{_TRIGRAM_SYMBOL[lower]}　动爻：{moving}爻",
        f"本卦：{ben}",
        f"互卦：{hu}",
        f"变卦：{bian}",
        f"体用：体卦{ti}{ti_wx}，用卦{yong}{yong_wx}｜{rel_text}（{rel_level}）",
        f"断语：{advice}",
        "※ 仅供传统文化参考，不构成决策建议。",
    ])
