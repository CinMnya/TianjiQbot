"""择日（黄道吉日查询、剖腹产择日）。"""

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


from lunar_python import Solar as _JR_Solar

# 事项 → (显示名, 命中的宜词集合)
_JR_EVENTS = {
    "嫁娶": ("结婚嫁娶", ("嫁娶", "结婚", "纳采", "订婚", "领证")),
    "开业": ("开业开张", ("开市", "开业", "开张", "交易", "立券")),
    "搬家": ("搬家入宅", ("搬家", "移徙", "入宅", "安床")),
    "提车": ("提车购车", ("交易", "立券", "纳财")),
    "出行": ("出行远游", ("出行",)),
    "装修": ("装修动土", ("修造", "动土", "装修", "上梁", "拆卸")),
    "祭祀": ("祭祀祈福", ("祭祀", "祈福")),
    "求嗣": ("求子嗣", ("求嗣", "祈福")),
}

_JR_LUCK = ("黄道", "黑道")
_JR_GOOD_DAY = ("青龙", "明堂", "金匮", "天德", "宝光", "玉堂", "司命")


def _jr_parse_month(arg: str):
    """'2026-11' / '2026年11月' / '11月'（默认当年）→ (y, m)。"""
    from datetime import date as _jr_date
    t = (arg or "").strip().replace("年", "-").replace("月", "").replace(".", "-")
    parts = [p for p in t.split("-") if p.strip().isdigit()]
    today = _jr_date.today()
    if len(parts) >= 2 and 1900 <= int(parts[0]) <= 2200:
        y, m = int(parts[0]), int(parts[1])
    elif len(parts) == 1:
        v = int(parts[0])
        if 1 <= v <= 12:
            y, m = today.year, v
        elif 202001 <= v <= 220012:  # 202611 连写
            y, m = v // 100, v % 100
        else:
            raise ValueError("月份写法：2026-11 / 11月 / 2026年11月")
    else:
        raise ValueError("月份写法：2026-11 / 11月 / 2026年11月")
    if not 1 <= m <= 12:
        raise ValueError("月份应在 1~12 之间")
    return y, m


def _jr_days(y: int, m: int):
    """当月每日 (Solar日期, 天神, 道, 宜列表, 忌列表, 冲)。"""
    from datetime import date as _jr_date, timedelta as _jr_td
    d0 = _jr_date(y, m, 1)
    nxt = _jr_date(y + 1, 1, 1) if m == 12 else _jr_date(y, m + 1, 1)
    out = []
    d = d0
    while d < nxt:
        lunar = _JR_Solar.fromYmd(d.year, d.month, d.day).getLunar()
        out.append((d, lunar.getDayTianShen(), lunar.getDayTianShenType(),
                    list(lunar.getDayYi()), list(lunar.getDayJi()),
                    lunar.getDayChongDesc()))
        d += _jr_td(days=1)
    return out


def _jr_hit(yi, kws):
    return any(k in w for w in yi for k in kws)


def _jr_main(arg: str = "") -> str:
    """黄道吉日/择日。arg: [事项] 年-月，如 '2026-11'、'搬家 2026-11'。"""
    t = (arg or "").strip()
    # 事项同义词归一化（触发词可能带进来）
    for _syn, _std in (("结婚", "嫁娶"), ("婚嫁", "嫁娶"), ("领证", "嫁娶"),
                       ("开张", "开业"), ("乔迁", "搬家"), ("入宅", "搬家"),
                       ("购车", "提车"), ("旅游", "出行"), ("动土", "装修"),
                       ("修造", "装修"), ("祈福", "祭祀"), ("求子", "求嗣")):
        if t.startswith(_syn):
            t = _std + t[len(_syn):]
            break
    ev_name, kws = None, None
    for ev, (disp, k) in _JR_EVENTS.items():
        if t.startswith(ev):
            ev_name, kws = disp, k
            t = t[len(ev):].strip()
            break
    y, m = _jr_parse_month(t)
    days = _jr_days(y, m)

    if kws is None:
        lines = [f"【黄道吉日 · {y}年{m}月】", "（◆黄道 ▲黑道 · 择日加事项：择日 搬家 2026-11）"]
        n_good = 0
        for d, god, typ, yi, ji, chong in days:
            mark = "◆" if typ == "黄道" else "▲"
            if typ == "黄道":
                n_good += 1
            yis = "、".join(yi[:3]) or "—"
            lines.append(f"{mark} {d.month:02d}-{d.day:02d} {god} 宜：{yis}")
        lines.append(f"本月黄道日 {n_good} 天。")
        return "\n".join(lines)

    # 事项择日：黄道且宜命中优先
    good, alt = [], []
    for d, god, typ, yi, ji, chong in days:
        if not _jr_hit(yi, kws):
            continue
        if typ == "黄道":
            good.append((d, god, yi, chong))
        else:
            alt.append((d, god, yi, chong))
    lines = [f"【择日 · {y}年{m}月 · {ev_name}】"]
    if not good and not alt:
        lines.append(f"本月无宜「{'、'.join(kws[:3])}」之日，建议换月或另择。")
        return "\n".join(lines)
    for d, god, yi, chong in good:
        lines.append(f"◆ {d.month:02d}-{d.day:02d} {god}日 宜：{'、'.join(yi[:4])} {chong}")
    if alt:
        lines.append("（以下黑道日亦宜，仅作备选）")
        for d, god, yi, chong in alt[:3]:
            lines.append(f"▲ {d.month:02d}-{d.day:02d} {god}日 宜：{'、'.join(yi[:4])} {chong}")
    if good:
        lines.append(f"首选：{good[0][0].month:02d}-{good[0][0].day:02d}（{good[0][1]}黄道）。")
    lines.append("提示：避冲生肖之日，重要事项可再结合双方八字。")
    return "\n".join(lines)


def _jr_good_hours(day) -> list:
    """day: Solar日期 → 当日黄道吉时 [(时段, 干支, 天神)]，白天优先取3。"""
    lunar = _JR_Solar.fromYmd(day.year, day.month, day.day).getLunar()
    out = [t for t in lunar.getTimes() if t.getTianShenType() == "黄道"]

    def _key(t):
        return (0 if t.getMinHm() >= "05:00" else 1, t.getMinHm())

    out.sort(key=_key)
    return [f"{t.getMinHm()}-{t.getMaxHm()}（{t.getGanZhi()}时·{t.getTianShen()}）"
            for t in out[:3]]


def pofuchan(arg: str = "") -> str:
    """剖腹产择日。arg: 2026-11 → 该月黄道吉日 + 各日吉时。"""
    y, m = _jr_parse_month(arg)
    days = _jr_days(y, m)
    lines = [f"【剖腹产择日 · {y}年{m}月】",
             "（黄道吉日为主，附日中黄道吉时；生产以母子平安为先，务必遵医嘱）"]
    picked = 0
    for d, god, typ, yi, ji, chong in days:
        if typ != "黄道" or picked >= 6:
            continue
        hours = _jr_good_hours(d)
        if not hours:
            continue
        gz = _JR_Solar.fromYmd(d.year, d.month, d.day).getLunar().getDayInGanZhi()
        lines.append(f"◆ {d.month:02d}-{d.day:02d} {gz}日 {god} {chong}")
        lines.append(f"　吉时：{'；'.join(hours)}")
        picked += 1
    if picked == 0:
        lines.append("本月黄道吉时配合较好之日较少，建议放宽至黑道吉时或另择月份。")
    return "\n".join(lines)


jiri = _jr_main
