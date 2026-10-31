"""七政四余星命（十一曜躔度 · 十二宫 · 命身宫）。"""

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

from .bazi import parse_birth_info, BaziError, calculate_ganzhi
from .sxtwl_compat import GAN, ZHI


QZ_D2R = math.pi / 180.0
QZ_R2D = 180.0 / math.pi

# ---------------------------------------------------------------- 二十八宿
# (宿名, 五行, 七曜, 动物, 黄道起点度[古宿制, J2000])
QZ_SU28 = (
    ("角", "木", "日", "蛟", 187.20),
    ("亢", "金", "金", "龙", 200.00),
    ("氐", "土", "土", "貉", 208.90),
    ("房", "日", "日", "兔", 225.20),
    ("心", "月", "月", "狐", 230.60),
    ("尾", "火", "火", "虎", 237.00),
    ("箕", "水", "水", "豹", 255.60),
    ("斗", "木", "木", "獬", 266.30),
    ("牛", "金", "金", "牛", 290.10),
    ("女", "土", "土", "蝠", 296.79),
    ("虚", "日", "日", "鼠", 307.57),
    ("危", "月", "月", "燕", 316.30),
    ("室", "火", "火", "猪", 331.76),
    ("壁", "水", "水", "貐", 349.52),
    ("奎", "木", "木", "狼", 358.57),
    ("娄", "金", "金", "狗", 15.90),
    ("胃", "土", "土", "雉", 26.30),
    ("昴", "日", "日", "鸡", 41.10),
    ("毕", "月", "月", "乌", 53.20),
    ("觜", "火", "火", "猴", 69.00),
    ("参", "水", "水", "猿", 70.00),
    ("井", "木", "木", "犴", 81.80),
    ("鬼", "金", "金", "羊", 112.30),
    ("柳", "土", "土", "獐", 115.20),
    ("星", "日", "日", "马", 130.50),
    ("张", "月", "月", "鹿", 136.40),
    ("翼", "火", "火", "蛇", 151.40),
    ("轸", "水", "水", "蚓", 170.10),
)
# 按黄经排序的起点表（供查宿）
QZ_SU_SORTED = tuple(sorted(((n, s) for n, _w, _r, _a, s in QZ_SU28), key=lambda x: x[1]))
QZ_SU_INFO = {n: (w, r, a, s) for n, w, r, a, s in QZ_SU28}

# ---------------------------------------------------------------- 十二宫
# 索引 = 黄经 // 30；戌宫起 0°。(地支, 黄道宫名, 宫主, 十二次)
QZ_GONG = (
    ("戌", "白羊", "火", "降娄"), ("酉", "金牛", "金", "大梁"),
    ("申", "阴阳", "水", "实沈"), ("未", "巨蟹", "月", "鹑首"),
    ("午", "狮子", "日", "鹑火"), ("巳", "双女", "水", "鹑尾"),
    ("辰", "天秤", "金", "寿星"), ("卯", "天蝎", "火", "大火"),
    ("寅", "人马", "木", "析木"), ("丑", "摩羯", "土", "星纪"),
    ("子", "宝瓶", "土", "玄枵"), ("亥", "双鱼", "木", "娵訾"),
)
QZ_ZHI_GONG = {g[0]: i for i, g in enumerate(QZ_GONG)}

# 十二宫位（从命宫起，沿黄道逆排）
QZ_WEI = ("命宫", "财帛", "兄弟", "田宅", "男女", "奴仆",
          "夫妻", "疾厄", "迁移", "官禄", "福德", "相貌")

# ---------------------------------------------------------------- 星曜
QZ_STARS = ("日", "月", "水", "金", "火", "木", "土", "罗", "计", "孛", "气")
QZ_STAR_FULL = {"日": "太阳", "月": "太阴", "水": "水星", "金": "金星",
                "火": "火星", "木": "木星", "土": "土星",
                "罗": "罗睺", "计": "计都", "孛": "月孛", "气": "紫气"}
QZ_STAR_WX = {"日": "火", "月": "水", "水": "水", "金": "金", "火": "火",
              "木": "木", "土": "土", "罗": "火", "计": "土", "孛": "水", "气": "木"}
QZ_STAR_COLOR_RGB = {
    "日": (212, 132, 32), "月": (86, 130, 176), "水": (110, 140, 160),
    "金": (176, 146, 60), "火": (196, 74, 60), "木": (52, 122, 82),
    "土": (146, 108, 62), "罗": (150, 78, 96), "计": (120, 96, 150),
    "孛": (72, 96, 130), "气": (96, 132, 96),
}

# 五星庙旺落弱（宫支）
QZ_DIGNITY = {
    "日": {"庙": ("午",), "旺": ("戌",), "落": ("子",), "弱": ("辰",)},
    "月": {"庙": ("未",), "旺": ("酉",), "落": ("丑",), "弱": ("卯",)},
    "水": {"庙": ("申", "巳"), "旺": ("巳",), "落": ("寅", "亥"), "弱": ("亥",)},
    "金": {"庙": ("酉", "辰"), "旺": ("亥",), "落": ("戌", "卯"), "弱": ("巳",)},
    "火": {"庙": ("戌", "卯"), "旺": ("丑",), "落": ("辰", "酉"), "弱": ("未",)},
    "木": {"庙": ("寅", "亥"), "旺": ("未",), "落": ("申", "巳"), "弱": ("丑",)},
    "土": {"庙": ("丑", "子"), "旺": ("辰",), "落": ("未", "午"), "弱": ("戌",)},
}

# 恩用仇难：以日干五行为主
QZ_EN = {"生我": "恩", "我生": "用", "克我": "难", "我克": "仇"}
QZ_SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
QZ_KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}

# JPL 近似轨道根数 (a, e, I, L, peri, node) + 每儒略世纪变化率
QZ_ELEM = {
    "水": ((0.38709927, 0.20563593, 7.00497902, 252.25032350, 77.45779628, 48.33076593),
           (0.00000037, 0.00001906, -0.00594749, 149472.67411175, 0.16047689, -0.12534081)),
    "金": ((0.72333566, 0.00677672, 3.39467605, 181.97909950, 131.60246718, 76.67984255),
           (0.00000390, -0.00004107, -0.00078890, 58517.81538729, 0.00268329, -0.27769418)),
    "地": ((1.00000261, 0.01671123, -0.00001531, 100.46457166, 102.93768193, 0.0),
           (0.00000562, -0.00004392, -0.01294668, 35999.37244981, 0.32327364, 0.0)),
    "火": ((1.52371034, 0.09339410, 1.84969142, -4.55343205, -23.94362959, 49.55953891),
           (0.00001847, 0.00007882, -0.00813131, 19140.30268499, 0.44441088, -0.29257343)),
    "木": ((5.20288700, 0.04838624, 1.30439695, 34.39644051, 14.72847983, 100.47390909),
           (-0.00011607, -0.00013253, -0.00183714, 3034.74612775, 0.21252668, 0.20469106)),
    "土": ((9.53667594, 0.05386179, 2.48599187, 49.95424423, 92.59887831, 113.66242448),
           (-0.00125060, -0.00050991, 0.00193609, 1222.49362201, -0.41897216, -0.28867794)),
}


# ---------------------------------------------------------------- 基础工具

def _qz_norm(x: float) -> float:
    x = math.fmod(x, 360.0)
    return x + 360.0 if x < 0 else x


def _qz_jd(dt: datetime) -> float:
    """公历(格里历)时刻 -> 儒略日。"""
    return (dt.toordinal() + 1721424.5
            + (dt.hour * 3600 + dt.minute * 60 + dt.second) / 86400.0)


def _qz_praec(T: float) -> float:
    """从 J2000 到 T 的岁差累计（度）。"""
    return 1.396971 * T + 0.0003086 * T * T


def _qz_nutation(T: float) -> float:
    """章动黄经主项（度）。"""
    om = _qz_norm(125.04452 - 1934.136261 * T)
    ls = _qz_norm(280.4665 + 36000.7698 * T)
    lm = _qz_norm(218.3165 + 481267.8813 * T)
    dpsi = (-17.20 * math.sin(om * QZ_D2R)
            - 1.32 * math.sin(2 * ls * QZ_D2R)
            - 0.23 * math.sin(2 * lm * QZ_D2R)
            + 0.21 * math.sin(2 * om * QZ_D2R))
    return dpsi / 3600.0


def _qz_sun(jd: float) -> float:
    """太阳视黄经（度，当日真春分点）。"""
    T = (jd - 2451545.0) / 36525.0
    L0 = 280.46646 + 36000.76983 * T + 0.0003032 * T * T
    M = 357.52911 + 35999.05029 * T - 0.0001537 * T * T
    C = ((1.914602 - 0.004817 * T - 0.000014 * T * T) * math.sin(M * QZ_D2R)
         + (0.019993 - 0.000101 * T) * math.sin(2 * M * QZ_D2R)
         + 0.000289 * math.sin(3 * M * QZ_D2R))
    true_long = L0 + C
    om = 125.04 - 1934.136 * T
    return _qz_norm(true_long - 0.00569 - 0.00478 * math.sin(om * QZ_D2R))


QZ_MOON_TERMS = (
    (6288774, 0, 0, 1, 0), (1274027, 2, 0, -1, 0), (658314, 2, 0, 0, 0),
    (213618, 0, 0, 2, 0), (-185116, 0, 1, 0, 0), (-114332, 0, 0, 0, 2),
    (58793, 2, 0, -2, 0), (57066, 2, -1, -1, 0), (53322, 2, 0, 1, 0),
    (45758, 2, -1, 0, 0), (-40923, 0, 1, -1, 0), (-34720, 1, 0, 0, 0),
    (-30383, 0, 1, 1, 0), (15327, 2, 0, 0, -2), (-12528, 0, 0, 1, 2),
    (10980, 0, 0, 1, -2), (10675, 4, 0, -1, 0), (10034, 0, 0, 3, 0),
    (8548, 4, 0, -2, 0), (-7888, 2, 1, -1, 0), (-6766, 2, 1, 0, 0),
    (-5163, 1, 0, -1, 0), (4987, 1, 1, 0, 0), (4036, 2, -1, 1, 0),
    (3994, 2, 0, 2, 0), (3861, 4, 0, 0, 0), (3665, 2, 0, -3, 0),
    (-2689, 0, 1, -2, 0), (-2602, 2, 0, -1, 2), (2390, 2, -1, -2, 0),
    (-2348, 1, 0, 1, 0), (2236, 2, -2, 0, 0), (-2120, 0, 1, 2, 0),
    (-2069, 0, 2, 0, 0), (2048, 2, -2, -1, 0), (-1773, 2, 0, 1, -2),
    (-1595, 2, 0, 0, 2), (1215, 4, -1, -1, 0), (-1110, 0, 0, 2, 2),
    (-892, 3, 0, -1, 0), (-810, 2, 1, 1, 0), (759, 4, -1, -2, 0),
    (-713, 0, 2, -1, 0), (-700, 2, 2, -1, 0), (691, 2, 1, -2, 0),
    (596, 2, -1, 0, -2), (549, 4, 0, 1, 0), (537, 0, 0, 4, 0),
    (520, 4, -1, 0, 0), (-487, 1, 0, -2, 0), (-399, 2, 1, 0, -2),
    (-381, 0, 0, 2, -2), (351, 1, 1, 1, 0), (-340, 3, -1, -2, 0),
    (330, 4, 0, -3, 0), (327, 2, -1, 2, 0), (-323, 0, 2, 1, 0),
    (299, 1, 1, -1, 0), (294, 2, 0, 3, 0),
)


def _qz_moon(jd: float) -> float:
    """太阴视黄经（度）。"""
    T = (jd - 2451545.0) / 36525.0
    Lp = _qz_norm(218.3164477 + 481267.88123421 * T - 0.0015786 * T * T
                  + T ** 3 / 538841.0 - T ** 4 / 65194000.0)
    D = _qz_norm(297.8501921 + 445267.1114034 * T - 0.0018819 * T * T
                 + T ** 3 / 545868.0 - T ** 4 / 113065000.0)
    M = _qz_norm(357.5291092 + 35999.0502909 * T - 0.0001536 * T * T + T ** 3 / 24490000.0)
    Mp = _qz_norm(134.9633964 + 477198.8675055 * T + 0.0087414 * T * T
                  + T ** 3 / 69699.0 - T ** 4 / 14712000.0)
    F = _qz_norm(93.2720950 + 483202.0175233 * T - 0.0036539 * T * T
                 - T ** 3 / 3526000.0 + T ** 4 / 863310000.0)
    s = 0.0
    for coef, d, m, mp, f in QZ_MOON_TERMS:
        s += coef * math.sin((d * D + m * M + mp * Mp + f * F) * QZ_D2R)
    lon = Lp + s / 1000000.0
    return _qz_norm(lon + _qz_nutation(T))


def _qz_helio(name: str, jd: float):
    """行星日心黄道坐标（J2000 黄道，AU）。"""
    T = (jd - 2451545.0) / 36525.0
    base, rate = QZ_ELEM[name]
    a = base[0] + rate[0] * T
    e = base[1] + rate[1] * T
    inc = (base[2] + rate[2] * T) * QZ_D2R
    L = base[3] + rate[3] * T
    peri = base[4] + rate[4] * T
    node = (base[5] + rate[5] * T) * QZ_D2R
    M = _qz_norm(L - peri) * QZ_D2R
    if M > math.pi:
        M -= 2 * math.pi
    E = M + e * math.sin(M)
    for _ in range(12):
        dE = (E - e * math.sin(E) - M) / (1 - e * math.cos(E))
        E -= dE
        if abs(dE) < 1e-9:
            break
    xp = a * (math.cos(E) - e)
    yp = a * math.sqrt(max(0.0, 1 - e * e)) * math.sin(E)
    w = (peri - base[5] - rate[5] * T) * QZ_D2R   # 近日点幅角
    cw, sw = math.cos(w), math.sin(w)
    cn, sn = math.cos(node), math.sin(node)
    ci, si = math.cos(inc), math.sin(inc)
    x = (cw * cn - sw * sn * ci) * xp + (-sw * cn - cw * sn * ci) * yp
    y = (cw * sn + sw * cn * ci) * xp + (-sw * sn + cw * cn * ci) * yp
    z = (sw * si) * xp + (cw * si) * yp
    return x, y, z


def _qz_planet(name: str, jd: float) -> float:
    """行星地心视黄经（度，当日真春分点）。"""
    lag = 0.0
    for _ in range(2):
        ex, ey, _ez = _qz_helio("地", jd)
        px, py, _pz = _qz_helio(name, jd - lag)
        dx, dy = px - ex, py - ey
        r = math.sqrt(dx * dx + dy * dy)
        lag = 0.0057755183 * r
    lon = math.degrees(math.atan2(dy, dx))
    T = (jd - 2451545.0) / 36525.0
    return _qz_norm(lon + _qz_praec(T) + _qz_nutation(T))


def _qz_node(jd: float) -> float:
    """罗睺：白道平升交点黄经（逆行）。"""
    T = (jd - 2451545.0) / 36525.0
    return _qz_norm(125.0445479 - 1934.1362891 * T + 0.0020754 * T * T
                    + T ** 3 / 467441.0 - T ** 4 / 60616000.0)


def _qz_apogee(jd: float) -> float:
    """月孛：月球轨道平远地点（月行最迟处，顺行）。"""
    T = (jd - 2451545.0) / 36525.0
    peri = (83.3532465 + 4069.0137287 * T - 0.0103200 * T * T
            - T ** 3 / 80053.0 + T ** 4 / 18999000.0)
    return _qz_norm(peri + 180.0)


def _qz_zihai(jd: float) -> float:
    """紫气：依闰法 28 年一周天。历元取万历五年十二月朔「躔张十四度」。"""
    # 1577-12-29 12:00 UT 附近；张宿起点 136.40（J2000 古宿制），张十四度
    base_jd = 2298273.0
    base_lon = 136.40 + 14.0 * 360.0 / 365.25
    per_day = 13.0504608 / 365.25 * (360.0 / 365.25)
    return _qz_norm(base_lon + (jd - base_jd) * per_day)


def _qz_star_lon(name: str, jd: float) -> float:
    if name == "日":
        return _qz_sun(jd)
    if name == "月":
        return _qz_moon(jd)
    if name == "罗":
        return _qz_node(jd)
    if name == "计":
        return _qz_norm(_qz_node(jd) + 180.0)
    if name == "孛":
        return _qz_apogee(jd)
    if name == "气":
        return _qz_zihai(jd)
    return _qz_planet(name, jd)


# ---------------------------------------------------------------- 定位

def _qz_gong_of(lon: float) -> int:
    """黄经 -> 黄道宫索引（0=戌）。"""
    return int(_qz_norm(lon) // 30.0) % 12


def _qz_su_of(lon_sid: float):
    """恒星黄经 -> (宿名, 宿内度数, 宿跨度, 宿起点)。"""
    lon_sid = _qz_norm(lon_sid)
    n = len(QZ_SU_SORTED)
    for i in range(n):
        name, start = QZ_SU_SORTED[i]
        nxt = QZ_SU_SORTED[(i + 1) % n][1]
        span = (nxt - start) % 360.0
        if span <= 0:
            span += 360.0
        if (lon_sid - start) % 360.0 < span:
            return name, (lon_sid - start) % 360.0, span, start
    name, start = QZ_SU_SORTED[0]
    return name, (lon_sid - start) % 360.0, 0.0, start


def _qz_dufen(du: float) -> str:
    d = int(du)
    f = int(round((du - d) * 60))
    if f >= 60:
        d += 1
        f -= 60
    return f"{d}度{f:02d}分"


def _qz_dir(name: str, jd: float) -> str:
    """顺/逆/留。"""
    if name in ("罗", "计"):
        return "逆"
    if name in ("孛", "气"):
        return "顺"
    a = _qz_star_lon(name, jd - 0.5)
    b = _qz_star_lon(name, jd + 0.5)
    diff = (b - a + 180.0) % 360.0 - 180.0
    if abs(diff) < 0.03:
        return "留"
    return "顺" if diff > 0 else "逆"


def _qz_dignity(name: str, zhi: str) -> str:
    d = QZ_DIGNITY.get(name)
    if not d:
        return ""
    for key in ("庙", "旺", "落", "弱"):
        if zhi in d.get(key, ()):
            return key
    return "平"


def _qz_relation(day_wx: str, star_wx: str) -> str:
    if star_wx == day_wx:
        return "比"
    if QZ_SHENG[star_wx] == day_wx:
        return "恩"
    if QZ_SHENG[day_wx] == star_wx:
        return "用"
    if QZ_KE[star_wx] == day_wx:
        return "难"
    if QZ_KE[day_wx] == star_wx:
        return "仇"
    return ""


def cast_qizheng(text: str = "") -> dict:
    """七政四余排盘。text 用与八字一致的出生信息格式。"""

    text = (text or "").strip()
    if not text:
        raise BaziError(
            "请提供出生信息，例如：七政四余 1990-05-20 14:30 男 北京"
        )
    birth = parse_birth_info(text)
    local_dt = datetime(birth.year, birth.month, birth.day, birth.hour, birth.minute)
    try:
        solar_dt, lon_off, eq_off, (yGZ, mGZ, dGZ, hGZ) = calculate_ganzhi(
            local_dt, birth.longitude, birth.tz_offset
        )
    except Exception as exc:  # noqa: BLE001
        raise BaziError(f"排盘计算失败: {exc}")

    # 真太阳时 -> UTC（北京时减 8h，行星位置只与 UT 有关）
    ut = local_dt - timedelta(hours=birth.tz_offset)
    jd = _qz_jd(ut)
    T = (jd - 2451545.0) / 36525.0
    praec = _qz_praec(T)

    day_gan = GAN[dGZ.tg]
    day_wx = {"甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
              "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水"}[day_gan]
    pillars = [GAN[yGZ.tg] + ZHI[yGZ.dz], GAN[mGZ.tg] + ZHI[mGZ.dz],
               GAN[dGZ.tg] + ZHI[dGZ.dz], GAN[hGZ.tg] + ZHI[hGZ.dz]]

    # ---- 十一曜躔度
    planets = []
    for name in QZ_STARS:
        lon = _qz_star_lon(name, jd)
        gi = _qz_gong_of(lon)
        zhi, xingzuo, _ruler, ci = QZ_GONG[gi]
        su, du, _span, _s0 = _qz_su_of(lon - praec)
        wx, _ri, animal, _st = QZ_SU_INFO[su]
        planets.append({
            "name": name,
            "full": QZ_STAR_FULL[name],
            "lon": round(lon, 4),
            "gong": gi,
            "zhi": zhi,
            "ci": ci,
            "xingzuo": xingzuo,
            "gong_du": round(_qz_norm(lon) % 30.0, 2),
            "su": su,
            "su_full": su + wx + animal,
            "su_du": round(du, 3),
            "su_du_txt": _qz_dufen(du),
            "dir": _qz_dir(name, jd),
            "dig": _qz_dignity(name, zhi),
            "wx": QZ_STAR_WX[name],
            "rel": _qz_relation(day_wx, QZ_STAR_WX[name]),
        })

    # ---- 命宫 / 身宫
    # 命宫：以生时加太阳宫，沿地支顺数至卯（等价于 命宫宫索引 = 太阳宫 + 生时 - 卯）
    # 身宫：太阴所躔之宫（杨国正《七政四余论命术》取此说）
    shi = hGZ.dz                       # 0=子
    sun_lon = next(p["lon"] for p in planets if p["name"] == "日")
    moon_lon = next(p["lon"] for p in planets if p["name"] == "月")
    shift = (shi - 3) * 30.0           # 卯时(3)生人太阳即命宫
    ming_h = _qz_norm(sun_lon + shift)
    ming_gi = _qz_gong_of(ming_h)
    ming_du = _qz_norm(sun_lon) % 30.0        # 命度 = 太阳在同宫之度数
    shen_gi = _qz_gong_of(moon_lon)

    # ---- 十二宫位（自命宫沿地支逆序，即黄经递增方向排布）
    gongwei = []
    for k, wname in enumerate(QZ_WEI):
        gi = (ming_gi + k) % 12
        zhi, xingzuo, ruler, ci = QZ_GONG[gi]
        gongwei.append({
            "idx": k, "name": wname, "gong": gi, "zhi": zhi, "ci": ci,
            "xingzuo": xingzuo, "ruler": ruler, "stars": [],
        })
    by_gi = {g["gong"]: g for g in gongwei}
    for p in planets:
        by_gi[p["gong"]]["stars"].append(p["name"])
        p["gong_wei"] = by_gi[p["gong"]]["name"]

    ming_ruler = QZ_GONG[ming_gi][2]
    su_ming, du_ming, _sp, _s0 = _qz_su_of(ming_h - praec)
    du_zhu = QZ_SU_INFO[su_ming][1]           # 命度主 = 命度所躔宿之曜

    # ---- 格局
    geju = []
    ming_stars = by_gi[ming_gi]["stars"]
    if ming_stars:
        geju.append("命宫坐" + "、".join(ming_stars) + "，星曜临命，性情显于外")
    if ming_ruler in QZ_STARS:
        mr = next((p for p in planets if p["name"] == ming_ruler), None)
        if mr:
            tag = mr["dig"] or "平"
            geju.append(f"命宫主 {QZ_STAR_FULL[ming_ruler]} 在{mr['zhi']}宫·"
                        f"{mr['xingzuo']}（{tag}）")
    d = next(p for p in planets if p["name"] == "日")
    m = next(p for p in planets if p["name"] == "月")
    sep = abs((d["lon"] - m["lon"] + 180.0) % 360.0 - 180.0)
    if sep < 8:
        geju.append(f"日月同宫（相距 {sep:.1f}°），合朔之象，主内敛专一")
    elif sep > 172:
        geju.append(f"日月对望（相距 {sep:.1f}°），望月当空，主外向显达")
    # 五星聚：相邻两宫内五星数量
    five = [p for p in planets if p["name"] in ("水", "金", "火", "木", "土")]
    cells = {}
    for p in five:
        cells.setdefault(p["gong"], []).append(p["name"])
    best, best_pair = 0, None
    for gi, names in cells.items():
        cnt = len(names) + len(cells.get((gi + 1) % 12, []))
        if cnt > best:
            best, best_pair = cnt, gi
    if best >= 3:
        z1 = QZ_GONG[best_pair][0]
        z2 = QZ_GONG[(best_pair + 1) % 12][0]
        geju.append(f"五星聚于{z1}·{z2}两宫（{best}星），气聚一方，格局偏旺")
    # 四余夹命
    for a, b, label in (("罗", "计", "罗计"), ("火", "罗", "火罗"), ("土", "计", "土计")):
        pa = next(p for p in planets if p["name"] == a)
        pb = next(p for p in planets if p["name"] == b)
        if (pa["gong"] + 1) % 12 == ming_gi and (pb["gong"] - 1) % 12 == ming_gi:
            geju.append(f"{label}夹命，势重而压力亦重")
    # 恩用仇难缺
    rels = {p["rel"] for p in planets}
    lack = [k for k in ("恩", "用") if k not in rels]
    if lack:
        geju.append("盘中缺 " + "、".join(lack) + " 星，须借岁运补之")
    nan = [p["name"] for p in planets if p["rel"] == "难"]
    if nan:
        geju.append("难星 " + "、".join(nan) + "，所落之宫为一生着力处")

    return {
        "birth": {
            "solar": f"{birth.year}-{birth.month:02d}-{birth.day:02d} "
                     f"{birth.hour:02d}:{birth.minute:02d}",
            "gender": birth.gender,
            "city": birth.city,
            "is_lunar": birth.is_lunar,
            "lunar_desc": birth.lunar_desc,
        },
        "solar_time": solar_dt.strftime("%Y-%m-%d %H:%M"),
        "lon_off": lon_off,
        "eq_off": eq_off,
        "corrected": birth.longitude is not None,
        "pillars": pillars,
        "day_gan": day_gan,
        "day_wx": day_wx,
        "planets": planets,
        "ming": {
            "gong": ming_gi, "zhi": QZ_GONG[ming_gi][0], "ci": QZ_GONG[ming_gi][3],
            "xingzuo": QZ_GONG[ming_gi][1], "ruler": ming_ruler,
            "du_zhu": du_zhu, "huang": round(ming_h, 2),
            "du": round(ming_du, 2), "su": su_ming, "su_du": round(du_ming, 3),
            "su_du_txt": _qz_dufen(du_ming),
        },
        "shen": {
            "gong": shen_gi, "zhi": QZ_GONG[shen_gi][0],
            "ci": QZ_GONG[shen_gi][3], "xingzuo": QZ_GONG[shen_gi][1],
            "ruler": QZ_GONG[shen_gi][2], "huang": round(moon_lon, 2),
        },
        "gongwei": gongwei,
        "geju": geju,
        "praec": round(praec, 4),
        "jd": round(jd, 5),
        "note": "日躔与宫界用回归黄道，宿度用古宿制恒星黄道（J2000），"
                "五星位置为天文近似值（误差 1′~10′）",
    }


def format_qizheng(c: dict) -> str:
    b = c["birth"]
    lines = [
        f"## 七政四余 · {c['pillars'][0]}年 {c['pillars'][1]}月 "
        f"{c['pillars'][2]}日 {c['pillars'][3]}时",
        "",
        f"**生辰** {b['solar']}　{b['gender']}"
        + (f"　{b['city']}" if b["city"] else ""),
        f"**真太阳时** {c['solar_time']}"
        + (f"（经度差 {c['lon_off']:+.0f} 分，均时差 {c['eq_off']:+.0f} 分）"
           if c["corrected"] else "（未校正）"),
        "",
        f"**命宫** {c['ming']['zhi']}宫·{c['ming']['xingzuo']}（{c['ming']['ci']}）　"
        f"命度 {c['ming']['su']}宿{c['ming']['su_du_txt']}　"
        f"命宫主 {QZ_STAR_FULL.get(c['ming']['ruler'], c['ming']['ruler'])}"
        f" · 命度主 {QZ_STAR_FULL.get(c['ming']['du_zhu'], c['ming']['du_zhu'])}",
        f"**身宫** {c['shen']['zhi']}宫·{c['shen']['xingzuo']}（{c['shen']['ci']}）　"
        f"身宫主 {QZ_STAR_FULL.get(c['shen']['ruler'], c['shen']['ruler'])}",
        "",
        "**十一曜躔度**",
    ]
    for p in c["planets"]:
        lines.append(
            f"· {p['full']}（{p['name']}）：{p['zhi']}宫·{p['xingzuo']}"
            f" {p['gong_du']:.2f}° · {p['su']}宿{p['su_du_txt']}"
            f" · {p['dir']}"
            + (f" · {p['dig']}" if p["dig"] and p["dig"] != "平" else "")
            + f" · {p['wx']}（{p['rel']}）· 居{p['gong_wei']}"
        )
    lines += ["", "**十二宫**"]
    for g in c["gongwei"]:
        stars = "、".join(g["stars"]) if g["stars"] else "空"
        lines.append(f"· {g['name']}（{g['zhi']}宫{g['xingzuo']}，主{g['ruler']}）：{stars}")
    if c["geju"]:
        lines += ["", "**格局**"]
        for g in c["geju"]:
            lines.append(f"· {g}")
    lines += ["", f"（{c['note']}）"]
    return "\n".join(lines)


def qizheng(text: str = "") -> str:
    return format_qizheng(cast_qizheng(text))
