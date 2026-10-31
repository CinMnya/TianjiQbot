"""黄历工具：今日宜忌、吉时与每日黄历摘要。"""

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


def almanac_today(arg: str = "") -> str:
    """今日黄历 / 指定日期黄历。参数: 2026-10-20。"""
    now = datetime.now()
    arg = (arg or "").strip()
    if arg:
        m = re.search(r"(\d{4})\s*[-/年.]\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})", arg)
        if not m:
            raise ValueError("用法: 黄历 / 黄历 2026-10-20")
        s = Solar.fromYmd(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    else:
        s = Solar.fromDate(now)

    l = s.getLunar()
    yi = "、".join(l.getDayYi()[:12]) or "无"
    ji = "、".join(l.getDayJi()[:12]) or "无"

    try:
        luck = f"{l.getDayTianShenLuck()}·{l.getDayTianShenType()}"
    except Exception:
        luck = ""
    tianshen = l.getDayTianShen()

    lines = [
        f"【黄历】{s.toYmd()} 星期{s.getWeekInChinese()}",
        f"农历：{l.toString()}",
        f"干支：{l.getYearInGanZhi()}年 {l.getMonthInGanZhi()}月 {l.getDayInGanZhi()}日",
        f"值神：{tianshen}" + (f"（{luck}）" if luck else "")
        + f"　建除：{l.getZhiXing()}日　星宿：{l.getXiu()}宿",
        f"冲煞：冲{l.getDayChongDesc()}　煞{l.getDaySha()}",
        f"宜：{yi}",
        f"忌：{ji}",
        f"彭祖百忌：{l.getPengZuGan()}；{l.getPengZuZhi()}",
    ]
    try:
        jq = l.getNextJieQi()
        lines.append(f"下一节气：{jq.getName()}（{jq.getSolar().toYmd()}）")
    except Exception:
        pass
    try:
        festivals = l.getFestivals() + l.getOtherFestivals()
        if festivals:
            lines.append("节日：" + "、".join(festivals))
    except Exception:
        pass
    lines.append("※ 仅供传统文化参考，不构成择日/医疗/投资建议。")
    return "\n".join(lines)

# ---------------------------------------------------------------- 今日宜忌/吉时


def _zb_lunar(y=None, m=None, d=None):
    from datetime import date as _zb_date
    from lunar_python import Solar as _zb_solar
    if y is None:
        t = _zb_date.today()
        y, m, d = t.year, t.month, t.day
    return _zb_solar.fromYmd(y, m, d).getLunar()


def jinri(arg: str = "") -> str:
    """今日宜忌。arg 可为空（今天）或 2026-11-02。"""
    y = m = d = None
    t = (arg or "").strip().replace("年", "-").replace("月", "-").replace("日", "")
    parts = [p for p in t.split("-") if p.strip().isdigit()]
    if len(parts) == 3:
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
    elif parts or t:
        raise ValueError("日期写法：2026-11-02（缺省=今天）")
    lun = _zb_lunar(y, m, d)
    from datetime import date as _zb_date
    day = _zb_date(lun.getSolar().getYear(), lun.getSolar().getMonth(), lun.getSolar().getDay())
    yi = list(lun.getDayYi())
    ji = list(lun.getDayJi())
    lines = [
        f"【今日宜忌 · {day.year}-{day.month:02d}-{day.day:02d} {lun.getDayInGanZhi()}日 {lun.getYearInGanZhiByLiChun()}年】",
        f"天神：{lun.getDayTianShen()}（{lun.getDayTianShenType()}）",
    ]
    lines.append("宜：" + "、".join(yi))
    lines.append("忌：" + "、".join(ji))
    lines.append(f"冲煞：{lun.getDayChongDesc()} · 煞方宜避")
    js = list(lun.getDayJiShen())
    xs = list(lun.getDayXiongSha())
    lines.append("吉神：" + "、".join(js[:6]) + (f" 等{len(js)}位" if len(js) > 6 else ""))
    lines.append("凶神：" + "、".join(xs[:6]) + (f" 等{len(xs)}位" if len(xs) > 6 else ""))
    good = [tm for tm in lun.getTimes()
            if tm.getTianShenType() == "黄道" and tm.getMinHm() < "23:00"]
    if good:
        seg = "；".join(f"{t.getMinHm()}-{t.getMaxHm()}({t.getGanZhi()}时·{t.getTianShen()})"
                       for t in good[:4])
        lines.append(f"黄道吉时：{seg}")
    lines.append("（老黄历仅供习俗参考）")
    return "\n".join(lines)


def jishi(arg: str = "") -> str:
    """今日吉时。arg 可为空（今天）或 2026-11-02。"""
    y = m = d = None
    t = (arg or "").strip().replace("年", "-").replace("月", "-").replace("日", "")
    parts = [p for p in t.split("-") if p.strip().isdigit()]
    if len(parts) == 3:
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
    elif parts or t:
        raise ValueError("日期写法：2026-11-02（缺省=今天）")
    lun = _zb_lunar(y, m, d)
    day = f"{lun.getSolar().getYear()}-{lun.getSolar().getMonth():02d}-{lun.getSolar().getDay():02d}"
    lines = [f"【今日吉时 · {day} {lun.getDayInGanZhi()}日】",
             "（◆黄道吉时 ▲黑道凶时 · 吉时宜签约/开张/出行等）"]
    n_good = 0
    for tm in lun.getTimes():
        if tm.getMinHm() >= "23:00":
            continue  # 跳过晚子时（与早子时重复）
        good = tm.getTianShenType() == "黄道"
        n_good += good
        mark = "◆" if good else "▲"
        lines.append(f"{mark} {tm.getGanZhi()}时 {tm.getMinHm()}-{tm.getMaxHm()}"
                     f" {tm.getTianShen()} 冲{tm.getChongDesc()}")
    lines.append(f"今日黄道吉时 {n_good} 个。")
    return "\n".join(lines)
