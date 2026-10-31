"""金口诀起课（四位课 · 五动）。"""

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

from .liuren import (_lr_parse_when, _yuejiang, _xunkong, LIUREN_GUIREN,
                     LIUREN_ZHI, LIUREN_GAN, LIUREN_WX, LIUREN_GAN_WX,
                     LIUREN_SHEN, LIUREN_SHENG, LIUREN_KE)


JJ_NAYIN = (
    "海中金", "炉中火", "大林木", "路旁土", "剑锋金", "山头火",
    "涧下水", "城头土", "白蜡金", "杨柳木", "泉中水", "屋上土",
    "霹雳火", "松柏木", "长流水", "沙中金", "山下火", "平地木",
    "壁上土", "金箔金", "覆灯火", "天河水", "大驿土", "钗钏金",
    "桑柘木", "大溪水", "沙中土", "天上火", "石榴木", "大海水",
)

# 十二天将五行(金口诀以天将五行论贵神)
JJ_SHEN_WX = {
    "贵人": "土", "螣蛇": "火", "朱雀": "火", "六合": "木",
    "勾陈": "土", "青龙": "木", "天空": "土", "白虎": "金",
    "太常": "土", "玄武": "水", "太阴": "金", "天后": "水",
}

# 吉神 / 凶神(金口诀常用取象)
JJ_SHEN_JI = frozenset(("贵人", "青龙", "六合", "太常"))
JJ_SHEN_XIONG = frozenset(("白虎", "玄武", "勾陈", "天空", "螣蛇"))

# 日干五子元遁起点(甲己还加甲…)
JJ_WUZI = {"甲": 0, "己": 0, "乙": 2, "庚": 2, "丙": 4,
           "辛": 4, "丁": 6, "壬": 6, "戊": 8, "癸": 8}

# 方位 -> 地分代表支
JJ_FANGWEI = {
    "北": 0, "东北": 2, "东": 3, "东南": 5, "南": 6,
    "西南": 8, "西": 9, "西北": 11,
}
JJ_FANGWEI_NAME = {
    0: "正北", 1: "东北", 2: "东北", 3: "正东", 4: "东南", 5: "东南",
    6: "正南", 7: "西南", 8: "西南", 9: "正西", 10: "西北", 11: "西北",
}

# 旺衰
JJ_WANG = ("旺", "相", "休", "囚", "死")


def _jj_nayin(gan: str, zhi: str) -> str:
    """干支纳音；不合六十甲子则返回空串。"""
    g = LIUREN_GAN.index(gan)
    z = LIUREN_ZHI.index(zhi)
    n = next((i for i in range(60) if i % 10 == g and i % 12 == z), None)
    if n is None:
        return ""
    return JJ_NAYIN[n // 2]


def _jj_wangshuai(wx: str, ling: str) -> str:
    """按月令五行判旺相休囚死。"""
    if wx == ling:
        return "旺"
    if LIUREN_SHENG.get(ling) == wx:
        return "相"
    if LIUREN_SHENG.get(wx) == ling:
        return "休"
    if LIUREN_KE.get(wx) == ling:
        return "囚"
    return "死"


def _jj_rel(a: str, b: str) -> str:
    """a 与 b 的五行关系(以 a 为主体)。"""
    if a == b:
        return "比和"
    if LIUREN_KE.get(a) == b:
        return "克"
    if LIUREN_KE.get(b) == a:
        return "被克"
    if LIUREN_SHENG.get(a) == b:
        return "生"
    return "被生"


def _jj_fen(arg: str):
    """从参数里取地分。返回 (地支索引 或 None, 说明)。"""
    s = (arg or "").strip()
    if not s:
        return None, ""
    # 先找方位词(长的优先)
    for word in ("东北", "东南", "西南", "西北", "北", "东", "南", "西"):
        if word in s:
            return JJ_FANGWEI[word], f"方位「{word}」"
    # 再找地支名，取最后一个
    hit = -1
    for i, ch in enumerate(s):
        if ch in LIUREN_ZHI:
            hit = i
    if hit >= 0:
        return LIUREN_ZHI.index(s[hit]), f"指定「{s[hit]}」"
    # 纯数字 1~12 视为地分序号
    m = re.fullmatch(r"\s*(\d{1,2})\s*", s)
    if m and 1 <= int(m.group(1)) <= 12:
        return (int(m.group(1)) - 1) % 12, f"报数 {m.group(1)}"
    return None, ""


def cast_jinjue(arg: str = "") -> dict:
    """起金口诀课。arg 可含时间与地分(地支/方位/1~12 数字)。"""
    dt = _lr_parse_when(arg)
    fen, fen_src = _jj_fen(arg)

    solar = Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, 0)
    lunar = solar.getLunar()
    year_gz = lunar.getYearInGanZhi()
    month_gz = lunar.getMonthInGanZhi()
    day_gz = lunar.getDayInGanZhi()
    time_gz = lunar.getTimeInGanZhi()
    day_gan = day_gz[0]

    shi_zhi = (dt.hour + 1) // 2 % 12
    if fen is None:
        fen = shi_zhi
        fen_src = "未报方位，取时支为地分"

    jq_name, (yj, yj_name), jq_start = _yuejiang(lunar, dt)

    # ---- 将神: 月将加时，地分上临之支 ----
    jiang_shen = (yj + fen - shi_zhi) % 12

    # ---- 贵神: 日干昼夜贵人，顺逆数至地分 ----
    is_day = 3 <= shi_zhi <= 8
    gui_zhi = LIUREN_GUIREN[day_gan][0 if is_day else 1]
    gui_pos = (gui_zhi - yj + shi_zhi) % 12      # 贵人所临地盘位
    forward = gui_pos in (11, 0, 1, 2, 3, 4)
    steps = (fen - gui_pos) % 12 if forward else (gui_pos - fen) % 12
    gui_shen = LIUREN_SHEN[steps]

    # ---- 人元: 日干五子元遁至地分 ----
    ren_yuan = LIUREN_GAN[(JJ_WUZI[day_gan] + fen) % 10]

    # ---- 四位五行 ----
    wx_ren = LIUREN_GAN_WX[ren_yuan]
    wx_gui = JJ_SHEN_WX[gui_shen]
    wx_jiang = LIUREN_WX[jiang_shen]
    wx_fen = LIUREN_WX[fen]

    ling_zhi = LIUREN_ZHI.index(month_gz[1])
    ling = LIUREN_WX[ling_zhi]

    siwei = [
        {"pos": "人元", "val": ren_yuan, "wx": wx_ren,
         "ws": _jj_wangshuai(wx_ren, ling),
         "nai": _jj_nayin(ren_yuan, LIUREN_ZHI[fen]),
         "note": "天时 · 客"},
        {"pos": "贵神", "val": gui_shen, "wx": wx_gui,
         "ws": _jj_wangshuai(wx_gui, ling), "nai": "",
         "note": "人事 · 贵"},
        {"pos": "将神", "val": LIUREN_ZHI[jiang_shen], "wx": wx_jiang,
         "ws": _jj_wangshuai(wx_jiang, ling), "nai": "",
         "note": "地理 · 将"},
        {"pos": "地分", "val": LIUREN_ZHI[fen], "wx": wx_fen,
         "ws": _jj_wangshuai(wx_fen, ling), "nai": "",
         "note": "根基 · 主"},
    ]

    # ---- 生克关系 ----
    rel_gui_jiang = _jj_rel(wx_gui, wx_jiang)
    rel_ren_gui = _jj_rel(wx_ren, wx_gui)
    rel_ren_jiang = _jj_rel(wx_ren, wx_jiang)
    rel_ren_fen = _jj_rel(wx_ren, wx_fen)

    dong = []
    if rel_ren_gui == "克":
        dong.append(("妻动", "人元克贵神", "主外人、妻妾、外人来求；向外求财较顺"))
    if rel_ren_gui == "被克":
        dong.append(("官动", "贵神克人元", "主官职、文书、公事；也主受制于上"))
    if rel_ren_jiang == "克":
        dong.append(("财动", "人元克将神", "主财帛、买卖、器物；求财有门"))
    if rel_ren_jiang == "被克":
        dong.append(("鬼动", "将神克人元", "主疾病、盗贼、忧疑；宜防暗损"))
    if not dong:
        dong.append(("子孙动", "四位无克", "主平顺、生养、喜庆，事缓而稳"))

    # ---- 课体 ----
    keti = []
    if jiang_shen == gui_zhi:
        keti.append("神将同支：贵神与将神共乘一支，内外一事，容易反复、久拖不决")
    if (jiang_shen - gui_zhi) % 12 == 6:
        keti.append("神将相冲：反吟之象，主来回折腾、事情翻覆")
    if jiang_shen == fen:
        keti.append("将神临地分：伏吟之象，主原地不动、宜守不宜进")
    if (jiang_shen - fen) % 12 == 6:
        keti.append("将神冲地分：根基受动，主迁移、变址、旧事重提")
    if gui_shen in JJ_SHEN_JI:
        keti.append(f"贵神得吉将（{gui_shen}）：有贵人、文书、和气之助")
    elif gui_shen in JJ_SHEN_XIONG:
        keti.append(f"贵神带凶将（{gui_shen}）：防口舌、拖延与暗耗")
    else:
        keti.append(f"贵神为平神（{gui_shen}）：不助不损，看神将生克定夺")

    # ---- 要点 ----
    notes = []
    if rel_gui_jiang == "克":
        notes.append("贵神克将神：外力压内事，宜借势、顺水推舟，不宜硬顶。")
    elif rel_gui_jiang == "被克":
        notes.append("将神克贵神：内事抗外力，自己能主导但耗神，忌与上位者顶撞。")
    elif rel_gui_jiang == "生":
        notes.append("贵神生将神：有外力来助，事情有人替你推一把。")
    elif rel_gui_jiang == "被生":
        notes.append("将神生贵神：你在为别人出力，注意别把自己搭进去。")
    else:
        notes.append("神将比和：同气相求，事易成但变化少，守成最佳。")

    if rel_ren_fen == "克":
        notes.append("人元克地分：我方主动、能掌控局面，但也易急躁伤人。")
    elif rel_ren_fen == "被克":
        notes.append("地分克人元：环境反制，根基先别扭，先解后进。")
    elif rel_ren_fen == "生":
        notes.append("人元生地分：投入多于回报，先付出后见利。")
    elif rel_ren_fen == "被生":
        notes.append("地分生人元：得地之助，家宅、根基处有暗中扶持。")

    strong = [s for s in siwei if s["ws"] in ("旺", "相")]
    weak = [s for s in siwei if s["ws"] in ("囚", "死")]
    if strong:
        notes.append("旺相者：" + "、".join(f"{s['pos']}{s['val']}" for s in strong)
                     + "，这几处是本课得力之处。")
    if weak:
        notes.append("囚死者：" + "、".join(f"{s['pos']}{s['val']}" for s in weak)
                     + "，这几处暂时使不上劲，别把希望押在上面。")

    kong = _xunkong(day_gz)
    if jiang_shen in kong or fen in kong:
        notes.append("将神或地分落旬空：对方说法易变、约好的事容易落空，宜留字据。")

    return {
        "dt": dt,
        "solar": f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}",
        "clock": f"{dt.hour:02d}:{dt.minute:02d}",
        "year_gz": year_gz,
        "month_gz": month_gz,
        "day_gz": day_gz,
        "time_gz": time_gz,
        "day_gan": day_gan,
        "shi_name": LIUREN_ZHI[shi_zhi],
        "jieqi": jq_name,
        "yuejiang": yj,
        "yuejiang_name": yj_name,
        "fen": fen,
        "fen_name": LIUREN_ZHI[fen],
        "fen_fangwei": JJ_FANGWEI_NAME[fen],
        "fen_src": fen_src,
        "ren_yuan": ren_yuan,
        "gui_shen": gui_shen,
        "jiang_shen": LIUREN_ZHI[jiang_shen],
        "jiang_shen_zhi": jiang_shen,
        "gui_pos": gui_pos,
        "siwei": siwei,
        "ling": ling,
        "ling_gz": month_gz,
        "dong": dong,
        "keti": keti,
        "notes": notes,
        "zhou": "昼占" if is_day else "夜占",
        "guiren": LIUREN_ZHI[gui_zhi],
        "guiren_pos": LIUREN_ZHI[gui_pos],
        "forward": forward,
        "xunkong": kong,
    }


def format_jinjue(c: dict) -> str:
    lines = [
        f"**金口诀** · 人元 {c['ren_yuan']} / 贵神 {c['gui_shen']} / "
        f"将神 {c['jiang_shen']} / 地分 {c['fen_name']}",
        f"{c['solar']} {c['clock']}　{c['year_gz']}年 {c['month_gz']}月 "
        f"{c['day_gz']}日 {c['time_gz']}时",
        f"月将 {LIUREN_ZHI[c['yuejiang']]}（{c['yuejiang_name']}）"
        f"· {c['zhou']} · 贵人乘{c['guiren']}临{c['guiren_pos']}"
        f"（{'顺行' if c['forward'] else '逆行'}）"
        f"· 地分 {c['fen_name']}（{c['fen_fangwei']}）",
        f"月令 {c['ling_gz']}（{c['ling']}当令）· 旬空 "
        + "".join(LIUREN_ZHI[z] for z in c["xunkong"]),
        "",
        "**四位**（人元 / 贵神 / 将神 / 地分）",
    ]
    for s in c["siwei"]:
        nai = f" · 纳音{s['nai']}" if s["nai"] else ""
        lines.append(f"· {s['pos']}：{s['val']}（{s['wx']}）· {s['ws']}"
                     f" · {s['note']}{nai}")
    lines.append("")
    lines.append("**关系**")
    pair = [
        ("贵神", "将神", c["siwei"][1], c["siwei"][2]),
        ("人元", "贵神", c["siwei"][0], c["siwei"][1]),
        ("人元", "将神", c["siwei"][0], c["siwei"][2]),
        ("人元", "地分", c["siwei"][0], c["siwei"][3]),
    ]
    for na, nb, a, b in pair:
        lines.append(f"· {na}{a['wx']} 与 {nb}{b['wx']}：{_jj_rel(a['wx'], b['wx'])}")
    lines.append("")
    lines.append("**五动**")
    for name, how, mean in c["dong"]:
        lines.append(f"· {name}：{how} —— {mean}")
    lines.append("")
    lines.append("**课体**")
    for k in c["keti"]:
        lines.append(f"· {k}")
    lines.append("")
    lines.append("**要点**")
    for n in c["notes"]:
        lines.append(f"· {n}")
    return "\n".join(lines)


def jinjue(arg: str = "") -> str:
    return format_jinjue(cast_jinjue(arg))
