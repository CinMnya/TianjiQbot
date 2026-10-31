"""大六壬排盘（月将加时 · 九宗门）。"""

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


LIUREN_ZHI = "子丑寅卯辰巳午未申酉戌亥"
LIUREN_GAN = "甲乙丙丁戊己庚辛壬癸"

# 中气 -> 月将(太阳过宫)
LIUREN_JIANG = {
    "大寒": (0, "神后"), "雨水": (11, "登明"), "春分": (10, "河魁"),
    "谷雨": (9, "从魁"), "小满": (8, "传送"), "夏至": (7, "小吉"),
    "大暑": (6, "胜光"), "处暑": (5, "太乙"), "秋分": (4, "天罡"),
    "霜降": (3, "太冲"), "小雪": (2, "功曹"), "冬至": (1, "大吉"),
}

# 十二天将(贵人起，顺/逆布)
LIUREN_SHEN = ("贵人", "螣蛇", "朱雀", "六合", "勾陈", "青龙",
               "天空", "白虎", "太常", "玄武", "太阴", "天后")

# 日干寄宫(十干寄十二支)
LIUREN_JIGONG = {"甲": 2, "乙": 4, "丙": 5, "丁": 7, "戊": 5,
                 "己": 7, "庚": 8, "辛": 10, "壬": 11, "癸": 1}

# 日干 -> (昼贵, 夜贵)
LIUREN_GUIREN = {
    "甲": (1, 7), "戊": (1, 7), "庚": (1, 7),
    "乙": (0, 8), "己": (0, 8),
    "丙": (11, 9), "丁": (11, 9),
    "壬": (3, 5), "癸": (3, 5),
    "辛": (6, 2),
}

# 地支 -> 五行
LIUREN_WX = {
    0: "水", 1: "土", 2: "木", 3: "木", 4: "土", 5: "火",
    6: "火", 7: "土", 8: "金", 9: "金", 10: "土", 11: "水",
}
LIUREN_GAN_WX = {"甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
                 "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水"}

# 相克: 木克土 土克水 水克火 火克金 金克木
LIUREN_KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
# 相生: 木生火 火生土 土生金 金生水 水生木
LIUREN_SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}

# 支刑(用于伏吟递传)；自刑者取冲
LIUREN_XING = {0: 3, 3: 0, 2: 5, 5: 8, 8: 2, 1: 10, 10: 7, 7: 1,
               4: 4, 6: 6, 9: 9, 11: 11}

# 三合局驿马: 申子辰马在寅, 寅午戌马在申, 巳酉丑马在亥, 亥卯未马在巳
LIUREN_MA = {8: 2, 0: 2, 4: 2, 2: 8, 6: 8, 10: 8,
             5: 11, 9: 11, 1: 11, 11: 5, 3: 5, 7: 5}

LIUREN_MONTH_CN = ("正", "二", "三", "四", "五", "六",
                   "七", "八", "九", "十", "冬", "腊")


# ---------------------------------------------------------------- 基础换算


def _ke(a_wx: str, b_wx: str) -> bool:
    """a 五行克 b 五行。"""
    return LIUREN_KE.get(a_wx) == b_wx


def _zhi_ke(a: int, b: int) -> bool:
    return _ke(LIUREN_WX[a], LIUREN_WX[b])


def _lr_liuqin(day_gan: str, zhi: int) -> str:
    """以日干为我，判地支六亲。"""
    me = LIUREN_GAN_WX[day_gan]
    it = LIUREN_WX[zhi]
    if me == it:
        return "兄弟"
    if LIUREN_KE.get(me) == it:
        return "妻财"
    if LIUREN_KE.get(it) == me:
        return "官鬼"
    if LIUREN_SHENG.get(me) == it:
        return "子孙"
    return "父母"


def _yuejiang(lunar, dt: datetime):
    """取最近已过的中气对应的月将。"""
    cur = lunar
    for _ in range(3):
        try:
            jq = cur.getPrevJieQi()
        except Exception:
            break
        name = jq.getName()
        s = jq.getSolar()
        start = datetime(s.getYear(), s.getMonth(), s.getDay(),
                         s.getHour(), s.getMinute())
        if name in LIUREN_JIANG:
            return name, LIUREN_JIANG[name], start
        # 前一个是「节」，继续往前找一个中气
        cur = Solar.fromYmdHms(s.getYear(), s.getMonth(), s.getDay(), 12, 0, 0).getLunar()
    return "冬至", LIUREN_JIANG["冬至"], dt


def _xunkong(day_gz: str) -> list:
    """旬空二支。"""
    g = LIUREN_GAN.index(day_gz[0])
    z = LIUREN_ZHI.index(day_gz[1])
    n = next((i for i in range(60) if i % 10 == g and i % 12 == z), 0)
    head = n - n % 10
    z1 = (head + 10) % 12
    z2 = (head + 11) % 12
    return [z1, z2]


def _lr_parse_when(when: str) -> datetime:
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


# ---------------------------------------------------------------- 排盘


def cast_liuren(when: str = "") -> dict:
    dt = _lr_parse_when(when)
    solar = Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, 0)
    lunar = solar.getLunar()

    year_gz = lunar.getYearInGanZhi()
    month_gz = lunar.getMonthInGanZhi()
    day_gz = lunar.getDayInGanZhi()
    time_gz = lunar.getTimeInGanZhi()
    day_gan = day_gz[0]

    shi_zhi = (dt.hour + 1) // 2 % 12
    jq_name, (yj, yj_name), jq_start = _yuejiang(lunar, dt)

    # 天盘: 月将加于时支，其余顺布
    tianpan = [(yj + i - shi_zhi) % 12 for i in range(12)]

    def pos_of(tian: int) -> int:
        """天盘某神所临的地盘位。"""
        return (tian - yj + shi_zhi) % 12

    # ---- 四课 ----
    ji = LIUREN_JIGONG[day_gan]
    ke = []
    up1 = tianpan[ji]
    ke.append({"no": 1, "up": up1, "down": ji, "down_label": f"{day_gan}"})
    up2 = tianpan[up1]
    ke.append({"no": 2, "up": up2, "down": up1, "down_label": LIUREN_ZHI[up1]})
    ri_zhi = LIUREN_ZHI.index(day_gz[1])
    up3 = tianpan[ri_zhi]
    ke.append({"no": 3, "up": up3, "down": ri_zhi, "down_label": LIUREN_ZHI[ri_zhi]})
    up4 = tianpan[up3]
    ke.append({"no": 4, "up": up4, "down": up3, "down_label": LIUREN_ZHI[up3]})

    # ---- 三传 ----
    chuan, method = _sanchuan(ke, tianpan, day_gan, ri_zhi, ji, yj, shi_zhi, day_gz)

    # ---- 十二天将 ----
    day_yang = LIUREN_GAN.index(day_gan) % 2 == 0
    is_day = 3 <= shi_zhi <= 8          # 卯~申为昼
    gui_zhi = LIUREN_GUIREN[day_gan][0 if is_day else 1]
    gui_pos = pos_of(gui_zhi)
    forward = gui_pos in (11, 0, 1, 2, 3, 4)   # 亥子丑寅卯辰为阳，顺行
    jiang = [""] * 12
    for k in range(12):
        p = (gui_pos + k) % 12 if forward else (gui_pos - k) % 12
        jiang[p] = LIUREN_SHEN[k]

    # ---- 六亲/旬空/驿马 ----
    kong = _xunkong(day_gz)
    ma = LIUREN_MA[ri_zhi]

    for k in ke:
        k["up_name"] = LIUREN_ZHI[k["up"]]
        k["lin"] = pos_of(k["up"])
        k["lin_name"] = LIUREN_ZHI[k["lin"]]
        k["jiang"] = jiang[k["lin"]]
        k["liuqin"] = _lr_liuqin(day_gan, k["up"])
        k["kong"] = k["up"] in kong

    for i, c in enumerate(chuan):
        c["no"] = i + 1
        c["name"] = LIUREN_ZHI[c["zhi"]]
        c["lin"] = pos_of(c["zhi"])
        c["lin_name"] = LIUREN_ZHI[c["lin"]]
        c["jiang"] = jiang[c["lin"]]
        c["liuqin"] = _lr_liuqin(day_gan, c["zhi"])
        c["kong"] = c["zhi"] in kong
        c["ma"] = c["zhi"] == ma

    return {
        "dt": dt,
        "solar": f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}",
        "clock": f"{dt.hour:02d}:{dt.minute:02d}",
        "year_gz": year_gz,
        "month_gz": month_gz,
        "day_gz": day_gz,
        "time_gz": time_gz,
        "day_gan": day_gan,
        "ri_zhi": ri_zhi,
        "shi_zhi": shi_zhi,
        "shi_name": LIUREN_ZHI[shi_zhi],
        "jieqi": jq_name,
        "jieqi_start": jq_start.strftime("%Y-%m-%d %H:%M"),
        "yuejiang": yj,
        "yuejiang_name": yj_name,
        "tianpan": tianpan,
        "jiang": jiang,
        "ke": ke,
        "chuan": chuan,
        "method": method,
        "xunkong": kong,
        "ma": ma,
        "zhou": "昼占" if is_day else "夜占",
        "guiren": LIUREN_ZHI[gui_zhi],
        "guiren_name": LIUREN_SHEN[0],
        "forward": forward,
        "notes": _notes(ke, chuan, method, kong, ma, day_gan),
    }


def _pairs_ke(ke: list):
    """返回 (下贼上列表, 上克下列表)，元素为四课序号。"""
    xia, shang = [], []
    for k in ke:
        if _zhi_ke(k["down"], k["up"]):
            xia.append(k)
        elif _zhi_ke(k["up"], k["down"]):
            shang.append(k)
    return xia, shang


def _biyong(cands: list, day_gan: str):
    """比用: 取与日干同阴阳的上神。"""
    yang = LIUREN_GAN.index(day_gan) % 2 == 0
    hit = [c for c in cands if (c["up"] % 2 == 0) == yang]
    return hit


def _shehai(c: dict) -> int:
    """涉害深度: 上神自所临地盘位归本家，沿途相克之数。"""
    up, down = c["up"], c["down"]
    steps = (up - down) % 12
    cnt = 0
    for k in range(1, steps + 1):
        z = (down + k) % 12
        if _zhi_ke(z, up) or _zhi_ke(up, z):
            cnt += 1
    return cnt


def _pick_by_ke(cands: list, day_gan: str) -> dict:
    """在若干克候选中按 比用 -> 涉害 -> 孟仲 定初传。"""
    if len(cands) == 1:
        return cands[0]
    bi = _biyong(cands, day_gan)
    if len(bi) == 1:
        return bi[0]
    pool = bi or cands
    if len(pool) == 1:
        return pool[0]
    deep = max(_shehai(c) for c in pool)
    pool = [c for c in pool if _shehai(c) == deep]
    if len(pool) == 1:
        return pool[0]
    for group in ((2, 5, 8, 11), (0, 3, 6, 9)):   # 孟(寅申巳亥) 再 仲(子午卯酉)
        hit = [c for c in pool if c["up"] in group]
        if hit:
            return hit[0]
    return pool[0]


def _sanchuan(ke, tianpan, day_gan, ri_zhi, ji, yj, shi_zhi, day_gz):
    """九宗门定三传，返回 (三传地支列表, 课体名)。"""
    up1, up3 = ke[0]["up"], ke[2]["up"]
    chuan = []

    # 伏吟: 月将 == 时支
    if yj == shi_zhi:
        xia, shang = _pairs_ke(ke)
        if xia or shang:
            c = _pick_by_ke(xia or shang, day_gan)
            first = c["up"]
            tag = "伏吟（有克）"
        else:
            first = up1 if LIUREN_GAN.index(day_gan) % 2 == 0 else up3
            tag = "伏吟（自任/自信）"
        mid = LIUREN_XING[first]
        if mid == first:
            mid = (first + 6) % 12
        last = LIUREN_XING[mid]
        if last == mid:
            last = (mid + 6) % 12
        return [{"zhi": first}, {"zhi": mid}, {"zhi": last}], tag

    # 返吟: 天地盘相冲
    if (yj - shi_zhi) % 12 == 6:
        xia, shang = _pairs_ke(ke)
        if xia or shang:
            c = _pick_by_ke(xia or shang, day_gan)
            chuan = [{"zhi": c["up"]}]
            tag = "返吟（有克）"
        else:
            chuan = [{"zhi": LIUREN_MA[ri_zhi]}]
            tag = "返吟（无克取马）"
        chuan.append({"zhi": up3})
        chuan.append({"zhi": up1})
        return chuan, tag

    xia, shang = _pairs_ke(ke)
    if xia:
        c = _pick_by_ke(xia, day_gan)
        tag = "贼克（下贼上）" if len(xia) == 1 else (
            "比用" if len(_biyong(xia, day_gan)) == 1 else "涉害")
        chuan = [{"zhi": c["up"]}]
    elif shang:
        c = _pick_by_ke(shang, day_gan)
        tag = "贼克（上克下）" if len(shang) == 1 else (
            "比用" if len(_biyong(shang, day_gan)) == 1 else "涉害")
        chuan = [{"zhi": c["up"]}]
    else:
        me = LIUREN_GAN_WX[day_gan]
        # 遥克: 蒿矢(上神克日干) / 弹射(日干克上神)
        yao = [k for k in ke if _ke(LIUREN_WX[k["up"]], me)]
        if yao:
            c = _pick_by_ke(yao, day_gan) if len(yao) > 1 else yao[0]
            chuan = [{"zhi": c["up"]}]
            tag = "遥克（蒿矢）"
        else:
            yao = [k for k in ke if _ke(me, LIUREN_WX[k["up"]])]
            if yao:
                c = _pick_by_ke(yao, day_gan) if len(yao) > 1 else yao[0]
                chuan = [{"zhi": c["up"]}]
                tag = "遥克（弹射）"
            else:
                yang = LIUREN_GAN.index(day_gan) % 2 == 0
                if ji == ri_zhi:
                    # 八专: 干支同位，实际只有两课
                    base = up1
                    first = (base + 2) % 12 if yang else (base - 2) % 12
                    chuan = [{"zhi": first}, {"zhi": up1}, {"zhi": up1}]
                    tag = "八专"
                elif len({(k["up"], k["down"]) for k in ke}) == 3:
                    # 别责: 四课不全
                    if yang:
                        he_gan = LIUREN_GAN[(LIUREN_GAN.index(day_gan) + 5) % 10]
                        first = tianpan[LIUREN_JIGONG[he_gan]]
                    else:
                        first = tianpan[(ri_zhi + 4) % 12]
                    chuan = [{"zhi": first}, {"zhi": up1}, {"zhi": up1}]
                    tag = "别责"
                else:
                    # 昴星
                    if yang:
                        first = tianpan[9]          # 地盘酉上神
                    else:
                        first = (9 - yj + shi_zhi) % 12   # 天盘酉下神
                    if yang:
                        chuan = [{"zhi": first}, {"zhi": up3}, {"zhi": up1}]
                    else:
                        chuan = [{"zhi": first}, {"zhi": up1}, {"zhi": up3}]
                    tag = "昴星"

    # 中传末传递取
    if len(chuan) == 1:
        mid = tianpan[chuan[0]["zhi"]]
        last = tianpan[mid]
        chuan.append({"zhi": mid})
        chuan.append({"zhi": last})
    return chuan, tag


def _notes(ke, chuan, method, kong, ma, day_gan) -> list:
    out = [f"课体：{method}。"]
    names = " → ".join(f"{LIUREN_ZHI[c['zhi']]}({_lr_liuqin(day_gan, c['zhi'])})"
                       for c in chuan)
    out.append(f"三传：{names}。")
    tail = _lr_liuqin(day_gan, chuan[-1]["zhi"])
    head = _lr_liuqin(day_gan, chuan[0]["zhi"])
    out.append(f"初传为{head}，末传为{tail} —— 事情的起手落在「{head}」，"
               f"收束落在「{tail}」。")
    hit = [LIUREN_ZHI[c["zhi"]] for c in chuan if c["zhi"] in kong]
    if hit:
        out.append("三传逢空：" + "、".join(hit) +
                   "。空不是没有，是「暂时不落实」，这一段容易停在口头上。")
    if any(c["zhi"] == ma for c in chuan):
        out.append("三传见驿马：事有动象，主奔走、迁动、线路变化。")
    return out


# ---------------------------------------------------------------- 文本输出


def format_liuren(c: dict) -> str:
    lines = [
        f"【大六壬】月将 {LIUREN_ZHI[c['yuejiang']]}（{c['yuejiang_name']}）"
        f"加 {c['shi_name']}时",
        f"{c['solar']} {c['clock']} · {c['year_gz']}年 {c['month_gz']}月 "
        f"{c['day_gz']}日 {c['time_gz']}时",
        f"节气 {c['jieqi']} · {c['zhou']} · 贵人 {c['guiren']}"
        f"（{'顺行' if c['forward'] else '逆行'}）",
        "旬空 " + "".join(LIUREN_ZHI[z] for z in c["xunkong"]) +
        f" · 驿马 {LIUREN_ZHI[c['ma']]} · 课体 {c['method']}",
        "",
        "**天地盘**（地盘 → 天盘 / 天将）",
    ]
    # 四行三位排布: 子丑寅 / 卯辰巳 ...
    for start in range(0, 12, 6):
        seg1 = "　".join(f"{LIUREN_ZHI[i]}→{LIUREN_ZHI[c['tianpan'][i]]}"
                        f"{c['jiang'][i]}" for i in range(start, start + 3))
        seg2 = "　".join(f"{LIUREN_ZHI[i]}→{LIUREN_ZHI[c['tianpan'][i]]}"
                        f"{c['jiang'][i]}" for i in range(start + 3, start + 6))
        lines.append("· " + seg1 + "　｜　" + seg2)

    lines.append("")
    lines.append("**四课**（上神 / 下神 · 天将 · 六亲）")
    for k in reversed(c["ke"]):
        down = k["down_label"]
        if k["no"] == 1:
            down = f"{down}(寄{LIUREN_ZHI[k['down']]})"
        lines.append(f"· {_cn_no(k['no'])}课：{k['up_name']} / {down}"
                     f" · {k['jiang']} · {k['liuqin']}"
                     + ("　空" if k["kong"] else ""))

    lines.append("")
    lines.append("**三传**（传 / 天将 / 所临 / 六亲）")
    for ch in c["chuan"]:
        tag = ""
        if ch["kong"]:
            tag += "　空"
        if ch["ma"]:
            tag += "　马"
        lines.append(f"· {_cn_chuan(ch['no'])}传：{ch['name']} / {ch['jiang']}"
                     f" / 临{ch['lin_name']} · {ch['liuqin']}{tag}")

    lines.append("")
    lines.append("**要点**")
    for t in c["notes"]:
        lines.append("· " + t)

    lines.append("")
    lines.append("※ 大六壬流派众多（月将换将、贵人起法、涉害深浅、中末递取各有出入），"
                 "本盘为通行九宗门排法，仅供传统文化参考。")
    return "\n".join(lines)


def _cn_no(n: int) -> str:
    return ("", "一", "二", "三", "四", "五")[n] if 0 < n <= 5 else str(n)


def _cn_chuan(n: int) -> str:
    return ("", "初", "中", "末")[n] if 0 < n <= 3 else str(n)


def liuren(arg: str = "") -> str:
    """指令入口: 大六壬 [时间]。"""
    return format_liuren(cast_liuren(arg))
