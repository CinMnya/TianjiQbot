"""奇门遁甲排盘（时家奇门 · 拆补法）。"""

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


QIMEN_JQ_JU = {
    "冬至": (1, 7, 4), "小寒": (2, 8, 5), "大寒": (3, 9, 6),
    "立春": (8, 5, 2), "雨水": (9, 6, 3), "惊蛰": (1, 7, 4),
    "春分": (3, 9, 6), "清明": (4, 1, 7), "谷雨": (5, 2, 8),
    "立夏": (4, 1, 7), "小满": (5, 2, 8), "芒种": (6, 3, 9),
    "夏至": (9, 3, 6), "小暑": (8, 2, 5), "大暑": (7, 1, 4),
    "立秋": (2, 5, 8), "处暑": (1, 4, 7), "白露": (9, 3, 6),
    "秋分": (7, 1, 4), "寒露": (6, 9, 3), "霜降": (5, 8, 2),
    "立冬": (6, 9, 3), "小雪": (5, 8, 2), "大雪": (4, 7, 1),
}

# 冬至到芒种用阳遁，夏至到大雪用阴遁
QIMEN_YANG = ("冬至", "小寒", "大寒", "立春", "雨水", "惊蛰",
              "春分", "清明", "谷雨", "立夏", "小满", "芒种")

QIMEN_GONG_NAME = {1: "坎一宫", 2: "坤二宫", 3: "震三宫", 4: "巽四宫",
                   5: "中五宫", 6: "乾六宫", 7: "兑七宫", 8: "艮八宫",
                   9: "离九宫"}
QIMEN_GONG_FANG = {1: "正北", 2: "西南", 3: "正东", 4: "东南", 5: "中宫",
                   6: "西北", 7: "正西", 8: "东北", 9: "正南"}

# 九星本宫 / 八门本宫
QIMEN_STAR_HOME = {1: "天蓬", 2: "天芮", 3: "天冲", 4: "天辅", 5: "天禽",
                   6: "天心", 7: "天柱", 8: "天任", 9: "天英"}
QIMEN_DOOR_HOME = {1: "休门", 2: "死门", 3: "伤门", 4: "杜门",
                   6: "开门", 7: "惊门", 8: "生门", 9: "景门"}

# 后天八卦顺时针环序(不含中五宫)
QIMEN_RING = (1, 8, 3, 4, 9, 2, 7, 6)
_RING_POS = {g: i for i, g in enumerate(QIMEN_RING)}

# 八门顺时针次序 / 八神次序
QIMEN_DOOR_RING = ("休门", "生门", "伤门", "杜门", "景门", "死门", "惊门", "开门")
QIMEN_SHEN_RING = ("值符", "腾蛇", "太阴", "六合", "白虎", "玄武", "九地", "九天")

QIMEN_LIUYI = "戊己庚辛壬癸"      # 六仪(对应六甲旬)
QIMEN_SANQI = "丁丙乙"            # 三奇逆序入盘
QIMEN_DIPAN_ORDER = QIMEN_LIUYI + QIMEN_SANQI   # 戊己庚辛壬癸丁丙乙

# 吉门 / 凶门(用于要点提示，不下断语)
QIMEN_JI_DOORS = frozenset({"开门", "休门", "生门"})


# ---------------------------------------------------------------- 基础换算


def _gz_index(gz: str) -> int:
    """干支 -> 六十甲子序号(0-59)。"""
    if not gz or len(gz) < 2:
        return 0
    g = GAN.index(gz[0]) if gz[0] in GAN else 0
    z = ZHI.index(gz[1]) if gz[1] in ZHI else 0
    for n in range(60):
        if n % 10 == g and n % 12 == z:
            return n
    return 0


def _ring(gong: int) -> int:
    """中五宫寄坤二宫。"""
    return 2 if gong == 5 else gong


def _dipan(ju: int, yang: bool) -> dict:
    """地盘三奇六仪: 戊起局数宫，阳遁顺行、阴遁逆行(遇宫循环)。"""
    out = {}
    g = ju
    step = 1 if yang else -1
    for gan in QIMEN_DIPAN_ORDER:
        out[g] = gan
        g += step
        if g > 9:
            g = 1
        if g < 1:
            g = 9
    return out


def _jieqi_info(lunar, dt: datetime):
    """当前节气、交节时间、节气内第几日。"""
    try:
        jq = lunar.getPrevJieQi()
        name = jq.getName()
        s = jq.getSolar()
        start = datetime(s.getYear(), s.getMonth(), s.getDay(), s.getHour(), s.getMinute())
    except Exception:
        name, start = "冬至", dt
    if name not in QIMEN_JQ_JU:
        # 极少数返回英文/全名，退化为按时间就近匹配
        name = next((k for k in QIMEN_JQ_JU if k in str(name)), "冬至")
    days = (dt.date() - start.date()).days + 1
    days = max(1, days)
    return name, start, days


def _yuan(days: int):
    """拆补法: 节气内五日一元，第 11 日起下元，超出的按第三元继续。"""
    idx = (days - 1) // 5
    if idx > 2:
        idx = 2
    return ("上元", "中元", "下元")[idx], idx


# ---------------------------------------------------------------- 排盘


def cast_qimen(when: str = "") -> dict:
    """排一个时家奇门盘。when 为空用当前时间，也可传 2026-10-24 11:53。"""
    dt = _parse_when(when)
    solar = Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, 0)
    lunar = solar.getLunar()

    year_gz = lunar.getYearInGanZhi()
    month_gz = lunar.getMonthInGanZhi()
    day_gz = lunar.getDayInGanZhi()
    time_gz = lunar.getTimeInGanZhi()

    jq_name, jq_start, jq_days = _jieqi_info(lunar, dt)
    yuan_name, yuan_idx = _yuan(jq_days)
    yang = jq_name in QIMEN_YANG
    ju = QIMEN_JQ_JU[jq_name][yuan_idx]

    # 地盘
    dipan = _dipan(ju, yang)

    # 旬首
    n_time = _gz_index(time_gz)
    xun_idx = n_time // 10                  # 0=甲子旬 ... 5=甲寅旬
    xun_gan = QIMEN_LIUYI[xun_idx]          # 旬首所遁之仪
    xun_zhi = ZHI[(n_time - n_time % 10) % 12]
    xun_name = f"甲{xun_zhi}({xun_gan})"

    # 值符宫(旬首仪所在地盘宫) / 时干宫
    fu_gong = next((g for g, gan in dipan.items() if gan == xun_gan), ju)
    shi_gan = time_gz[0]
    shi_gan_use = xun_gan if shi_gan == "甲" else shi_gan
    shi_gong = next((g for g, gan in dipan.items() if gan == shi_gan_use), ju)

    fu_gong_r = _ring(fu_gong)
    shi_gong_r = _ring(shi_gong)

    fu_star = QIMEN_STAR_HOME[fu_gong_r]
    fu_door = QIMEN_DOOR_HOME[fu_gong_r]
    # 旬首在中五宫: 天禽寄坤二，值符取天禽(随天芮)
    if fu_gong == 5:
        fu_star = "天禽"

    # 天盘九星: 值符星加时干宫，其余按环序整体转
    shift = (_RING_POS[shi_gong_r] - _RING_POS[fu_gong_r]) % 8
    stars, tian_gan = {}, {}
    for g in QIMEN_RING:
        tgt = QIMEN_RING[(_RING_POS[g] + shift) % 8]
        stars[tgt] = QIMEN_STAR_HOME[g]
        tian_gan[tgt] = dipan.get(g, "")

    # 人盘八门: 值使门随旬首到时支的步数，阳顺阴逆
    steps = (_gz_index(time_gz) % 12 - ZHI.index(xun_zhi)) % 12
    d0_pos = _RING_POS[fu_gong_r]
    d_pos = (d0_pos + steps) % 8 if yang else (d0_pos - steps) % 8
    door_gong = QIMEN_RING[d_pos]
    doors = {}
    i0 = QIMEN_DOOR_RING.index(fu_door)
    for k in range(8):
        doors[QIMEN_RING[(d_pos + k) % 8]] = QIMEN_DOOR_RING[(i0 + k) % 8]

    # 神盘八神: 值符神起于天盘值符落宫，阳顺阴逆
    shen = {}
    s_start = _RING_POS[shi_gong_r]
    for k in range(8):
        pos = (s_start + k) % 8 if yang else (s_start - k) % 8
        shen[QIMEN_RING[pos]] = QIMEN_SHEN_RING[k]

    palaces = []
    for g in range(1, 10):
        if g == 5:
            palaces.append({
                "gong": 5,
                "name": QIMEN_GONG_NAME[5],
                "fangwei": QIMEN_GONG_FANG[5],
                "star": "天禽",
                "door": "—",
                "shen": "—",
                "gan_di": dipan.get(5, ""),
                "gan_tian": "",
                "ji": False,
            })
            continue
        palaces.append({
            "gong": g,
            "name": QIMEN_GONG_NAME[g],
            "fangwei": QIMEN_GONG_FANG[g],
            "star": stars.get(g, ""),
            "door": doors.get(g, ""),
            "shen": shen.get(g, ""),
            "gan_di": dipan.get(g, ""),
            "gan_tian": tian_gan.get(g, ""),
            "ji": doors.get(g) in QIMEN_JI_DOORS,
        })

    by_gong = {p["gong"]: p for p in palaces}

    # 日干宫 / 时干宫(用于人我关系提示)
    day_gan = day_gz[0]
    day_gan_use = day_gan
    if day_gan == "甲":
        dn = _gz_index(day_gz)
        day_gan_use = QIMEN_LIUYI[dn // 10]
    ri_gong = next((g for g, gan in dipan.items() if gan == day_gan_use), 0)

    return {
        "dt": dt,
        "solar": f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}",
        "clock": f"{dt.hour:02d}:{dt.minute:02d}",
        "year_gz": year_gz,
        "month_gz": month_gz,
        "day_gz": day_gz,
        "time_gz": time_gz,
        "jieqi": jq_name,
        "jieqi_start": jq_start.strftime("%Y-%m-%d %H:%M"),
        "jieqi_days": jq_days,
        "yuan": yuan_name,
        "yang": yang,
        "ju": ju,
        "ju_name": f"{'阳' if yang else '阴'}遁{_ju_cn(ju)}局",
        "dipan": dipan,
        "xun": xun_name,
        "xun_gan": xun_gan,
        "fu_star": fu_star,
        "fu_door": fu_door,
        "fu_gong": fu_gong,
        "fu_land": shi_gong_r,
        "fu_land_name": QIMEN_GONG_NAME[shi_gong_r],
        "shi_gan": shi_gan,
        "shi_gong": shi_gong,
        "door_gong": door_gong,
        "palaces": palaces,
        "by_gong": by_gong,
        "day_gan": day_gan,
        "ri_gong": ri_gong,
        "ji_doors": [p for p in palaces if p["ji"]],
        "patterns": _patterns(palaces, by_gong, fu_gong, shi_gong, shift,
                              fu_star, fu_door, door_gong, yang, dipan),
    }


def _ju_cn(ju: int) -> str:
    return ("", "一", "二", "三", "四", "五", "六", "七", "八", "九")[ju]


def _parse_when(when: str) -> datetime:
    when = (when or "").strip()
    if not when:
        return datetime.now()
    m = None
    for pat in (r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?\s*(\d{1,2})[:：时点]?(\d{1,2})?",
                r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})"):
        m = re.search(pat, when)
        if m:
            break
    if not m:
        return datetime.now()
    g = m.groups()
    hh = int(g[3]) if len(g) > 3 and g[3] else 0
    mm = int(g[4]) if len(g) > 4 and g[4] else 0
    return datetime(int(g[0]), int(g[1]), int(g[2]), min(hh, 23), min(mm, 59))


def _patterns(palaces, by_gong, fu_gong, shi_gong, shift, fu_star,
              fu_door, door_gong, yang, dipan) -> list:
    """格局要点(结构性提示, 不下吉凶断语)。"""
    out = []
    zhi_fu_palace = by_gong.get(_ring(shi_gong), {})
    out.append(
        f"值符{fu_star}落{by_gong[_ring(shi_gong)]['name']}"
        f"（{by_gong[_ring(shi_gong)]['fangwei']}），值使{fu_door}落"
        f"{by_gong[door_gong]['name']}（{by_gong[door_gong]['fangwei']}）。"
    )
    if shift == 0:
        out.append("值符归本宫 —— 天盘伏吟：局面偏静，事情容易拖延反复，"
                   "宜守成、宜等，不宜仓促开新局。")
    elif shift == 4:
        out.append("值符落对冲宫 —— 天盘反吟：变动大、来回拉扯，"
                   "计划容易被打乱，先把节奏稳住再谈推进。")
    if door_gong == _ring(fu_gong):
        out.append("值使门归本宫 —— 人盘伏吟：人际与执行层面容易卡住，"
                   "同一件事要来回确认几次才动得了。")

    ji = [p for p in palaces if p["ji"]]
    if ji:
        out.append("三吉门（开/休/生）落宫：" + "、".join(
            f"{p['door']}在{p['name']}（{p['fangwei']}）" for p in ji) +
            "。这几个方位是盘上气口，谈事、见面、出行可优先考虑。")
    else:
        out.append("三吉门未明现或落宫受制，做事更依赖人和与准备，别指望方位帮忙。")

    # 三奇(乙丙丁)落宫
    qi = []
    for p in palaces:
        if p["gong"] == 5:
            continue
        if p["gan_tian"] in ("乙", "丙", "丁") or p["gan_di"] in ("乙", "丙", "丁"):
            tag = []
            if p["gan_tian"] in ("乙", "丙", "丁"):
                tag.append(f"天盘{p['gan_tian']}")
            if p["gan_di"] in ("乙", "丙", "丁"):
                tag.append(f"地盘{p['gan_di']}")
            qi.append(f"{p['name']}（{p['fangwei']}）{'/'.join(tag)}")
    if qi:
        out.append("三奇分布：" + "；".join(qi[:4]) +
                   "。三奇所在是盘上最「活」的位置，适合放需要灵感和转机的事。")
    return out


# ---------------------------------------------------------------- 文本输出


def format_qimen(chart: dict) -> str:
    lines = [
        f"【奇门遁甲】{chart['ju_name']} · 拆补法 · 转盘",
        f"{chart['solar']} {chart['clock']} · "
        f"{chart['year_gz']}年 {chart['month_gz']}月 {chart['day_gz']}日 {chart['time_gz']}时",
        f"节气 {chart['jieqi']} · {chart['yuan']}（第{chart['jieqi_days']}日）"
        f" · 旬首 {chart['xun']}",
        f"值符 {chart['fu_star']} · 值使 {chart['fu_door']} · 时干 {chart['shi_gan']}",
        "",
    ]
    if chart["shi_gan"] == "甲":
        lines[3] = (f"值符 {chart['fu_star']} · 值使 {chart['fu_door']} · "
                    f"时干 甲（用旬首{chart['xun_gan']}）")
    lines.append("**九宫盘**（天盘干 星 门 神 —— 地盘干）")
    order = [4, 9, 2, 3, 5, 7, 8, 1, 6]     # 巽离坤 / 震中兑 / 艮坎乾
    row_txt = []
    for i, g in enumerate(order):
        p = chart["by_gong"][g]
        if g == 5:
            cell = f"中五宫｜天禽(寄坤)｜地盘{p['gan_di'] or '—'}"
        else:
            cell = (f"{p['name']}｜{p['gan_tian']} {p['star']} {p['door']} {p['shen']}"
                    f"｜地{p['gan_di']}")
        row_txt.append("· " + cell)
        if i % 3 == 2:
            lines.append("　".join(row_txt))
            row_txt = []

    lines.append("")
    lines.append("**要点**")
    for t in chart["patterns"]:
        lines.append("· " + t)

    lines.append("")
    lines.append("※ 奇门流派众多（置闰/拆补、转盘/飞盘、中宫寄宫各有不同），"
                 "本盘为拆补法转盘排法，仅供传统文化参考。")
    return "\n".join(lines)


def qimen(arg: str = "") -> str:
    """指令入口: 奇门 [时间] -> 文本。"""
    return format_qimen(cast_qimen(arg))
