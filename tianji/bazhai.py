"""八宅风水：命卦与宅卦匹配、东西四命。"""

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

from .sxtwl_compat import GAN, ZHI
from .bazi import parse_birth_info, cast_chart


# ---------------------------------------------------------------------------
# 八宅风水（命卦 + 八方吉凶）
# ---------------------------------------------------------------------------
_MING_GUA = {1: "坎", 2: "坤", 3: "震", 4: "巽", 5: "中", 6: "乾", 7: "兑", 8: "艮", 9: "离"}
_SIT_GUA = {"北": 1, "南": 9, "东": 3, "西": 7, "东南": 4, "西北": 6, "东北": 8, "西南": 2}
_OPPOSITE = {"北": "南", "南": "北", "东": "西", "西": "东",
             "东南": "西北", "西北": "东南", "东北": "西南", "西南": "东北"}
_BAZHAI_TABLE = {
    "坎": [("北", "伏位", "小吉"), ("东北", "五鬼", "凶"), ("东", "天医", "吉"), ("东南", "生气", "大吉"),
           ("南", "延年", "吉"), ("西南", "绝命", "大凶"), ("西", "祸害", "小凶"), ("西北", "六煞", "凶")],
    "坤": [("北", "绝命", "大凶"), ("东北", "生气", "大吉"), ("东", "祸害", "小凶"), ("东南", "五鬼", "凶"),
           ("南", "六煞", "凶"), ("西南", "伏位", "小吉"), ("西", "天医", "吉"), ("西北", "延年", "吉")],
    "震": [("北", "天医", "吉"), ("东北", "六煞", "凶"), ("东", "伏位", "小吉"), ("东南", "延年", "吉"),
           ("南", "生气", "大吉"), ("西南", "祸害", "小凶"), ("西", "绝命", "大凶"), ("西北", "五鬼", "凶")],
    "巽": [("北", "生气", "大吉"), ("东北", "绝命", "大凶"), ("东", "延年", "吉"), ("东南", "伏位", "小吉"),
           ("南", "天医", "吉"), ("西南", "五鬼", "凶"), ("西", "六煞", "凶"), ("西北", "祸害", "小凶")],
    "乾": [("北", "六煞", "凶"), ("东北", "天医", "吉"), ("东", "五鬼", "凶"), ("东南", "祸害", "小凶"),
           ("南", "绝命", "大凶"), ("西南", "延年", "吉"), ("西", "生气", "大吉"), ("西北", "伏位", "小吉")],
    "兑": [("北", "祸害", "小凶"), ("东北", "延年", "吉"), ("东", "绝命", "大凶"), ("东南", "六煞", "凶"),
           ("南", "五鬼", "凶"), ("西南", "天医", "吉"), ("西", "伏位", "小吉"), ("西北", "生气", "大吉")],
    "艮": [("北", "五鬼", "凶"), ("东北", "伏位", "小吉"), ("东", "六煞", "凶"), ("东南", "绝命", "大凶"),
           ("南", "祸害", "小凶"), ("西南", "生气", "大吉"), ("西", "延年", "吉"), ("西北", "天医", "吉")],
    "离": [("北", "延年", "吉"), ("东北", "祸害", "小凶"), ("东", "生气", "大吉"), ("东南", "天医", "吉"),
           ("南", "伏位", "小吉"), ("西南", "六煞", "凶"), ("西", "五鬼", "凶"), ("西北", "绝命", "大凶")],
}


def _year_gz(y: int) -> str:
    n = (y - 4) % 60
    return GAN[n % 10] + ZHI[n % 12]


def _effective_year(birth, chart) -> int:
    y = birth.year
    p = chart["pillars"][0]
    return y if _year_gz(y) == p["gan"] + p["zhi"] else y - 1


def bazhai(arg: str = "", saved_raw: str | None = None) -> str:
    """八宅风水：命卦 + 八方吉凶；可选房屋坐向做宅命相配。"""
    arg = (arg or "").strip()
    year = None
    gender = None
    sit = None

    m = re.search(r"(\d{4})", arg)
    if m:
        year = int(m.group(1))
    gm = re.search(r"(男|女)", arg)
    if gm:
        gender = gm.group(1)

    sm = re.search(r"坐\s*(东南|西北|东北|西南|东|南|西|北)", arg)
    cm = re.search(r"朝\s*(东南|西北|东北|西南|东|南|西|北)", arg)
    if sm:
        sit = sm.group(1)
    elif cm:
        sit = _OPPOSITE.get(cm.group(1))
    else:
        dm = re.search(r"(东南|西北|东北|西南|东|南|西|北)", arg)
        if dm:
            sit = dm.group(1)

    if saved_raw and (year is None or gender is None):
        try:
            b = parse_birth_info(saved_raw)
            c = cast_chart(b)
            if gender is None:
                gender = b.gender
            if year is None:
                year = _effective_year(b, c)
        except Exception:
            pass

    if year is None or gender is None:
        raise ValueError("用法: 八宅 1990 男 坐北朝南；或先发『八字 ...』存档案后发『八宅 坐北朝南』")
    if not (1900 <= year <= 2100):
        raise ValueError("出生年份需在 1900-2100 之间")

    yy = year % 100
    gua = (100 - yy) % 9 if gender == "男" else (yy - 4) % 9
    if gua == 0:
        gua = 9
    if gua == 5:
        gua = 2 if gender == "男" else 8
    gua_name = _MING_GUA[gua]
    group = "东四命" if gua in (1, 3, 4, 9) else "西四命"

    lines = [f"【八宅风水】{year}年 {gender}命", f"命卦：{gua_name}命（{group}）"]

    if sit and sit in _SIT_GUA:
        zhai = _SIT_GUA[sit]
        zhai_name = _MING_GUA[zhai]
        zhai_group = "东四宅" if zhai in (1, 3, 4, 9) else "西四宅"
        match = "相配 ✅" if (gua in (1, 3, 4, 9)) == (zhai in (1, 3, 4, 9)) else "不配 ⚠️"
        lines.append(f"宅卦：{zhai_name}宅（坐{sit}）｜{zhai_group}｜宅命{match}")

    table = _BAZHAI_TABLE[gua_name]
    good = [f"{d}{star}（{luck}）" for d, star, luck in table if luck in {"大吉", "吉", "小吉"}]
    bad = [f"{d}{star}（{luck}）" for d, star, luck in table if luck in {"大凶", "凶", "小凶"}]
    lines.append("吉方：" + "、".join(good))
    lines.append("凶方：" + "、".join(bad))
    lines.append("建议：大门、卧室、书桌优先放在生气/天医/延年方；绝命、五鬼方少做主卧与灶位。")
    lines.append("※ 仅供传统文化参考，不构成置业/装修建议。")
    return "\n".join(lines)
