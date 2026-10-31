"""sxtwl 兼容层：基于 lunar-python 实现的纯 Python 干支/节气工具。"""

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

import math
from lunar_python import Solar, Lunar


# 说明: C++ 版 sxtwl 在 Python 3.13 无预编译 wheel, 这里用 lunar-python 实现
# paipan.py 所需的 fromSolar / fromLunar / Time / toJD / getShiGz / getJieQiByYear。

GAN = "甲乙丙丁戊己庚辛壬癸"
ZHI = "子丑寅卯辰巳午未申酉戌亥"

# 24 节气顺序（与 paipan.py 的 _JQ_ORDER 对应）
_JQ_ORDER = [
    "冬至", "小寒", "大寒", "立春", "雨水", "惊蛰", "春分", "清明",
    "谷雨", "立夏", "小满", "芒种", "夏至", "小暑", "大暑", "立秋",
    "处暑", "白露", "秋分", "寒露", "霜降", "立冬", "小雪", "大雪",
]


class GZ:
    """干支索引对象，tg=天干索引(0-9)，dz=地支索引(0-11)。"""

    __slots__ = ("tg", "dz")

    def __init__(self, tg, dz):
        self.tg = tg
        self.dz = dz


def _eight_char(y, m, d):
    """公历(y,m,d) -> lunar-python EightChar 对象（默认 0 时，与 sxtwl.fromSolar 同口径）。"""
    return Solar.fromYmd(y, m, d).getLunar().getEightChar()


class Day:
    def __init__(self, y, m, d):
        self._y, self._m, self._d = y, m, d
        self._ec = _eight_char(y, m, d)

    def getYearGZ(self):
        gz = self._ec.getYear()
        return GZ(GAN.index(gz[0]), ZHI.index(gz[1]))

    def getMonthGZ(self):
        gz = self._ec.getMonth()
        return GZ(GAN.index(gz[0]), ZHI.index(gz[1]))

    def getDayGZ(self):
        gz = self._ec.getDay()
        return GZ(GAN.index(gz[0]), ZHI.index(gz[1]))

    def getHourGZ(self, hour, isZaoWanZiShi=True):
        # sxtwl 默认 isZaoWanZiShi=True（晚子时：23 点用次日日干起子时）
        return getShiGz(self.getDayGZ().tg, hour, isZaoWanZiShi)


def fromSolar(y, m, d):
    return Day(y, m, d)


class _SolarDate:
    """sxtwl.fromLunar 返回对象的兼容结构。"""

    __slots__ = ("_y", "_m", "_d")

    def __init__(self, y, m, d):
        self._y, self._m, self._d = y, m, d

    def getSolarYear(self):
        return self._y

    def getSolarMonth(self):
        return self._m

    def getSolarDay(self):
        return self._d


def fromLunar(year, month, day, is_leap=False):
    """农历 -> 公历。lunar-python 用负数月份表示闰月。"""
    m = -month if is_leap else month
    s = Lunar.fromYmd(year, m, day).getSolar()
    return _SolarDate(s.getYear(), s.getMonth(), s.getDay())


class Time:
    """sxtwl 的时间结构。"""

    def __init__(self):
        self.Y = 0
        self.M = 0
        self.D = 0
        self.h = 0
        self.m = 0
        self.s = 0


def _to_jd(y, m, d, hh=0, mm=0, ss=0):
    """标准天文儒略日（与 lunar-python Solar.getJulianDay 同口径）。"""
    a = (14 - m) // 12
    yy = y + 4800 - a
    mo = m + 12 * a - 3
    jdn = d + (153 * mo + 2) // 5 + 365 * yy + yy // 4 - yy // 100 + yy // 400 - 32045
    return jdn + (hh - 12) / 24.0 + mm / 1440.0 + ss / 86400.0


def toJD(t):
    return _to_jd(t.Y, t.M, t.D, t.h, t.m, t.s)


def getShiGz(dayTg, hour, isZaoWanZiShi=True):
    """移植自 sxtwl.getShiGz：日干 dayTg(0-9) + 小时(0-23) -> 时柱 GZ。

    五鼠遁:
        甲己日 -> 甲子时(0)
        乙庚日 -> 丙子时(2)
        丙辛日 -> 戊子时(4)
        丁壬日 -> 庚子时(6)
        戊癸日 -> 壬子时(8)
    """
    step = (hour + 1) // 2
    if step >= 12:
        dz = 0  # 23 点 -> 子时
    else:
        dz = step % 12
    if (not isZaoWanZiShi) and hour == 23:
        step = 0  # 早子时：23 点算当日子时
    base = {0: 0, 5: 0, 1: 2, 6: 2, 2: 4, 7: 4, 3: 6, 8: 6, 4: 8, 9: 8}[dayTg]
    return GZ((base + step) % 10, dz)


class _JieQiInfo:
    __slots__ = ("jqIndex", "jd")

    def __init__(self, jqIndex, jd):
        self.jqIndex = jqIndex
        self.jd = jd


def getJieQiByYear(year):
    """返回该阳历年全部 24 节气的 (jqIndex, 儒略日)，供起大运数「节」用。"""
    table = Lunar.fromYmd(year, 1, 1).getJieQiTable()
    infos = []
    for name, solar in table.items():
        if name not in _JQ_ORDER:
            continue
        if solar.getYear() != year:
            continue
        infos.append(_JieQiInfo(_JQ_ORDER.index(name), solar.getJulianDay()))
    return infos


# ---------------------------------------------------------------------------
# 自检（python -m sxtwl）
# ---------------------------------------------------------------------------



# 把兼容层注册成名为 sxtwl 的模块, 供引擎代码 import
_sxtwl_mod = types.ModuleType("sxtwl")
for _n in ("GZ", "Day", "fromSolar", "fromLunar", "Time", "toJD", "getShiGz", "getJieQiByYear"):
    setattr(_sxtwl_mod, _n, globals()[_n])
sys.modules["sxtwl"] = _sxtwl_mod
sxtwl = _sxtwl_mod
