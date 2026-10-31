"""玄空飞星风水（三元九运 · 二十四山）。"""

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


XK_GONG = {1: "坎", 2: "坤", 3: "震", 4: "巽", 5: "中",
           6: "乾", 7: "兑", 8: "艮", 9: "离"}
XK_GONG_FANG = {1: "正北", 2: "西南", 3: "正东", 4: "东南", 5: "中宫",
                6: "西北", 7: "正西", 8: "东北", 9: "正南"}

# 飞泊次序(洛书宫位)
XK_FEI_SEQ = (5, 6, 7, 8, 9, 1, 2, 3, 4)

# 二十四山(从壬起，顺时针，每山 15°)
XK_SHAN_ORDER = "壬子癸丑艮寅甲卯乙辰巽巳丙午丁未坤申庚酉辛戌乾亥"

# 每三山一卦
XK_SHAN_GONG = (1, 8, 3, 4, 9, 2, 7, 6)

# 三元龙阴阳: 每组三山依次为 地元 / 天元 / 人元
XK_YUAN_NAME = ("地元", "天元", "人元")
XK_GROUP_YINYANG = {
    1: ("阳", "阴", "阴"), 3: ("阳", "阴", "阴"),
    9: ("阳", "阴", "阴"), 7: ("阳", "阴", "阴"),
    8: ("阴", "阳", "阳"), 4: ("阴", "阳", "阳"),
    2: ("阴", "阳", "阳"), 6: ("阴", "阳", "阳"),
}

# 方位 -> 二十四山
XK_FANG_SHAN = {"北": "子", "东北": "艮", "东": "卯", "东南": "巽",
                "南": "午", "西南": "坤", "西": "酉", "西北": "乾"}

# 星气名称
XK_QI = {0: "旺", 1: "生", 2: "进", 8: "退", 7: "衰", 6: "死"}
XK_QI_NOTE = {
    "旺": "当运最旺", "生": "下运生气", "进": "再下运进气",
    "退": "上运退气", "衰": "更早衰气", "死": "死气", "煞": "煞气",
}

# 金锁玉关: 一二三四要砂, 六七八九要水
XK_SHA_GONG = (1, 2, 3, 4)
XK_SHUI_GONG = (6, 7, 8, 9)


def _xk_shan_info(shanz: str) -> dict:
    """二十四山的卦、元龙、阴阳。"""
    i = XK_SHAN_ORDER.index(shanz)
    gong = XK_SHAN_GONG[i // 3]
    k = i % 3
    return {
        "shan": shanz,
        "gong": gong,
        "gong_name": XK_GONG[gong],
        "yuan": XK_YUAN_NAME[k],
        "yuan_idx": k,
        "yinyang": XK_GROUP_YINYANG[gong][k],
        "du": (345 + i * 15) % 360,
        "fang": XK_GONG_FANG[gong],
    }


def _xk_dui_shan(shanz: str) -> str:
    """对宫同元龙之山(子<->午、壬<->丙 …)。"""
    i = XK_SHAN_ORDER.index(shanz)
    return XK_SHAN_ORDER[(i + 12) % 24]


def _xk_yun(year: int) -> dict:
    """三元九运。1864 起一运，每运 20 年。"""
    n = (year - 1864) // 20
    star = n % 9 + 1
    start = 1864 + n * 20
    if n < 3:
        yuan = "上元"
    elif n < 6:
        yuan = "中元"
    else:
        yuan = "下元"
    return {"star": star, "start": start, "end": start + 19,
            "yuan": yuan, "name": f"{yuan}{'一二三四五六七八九'[star - 1]}运"}


def _xk_fei(center: int, forward: bool = True) -> dict:
    """某星入中飞布九宫。"""
    out = {}
    for k, g in enumerate(XK_FEI_SEQ):
        out[g] = (center - 1 + k) % 9 + 1 if forward else (center - 1 - k) % 9 + 1
    return out


def _xk_forward(center: int, yuan_idx: int, self_yy: str) -> bool:
    """入中星的顺逆。

    规则：取入中星所辖三山中、与坐向同元龙位置的那一山，阳顺阴逆；
    五黄入中时中宫无卦，改用坐向自身的阴阳。
    """
    if center == 5:
        return self_yy == "阳"
    start = XK_SHAN_GONG.index(center) * 3 + yuan_idx
    return XK_GROUP_YINYANG[center][yuan_idx] == "阳"


def _xk_qi(star: int, yun: int) -> str:
    """星在当运下的气: 旺相休囚死一类。"""
    d = (star - yun) % 9
    return XK_QI.get(d, "煞")


def _xk_year_star(year: int) -> int:
    """流年入中之星。"""
    s = sum(int(c) for c in str(year))
    while s > 9:
        s = sum(int(c) for c in str(s))
    v = 11 - s
    while v > 9:
        v -= 9
    while v < 1:
        v += 9
    return v


_SHAN_CLS = "[" + XK_SHAN_ORDER + "]"
_FANG_CLS = "(东北|东南|西南|西北|东|南|西|北)"


def _xk_parse(arg: str):
    """解析参数: 坐向 + 年份。返回 (zuo, xiang, year, 备注)。"""
    s = (arg or "").strip()
    year = datetime.now().year
    m = re.search(r"(19\d{2}|20\d{2})", s)
    if m:
        year = int(m.group(1))

    zuo = xiang = ""
    m = re.search(r"坐" + _SHAN_CLS + r"向" + _SHAN_CLS, s)
    if m:
        zuo, xiang = s[m.start() + 1], s[m.start() + 3]
    if not zuo:
        m = re.search(_SHAN_CLS + r"山" + _SHAN_CLS + r"向", s)
        if m:
            zuo, xiang = s[m.start()], s[m.start() + 2]
    if not zuo:
        m = re.search(r"坐" + _FANG_CLS + r"朝" + _FANG_CLS, s)
        if m:
            zuo = XK_FANG_SHAN[m.group(1)]
            xiang = XK_FANG_SHAN[m.group(2)]
    if not zuo:
        m = re.search(r"坐" + _FANG_CLS, s)
        if m:
            zuo = XK_FANG_SHAN[m.group(1)]
    if not zuo:
        m = re.search(r"坐" + _SHAN_CLS, s)
        if m:
            zuo = s[m.start() + 1]
    if not xiang:
        m = re.search(r"向" + _SHAN_CLS, s)
        if m:
            xiang = s[m.start() + 1]
    if not xiang:
        m = re.search(r"朝" + _FANG_CLS, s)
        if m:
            xiang = XK_FANG_SHAN[m.group(1)]

    note = ""
    if not zuo and not xiang:
        zuo = "子"
        xiang = "午"
        note = "未给坐向，按子山午向（坐北朝南）演示"
    elif zuo and not xiang:
        xiang = _xk_dui_shan(zuo)
        note = f"只给了坐山，取对宫{xiang}为向"
    elif xiang and not zuo:
        zuo = _xk_dui_shan(xiang)
        note = f"只给了朝向，取对宫{zuo}为坐"
    return zuo, xiang, year, note


def cast_xuankong(arg: str = "") -> dict:
    """排玄空飞星盘。"""
    zuo, xiang, year, note = _xk_parse(arg)
    zi = _xk_shan_info(zuo)
    xi = _xk_shan_info(xiang)
    yun = _xk_yun(year)
    ys = yun["star"]

    # 运盘: 当运星入中顺飞
    yun_pan = _xk_fei(ys, True)
    # 山星: 坐山所在宫位的运星入中
    shan_center = yun_pan[zi["gong"]]
    shan_fwd = _xk_forward(shan_center, zi["yuan_idx"], zi["yinyang"])
    shan_pan = _xk_fei(shan_center, shan_fwd)
    # 向星: 朝向所在宫位的运星入中
    xiang_center = yun_pan[xi["gong"]]
    xiang_fwd = _xk_forward(xiang_center, xi["yuan_idx"], xi["yinyang"])
    xiang_pan = _xk_fei(xiang_center, xiang_fwd)

    def _rule(center, info):
        if center == 5:
            return f"{center}入中（中宫无卦）→ 取{info['shan']}本身{info['yuan']}·{info['yinyang']}→{'顺' if info['yinyang'] == '阳' else '逆'}飞"
        gong = XK_GONG[center]
        ref = XK_SHAN_ORDER[XK_SHAN_GONG.index(center) * 3 + info["yuan_idx"]]
        yy = XK_GROUP_YINYANG[center][info["yuan_idx"]]
        return (f"{center}入中（{gong}宫）→ 同元龙取{ref}（{yy}）"
                f"→{'顺' if yy == '阳' else '逆'}飞")

    gz, gx = zi["gong"], xi["gong"]
    at_zuo_shan = shan_pan[gz]
    at_zuo_xiang = xiang_pan[gz]
    at_xiang_shan = shan_pan[gx]
    at_xiang_xiang = xiang_pan[gx]

    # 格局判定
    if at_zuo_shan == ys and at_xiang_xiang == ys:
        geju = "旺山旺向（到山到向）"
        geju_note = ("当运星到坐山又到向首，山管人丁、水管财，"
                     "丁财两旺的格局，宜坐实朝空、后方有靠、前方开阔。")
    elif at_xiang_shan == ys and at_zuo_xiang == ys:
        geju = "上山下水"
        geju_note = ("当运星颠倒，山星落向首、向星落坐山，"
                     "丁财两失之象。宜坐空朝实（背水、前方有高实），"
                     "用布局补救，不宜再在向首开大窗泄气。")
    elif at_xiang_shan == ys and at_xiang_xiang == ys:
        geju = "双星会向"
        geju_note = ("山向两星同聚向首，财气旺而人丁稍弱，"
                     "宜前方开阔纳气，后方不宜过高逼压。")
    elif at_zuo_shan == ys and at_zuo_xiang == ys:
        geju = "双星会坐"
        geju_note = ("山向两星同聚坐山，人丁旺而财气稍缓，"
                     "宜后方厚实有靠，向首见水或通路引财。")
    else:
        geju = "一般格局"
        geju_note = ("当运星未成对落到山向，吉凶要看各宫双星组合，"
                     "以当运、生气宫为用，煞死宫宜静宜化。")

    # 九宫组合
    gongs = []
    for g in range(1, 10):
        shan = shan_pan[g]
        xw = xiang_pan[g]
        gongs.append({
            "gong": g,
            "name": XK_GONG[g],
            "fang": "中宫" if g == 5 else XK_GONG_FANG[g],
            "yun": yun_pan[g],
            "shan": shan,
            "xiang": xw,
            "shan_qi": _xk_qi(shan, ys),
            "xiang_qi": _xk_qi(xw, ys),
            "is_zuo": g == gz,
            "is_xiang": g == gx,
            "sha_shui": ("宜砂" if g in XK_SHA_GONG
                         else ("宜水" if g in XK_SHUI_GONG else "不论")),
        })

    # 流年
    lyear = datetime.now().year
    ly_star = _xk_year_star(lyear)
    liunian_pan = _xk_fei(ly_star, True)

    # 金锁玉关: 方位宜砂宜水
    jinsuo = []
    for g in list(XK_SHA_GONG) + list(XK_SHUI_GONG):
        jinsuo.append({
            "fang": "中宫" if g == 5 else XK_GONG_FANG[g],
            "gong": XK_GONG[g],
            "need": "砂" if g in XK_SHA_GONG else "水",
        })

    # 要点
    notes = []
    if geju.startswith("旺山旺向"):
        notes.append("旺山旺向：坐方要高实（山）、向首要低空（水），顺此格局，"
                     "人丁与财气都稳；反过来用（坐空朝实）会把旺气用废。")
    elif geju == "上山下水":
        notes.append("上山下水：这是需要「反用」的格局——坐方宜见水、"
                     "向首宜有高实遮挡，才能把颠倒的星气拉回来。")
    elif geju in ("双星会向", "双星会坐"):
        notes.append(f"{geju}：气聚一头，另一头要靠布局补。"
                     "会向重纳气口，会坐重靠山与床位。")
        if ys == 9:
            notes.append("九运本身没有传统意义上的旺山旺向，双九到坐或到向"
                         "就是这二十年的当运旺局，取「双星会向」重财、"
                         "「双星会坐」重丁，按需要选。")

    zq = _xk_qi(at_zuo_shan, ys)
    xq = _xk_qi(at_xiang_xiang, ys)
    notes.append(f"坐山{zi['gong_name']}宫山星{at_zuo_shan}（{zq}）、"
                 f"向首{xi['gong_name']}宫向星{at_xiang_xiang}（{xq}），"
                 f"这两处是这套宅子的主气，装修、开门、安床先看这里。")

    bad = [g for g in gongs if g["gong"] != 5
           and g["shan_qi"] in ("死", "煞") and g["xiang_qi"] in ("死", "煞")]
    if bad:
        notes.append("山向双死煞之宫：" + "、".join(
            f"{b['name']}（{b['fang']}）" for b in bad)
            + "。这些方位宜静、宜置物压住，不宜作卧室、书房或大门。")

    wang = [g for g in gongs if g["gong"] != 5
            and (g["shan_qi"] in ("旺", "生") or g["xiang_qi"] in ("旺", "生"))]
    if wang:
        notes.append("得气之宫：" + "、".join(
            f"{b['name']}（{b['fang']}）" for b in wang)
            + "，可用作主要活动区、办公位或床位。")

    notes.append("金锁玉关另有一套判断：坎坤震巽（北、西南、东、东南）宜砂宜高，"
                 "乾兑艮离（西北、西、东北、南）宜水宜低；"
                 "两套都合，才算真稳。")

    return {
        "zuo": zi,
        "xiang": xi,
        "year": year,
        "yun": yun,
        "yun_pan": yun_pan,
        "shan_pan": shan_pan,
        "xiang_pan": xiang_pan,
        "shan_center": shan_center,
        "xiang_center": xiang_center,
        "shan_rule": _rule(shan_center, zi),
        "xiang_rule": _rule(xiang_center, xi),
        "shan_fwd": shan_fwd,
        "xiang_fwd": xiang_fwd,
        "geju": geju,
        "geju_note": geju_note,
        "gongs": gongs,
        "liunian_year": lyear,
        "liunian_star": ly_star,
        "liunian_pan": liunian_pan,
        "jinsuo": jinsuo,
        "notes": notes,
        "parse_note": note,
    }


def _xk_grid_line(pan: dict, key: str = "") -> list:
    """把盘排成三行文字(巽离坤 / 震中兑 / 艮坎乾)。"""
    rows = []
    for r in ((4, 9, 2), (3, 5, 7), (8, 1, 6)):
        cells = []
        for g in r:
            v = pan[g] if not key else pan[g][key]
            cells.append(f"{XK_GONG[g]}{v}")
        rows.append("  ".join(cells))
    return rows


def format_xuankong(c: dict) -> str:
    zi, xi = c["zuo"], c["xiang"]
    yun = c["yun"]
    lines = [
        f"**玄空飞星** · {yun['name']} {zi['shan']}山{xi['shan']}向",
        f"{yun['start']}–{yun['end']}年 · 坐 {zi['shan']}（{zi['gong_name']}卦·"
        f"{zi['yuan']}龙·{zi['yinyang']}）　向 {xi['shan']}（{xi['gong_name']}卦·"
        f"{xi['yuan']}龙·{xi['yinyang']}）",
        f"坐山约 {zi['du']}° · 朝向约 {xi['du']}° · "
        f"{c['liunian_year']}年{c['liunian_star']}入中",
    ]
    if c["parse_note"]:
        lines.append(f"（{c['parse_note']}）")
    lines += ["", "**运盘**（当运星入中顺飞）"]
    lines += ["　" + r for r in _xk_grid_line(c["yun_pan"])]
    lines += ["", f"**山星盘**（{c['shan_rule']}）"]
    lines += ["　" + r for r in _xk_grid_line(c["shan_pan"])]
    lines += ["", f"**向星盘**（{c['xiang_rule']}）"]
    lines += ["　" + r for r in _xk_grid_line(c["xiang_pan"])]

    lines += ["", "**九宫双星**（宫 / 山星 / 向星 / 山气 / 向气）"]
    for g in c["gongs"]:
        tag = "　← 坐" if g["is_zuo"] else ("　← 向" if g["is_xiang"] else "")
        name = "中宫" if g["gong"] == 5 else f"{g['name']}宫（{g['fang']}）"
        lines.append(f"· {name}运{g['yun']}　"
                     f"山{g['shan']}（{g['shan_qi']}）　向{g['xiang']}（{g['xiang_qi']}）"
                     f"　{g['sha_shui']}{tag}")

    lines += ["", f"**格局**：{c['geju']}"]
    lines.append(c["geju_note"])
    lines += ["", "**要点**"]
    for n in c["notes"]:
        lines.append(f"· {n}")
    return "\n".join(lines)


def xuankong(arg: str = "") -> str:
    return format_xuankong(cast_xuankong(arg))
