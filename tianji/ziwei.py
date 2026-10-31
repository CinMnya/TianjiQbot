"""紫微斗数排盘：安星、十二宫与文本盘面。"""

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

from .bazi import parse_birth_info


ZIWEI_DIZHI = "子丑寅卯辰巳午未申酉戌亥"
ZIWEI_TIANGAN = "甲乙丙丁戊己庚辛壬癸"
ZIWEI_WUXING = "木火土金水"

_ZIWEI_LUNAR_MONTH = ("正", "二", "三", "四", "五", "六",
                      "七", "八", "九", "十", "冬", "腊")

_PALACE_NAMES = ("命宫", "兄弟", "夫妻", "子女", "财帛", "疾厄",
                 "迁移", "交友", "官禄", "田宅", "福德", "父母")

# 六十甲子纳音(每两个一组, 共 30 组)
_NAYIN = (
    "金", "火", "木", "土", "金", "火", "水", "土", "金", "木",
    "水", "土", "火", "木", "水", "金", "火", "木", "土", "金",
    "火", "水", "土", "金", "木", "水", "土", "火", "木", "水",
)

# 纳音五行 -> (局数, 局名)
_JU = {"水": (2, "水二局"), "木": (3, "木三局"), "金": (4, "金四局"),
       "土": (5, "土五局"), "火": (6, "火六局")}

# 紫微系(相对紫微逆行的偏移) / 天府系(相对天府顺行的偏移)
_ZIWEI_SERIES = (("紫微", 0), ("天机", -1), ("太阳", -3),
                 ("武曲", -4), ("天同", -5), ("廉贞", -8))
_TIANFU_SERIES = (("天府", 0), ("太阴", 1), ("贪狼", 2), ("巨门", 3),
                  ("天相", 4), ("天梁", 5), ("七杀", 6), ("破军", 10))

_MAIN_STARS = frozenset(n for n, _ in _ZIWEI_SERIES) | frozenset(n for n, _ in _TIANFU_SERIES)

# 生年干四化: (化禄, 化权, 化科, 化忌)
_SIHUA = {
    "甲": ("廉贞", "破军", "武曲", "太阳"),
    "乙": ("天机", "天梁", "紫微", "太阴"),
    "丙": ("天同", "天机", "文昌", "廉贞"),
    "丁": ("太阴", "天同", "天机", "巨门"),
    "戊": ("贪狼", "太阴", "右弼", "天机"),
    "己": ("武曲", "贪狼", "天梁", "文曲"),
    "庚": ("太阳", "武曲", "天府", "天同"),
    "辛": ("巨门", "太阳", "文曲", "文昌"),
    "壬": ("天梁", "紫微", "左辅", "武曲"),
    "癸": ("破军", "巨门", "太阴", "贪狼"),
}
_SIHUA_NAME = ("禄", "权", "科", "忌")

# 天魁天钺(按生年干)
_KUI_YUE = {
    "甲": (1, 7), "戊": (1, 7), "庚": (1, 7),
    "乙": (0, 8), "己": (0, 8),
    "丙": (11, 9), "丁": (11, 9),
    "辛": (6, 2),
    "壬": (3, 5), "癸": (3, 5),
}

# 禄存(按生年干)
_LUCUN = {"甲": 2, "乙": 3, "丙": 5, "丁": 6, "戊": 5,
          "己": 6, "庚": 8, "辛": 9, "壬": 11, "癸": 0}

# 火铃起点(按生年支三合局), 一律自子时顺行
_HUO_START = {"寅午戌": 1, "申子辰": 2, "巳酉丑": 3, "亥卯未": 9}
_LING_START = {"寅午戌": 3, "申子辰": 10, "巳酉丑": 10, "亥卯未": 10}
# 天马(按生年支三合局)
_TIANMA = {"寅午戌": 8, "申子辰": 2, "巳酉丑": 11, "亥卯未": 5}

# 命主(按命宫地支) / 身主(按生年支)
_MING_ZHU = {0: "贪狼", 1: "巨门", 11: "巨门", 2: "禄存", 10: "禄存",
             3: "文曲", 9: "文曲", 4: "廉贞", 8: "廉贞",
             5: "武曲", 7: "武曲", 6: "破军"}
_SHEN_ZHU = ("火星", "天相", "天梁", "天同", "文昌", "天机")

_LUCKY = frozenset({"左辅", "右弼", "文昌", "文曲", "天魁", "天钺",
                    "禄存", "天马", "三台", "八座", "红鸾", "天喜"})
_MALEFIC = frozenset({"擎羊", "陀罗", "火星", "铃星", "地空", "地劫",
                      "天刑", "天姚"})


# ---------------------------------------------------------------- 基础换算


def _sanhe(zhi: int) -> str:
    """地支三合局名。"""
    if zhi in (2, 6, 10):
        return "寅午戌"
    if zhi in (8, 0, 4):
        return "申子辰"
    if zhi in (5, 9, 1):
        return "巳酉丑"
    return "亥卯未"


def _nayin(gan: int, zhi: int) -> str:
    """宫干支 -> 纳音五行。"""
    for n in range(60):
        if n % 10 == gan and n % 12 == zhi:
            return _NAYIN[n // 2]
    return "土"


def _palace_gan(zhi: int, yin_gan: int) -> int:
    """五虎遁: 由寅宫天干推任意地支宫的天干。"""
    return (yin_gan + ((zhi - 2) % 12)) % 10


def _ziwei_zhi(ju: int, day: int) -> int:
    """五行局数 + 农历日 -> 紫微星所在地支。

    取最小的 m 使 m*ju >= day, 余数 r = m*ju - day;
    r 为偶数则自 (m-1) 宫顺进 r 位, 奇数则逆退 r 位(寅宫起算)。
    """
    m = (day + ju - 1) // ju
    r = m * ju - day
    idx = (m - 1) + (r if r % 2 == 0 else -r)
    return (2 + idx) % 12


def _lunar_text(year_gz: str, month: int, day: int, leap: bool) -> str:
    m = _ZIWEI_LUNAR_MONTH[(month - 1) % 12]
    d = _lunar_day_text(day)
    return f"农历{year_gz}年{'闰' if leap else ''}{m}月{d}"


def _lunar_day_text(day: int) -> str:
    cn = "一二三四五六七八九十"
    if day <= 10:
        return "初" + cn[day - 1]
    if day < 20:
        return "十" + cn[day - 11]
    if day == 20:
        return "二十"
    if day < 30:
        return "廿" + cn[day - 21]
    return "三十"


# ---------------------------------------------------------------- 排盘


def cast_ziwei(text: str) -> dict:
    """从出生信息文本排出紫微斗数命盘。"""

    birth = parse_birth_info(text)
    if birth.is_lunar and birth.lunar_desc:
        pass  # parse_birth_info 已把农历换算成公历, 下面统一按公历取农历

    # 23 点后属次日子时(通行做法), 日期进一位
    late_zi = birth.hour >= 23
    dt = datetime(birth.year, birth.month, birth.day, birth.hour, birth.minute)
    if late_zi:
        dt = dt + timedelta(days=1)

    solar = Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, birth.minute, 0)
    lun = solar.getLunar()
    lunar_year = lun.getYear()
    lunar_month = lun.getMonth()
    leap = lunar_month < 0
    lunar_month = abs(lunar_month)
    lunar_day = lun.getDay()
    year_gz = lun.getYearInGanZhi()
    y_gan = year_gz[0]
    y_zhi = year_gz[1]
    yi = ZIWEI_TIANGAN.index(y_gan)
    zi = ZIWEI_DIZHI.index(y_zhi)

    hour_zhi = ((birth.hour + 1) // 2) % 12

    # 命宫: 寅起正月顺数到生月, 再从该宫起子时逆数到生时
    ming_zhi = (2 + (lunar_month - 1) - hour_zhi) % 12
    # 身宫: 同上但顺数
    shen_zhi = (2 + (lunar_month - 1) + hour_zhi) % 12

    # 五虎遁定宫干
    yin_gan = (yi * 2 + 2) % 10
    gan_of = {z: _palace_gan(z, yin_gan) for z in range(12)}

    # 五行局: 命宫纳音
    ju_wx = _nayin(gan_of[ming_zhi], ming_zhi)
    ju_num, ju_name = _JU[ju_wx]

    # 紫微 / 天府
    zw = _ziwei_zhi(ju_num, lunar_day)
    tf = (4 - zw) % 12

    stars: dict = {z: [] for z in range(12)}

    def put(z: int, name: str):
        stars[z].append(name)

    for name, off in _ZIWEI_SERIES:
        put((zw + off) % 12, name)
    for name, off in _TIANFU_SERIES:
        put((tf + off) % 12, name)

    # 辅煞杂曜
    zuofu = (4 + lunar_month - 1) % 12
    youbi = (10 - (lunar_month - 1)) % 12
    wenchang = (10 - hour_zhi) % 12
    wenqu = (4 + hour_zhi) % 12
    kui, yue = _KUI_YUE[y_gan]
    lucun = _LUCUN[y_gan]
    sanhe = _sanhe(zi)
    huo = (_HUO_START[sanhe] + hour_zhi) % 12
    ling = (_LING_START[sanhe] + hour_zhi) % 12
    dikong = (11 - hour_zhi) % 12
    dijie = (11 + hour_zhi) % 12
    tianma = _TIANMA[sanhe]
    hongluan = (3 - zi) % 12

    extra = [
        ("左辅", zuofu), ("右弼", youbi), ("文昌", wenchang), ("文曲", wenqu),
        ("天魁", kui), ("天钺", yue), ("禄存", lucun),
        ("擎羊", (lucun + 1) % 12), ("陀罗", (lucun - 1) % 12),
        ("火星", huo), ("铃星", ling), ("地空", dikong), ("地劫", dijie),
        ("天马", tianma), ("红鸾", hongluan), ("天喜", (hongluan + 6) % 12),
        ("天刑", (8 + lunar_month) % 12), ("天姚", lunar_month % 12),
        ("三台", (zuofu + lunar_day - 1) % 12),
        ("八座", (youbi - (lunar_day - 1)) % 12),
    ]
    for name, z in extra:
        put(z, name)

    # 生年四化
    sh = _SIHUA[y_gan]
    hua = {sh[0]: "禄", sh[1]: "权", sh[2]: "科", sh[3]: "忌"}

    # 十二宫
    palaces = []
    for i in range(12):
        z = (ming_zhi - i) % 12
        main = [s for s in stars[z] if s in _MAIN_STARS]
        luck = [s for s in stars[z] if s in _LUCKY]
        bad = [s for s in stars[z] if s in _MALEFIC]
        palaces.append({
            "index": i,
            "name": _PALACE_NAMES[i],
            "zhi": z,
            "zhi_name": ZIWEI_DIZHI[z],
            "gan": ZIWEI_TIANGAN[gan_of[z]],
            "key": f"{ZIWEI_TIANGAN[gan_of[z]]}{ZIWEI_DIZHI[z]}",
            "main": main,
            "lucky": luck,
            "malefic": bad,
            "hua": {s: hua[s] for s in stars[z] if s in hua},
            "empty": not main,
        })

    # 大限: 阳男阴女顺行, 阴男阳女逆行, 起限 = 局数(虚岁)
    yang_year = y_gan in "甲丙戊庚壬"
    forward = (yang_year and birth.gender == "男") or (not yang_year and birth.gender == "女")
    for i, p in enumerate(palaces):
        z = (ming_zhi + i) % 12 if forward else (ming_zhi - i) % 12
        start = ju_num + i * 10
        for q in palaces:
            if q["zhi"] == z:
                q["daxian"] = (start, start + 9)

    shen_palace_index = (ming_zhi - shen_zhi) % 12

    return {
        "gender": birth.gender,
        "yin_yang": "阳" if yang_year else "阴",
        "forward": forward,
        "solar": f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}",
        "lunar": _lunar_text(year_gz, lunar_month, lunar_day, leap),
        "lunar_raw": (lunar_year, lunar_month, lunar_day, leap),
        "hour_zhi": ZIWEI_DIZHI[hour_zhi],
        "late_zi": late_zi,
        "year_gz": year_gz,
        "ju_wx": ju_wx,
        "ju_num": ju_num,
        "ju_name": ju_name,
        "ming": palaces[0],
        "shen_zhi": shen_zhi,
        "shen_key": f"{ZIWEI_TIANGAN[gan_of[shen_zhi]]}{ZIWEI_DIZHI[shen_zhi]}",
        "shen_palace": _PALACE_NAMES[shen_palace_index],
        "ming_zhu": _MING_ZHU[ming_zhi],
        "shen_zhu": _SHEN_ZHU[zi % 6],
        "ziwei_zhi": ZIWEI_DIZHI[zw],
        "tianfu_zhi": ZIWEI_DIZHI[tf],
        "palaces": palaces,
        "sihua": dict(zip(("禄", "权", "科", "忌"), sh)),
        "hour_raw": hour_zhi,
        "month_raw": lunar_month,
        "day_raw": lunar_day,
        "y_gan": y_gan,
        "y_zhi": y_zhi,
    }


# ---------------------------------------------------------------- 文本输出


def _stars_line(names: list) -> str:
    return " ".join(names) if names else "—"


def _star_with_hua(name: str, hua: dict) -> str:
    return f"{name}(化{hua[name]})" if name in hua else name


def _palace_block(p: dict, chart: dict) -> str:
    """单宫一行紧凑描述。"""
    order = {s: i for i, s in enumerate(
        ["紫微", "天机", "太阳", "武曲", "天同", "廉贞",
         "天府", "太阴", "贪狼", "巨门", "天相", "天梁", "七杀", "破军"])}
    main = sorted(p["main"], key=lambda s: order.get(s, 99))
    head = f"**{p['name']}** {p['zhi_name']}"
    body = []
    if main:
        body.append(" ".join(_star_with_hua(s, p["hua"]) for s in main))
    else:
        opposite = chart["palaces"][(p["index"] + 6) % 12]
        borrow = " ".join(opposite["main"]) or "亦无主星"
        body.append(f"空宫 · 借对宫{borrow}")
    if p["lucky"]:
        body.append("吉 " + " ".join(_star_with_hua(s, p["hua"]) for s in p["lucky"]))
    if p["malefic"]:
        body.append("煞 " + " ".join(_star_with_hua(s, p["hua"]) for s in p["malefic"]))
    return head + "｜" + "｜".join(body)


def _pattern_lines(chart: dict) -> list:
    """格局速读(规则式, 只做结构性判断, 不下吉凶结论)。"""
    ps = chart["palaces"]
    ming = ps[0]
    sanfang = [ps[0], ps[4], ps[8], ps[6]]   # 命 财帛 官禄 迁移
    sanfang_stars = set()
    for p in sanfang:
        sanfang_stars.update(p["main"])
    out: list = []

    main = set(ming["main"])
    if not main:
        opp = ps[6]
        out.append(f"命宫无主星，借对宫（{opp['zhi_name']}）{' '.join(opp['main']) or '亦空'} 安命，"
                   "性格多随外境而动。")
    else:
        out.append(f"命宫主星：{' '.join(sorted(main, key=lambda s: ['紫微','天机','太阳','武曲','天同','廉贞','天府','太阴','贪狼','巨门','天相','天梁','七杀','破军'].index(s)))}，"
                   f"坐{ZIWEI_DIZHI[ming['zhi']]}宫。")

    if {"七杀", "破军", "贪狼"} & sanfang_stars:
        hit = "、".join(sorted({"七杀", "破军", "贪狼"} & sanfang_stars))
        out.append(f"三方见 {hit} —— 杀破狼格：一生变动多，宜在动中求成。")
    if {"天机", "太阴", "天同", "天梁"} <= sanfang_stars:
        out.append("机月同梁齐会 —— 机月同梁格：宜公职、文教、参谋类工作，稳中取胜。")
    if {"紫微", "天府"} & main:
        out.append("帝星坐命 —— 重面子与主导权，喜被尊重，不耐被指挥。")
    if "禄存" in ming["lucky"] or ming["hua"].get("禄"):
        out.append("命宫见禄 —— 财禄之气聚于自身，宜守成积累。")
    evils = {"擎羊", "陀罗", "火星", "铃星", "地空", "地劫"} & set(ming["malefic"])
    if len(evils) >= 2:
        out.append(f"命宫煞星偏多（{'、'.join(sorted(evils))}），行事宜留余步，忌孤注一掷。")

    out.append(f"身宫落「{chart['shen_palace']}」—— 中年后着力于此。")
    return out


def format_ziwei(chart: dict) -> str:
    """命盘 -> 可读文本。"""
    yy = f"{chart['yin_yang']}{chart['gender']}"
    direction = "顺行" if chart["forward"] else "逆行"
    lines = [
        f"【紫微斗数】{yy} · {chart['ju_name']}",
        f"{chart['lunar']} {chart['hour_zhi']}时 · 公历 {chart['solar']}",
        f"命宫 {chart['ming']['zhi_name']}（{chart['ming']['key']}）"
        f" · 身宫 {ZIWEI_DIZHI[chart['shen_zhi']]}（{chart['shen_key']}）"
        f" · 身在{chart['shen_palace']}",
        f"命主 {chart['ming_zhu']} · 身主 {chart['shen_zhu']}"
        f" · 大限{direction} · 起限 {chart['ju_num']} 岁（虚）",
        f"紫微在{chart['ziwei_zhi']} · 天府在{chart['tianfu_zhi']}",
        "",
        "**十二宫**",
    ]
    for p in chart["palaces"]:
        lines.append("· " + _palace_block(p, chart))

    lines.append("")
    lines.append("**大限**（虚岁）")
    seq = sorted(chart["palaces"], key=lambda p: p["daxian"][0])
    for start in range(0, 12, 4):
        chunk = seq[start:start + 4]
        lines.append("　" + " · ".join(
            f"{p['daxian'][0]}-{p['daxian'][1]} {p['name']}({p['zhi_name']})" for p in chunk))

    lines.append("")
    lines.append("**生年四化**（{0}干）".format(chart["y_gan"]))
    sh = chart["sihua"]
    lines.append("　" + "　".join(f"{sh[k]}化{k}" for k in ("禄", "权", "科", "忌")))

    lines.append("")
    lines.append("**格局速读**")
    for t in _pattern_lines(chart):
        lines.append("· " + t)

    if chart["late_zi"]:
        lines.append("")
        lines.append("※ 出生于 23 点后，已按次日子时起盘。")
    lines.append("")
    lines.append("※ 紫微斗数流派众多（四化、亮度、闰月处理各有出入），本盘为通行排法，仅供传统文化参考。")
    return "\n".join(lines)
