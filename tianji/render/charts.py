"""命盘图片渲染（Pillow）：八字盘、紫微盘、奇门盘、六壬盘等。"""

import io

from PIL import Image, ImageDraw, ImageFont



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


WX_COLOR = {
    "木": (46, 139, 87),    # 森绿
    "火": (200, 60, 50),    # 朱红
    "土": (178, 132, 58),   # 赭黄
    "金": (120, 120, 130),  # 银灰
    "水": (54, 110, 190),   # 沧蓝
}
DAY_MASTER_COLOR = (200, 30, 30)   # 日主红
TEXT_COLOR = (45, 45, 50)
SUB_COLOR = (110, 110, 118)
LINE_COLOR = (210, 210, 216)
BG_COLOR = (250, 250, 248)
PANEL_COLOR = (244, 246, 250)
TITLE_COLOR = (28, 32, 40)

_FONT_CANDIDATES = [
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simsun.ttc",
    "C:/Windows/Fonts/simkai.ttf",
    "C:/Windows/Fonts/Deng.ttf",
]


def _load_font(size):
    last_err = None
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue
    # 万般无奈用默认字体(中文会成方块, 仅作兜底)
    try:
        return ImageFont.load_default()
    except Exception:
        raise RuntimeError(f"找不到可用中文字体: {last_err}")


_FONTS = {}


def _font(size):
    if size not in _FONTS:
        _FONTS[size] = _load_font(size)
    return _FONTS[size]


def _text(draw, xy, text, font_size, fill=TEXT_COLOR, anchor="la"):
    draw.text(xy, text, font=_font(font_size), fill=fill, anchor=anchor)


def render_chart_image(chart: dict) -> io.BytesIO:
    """渲染命盘为竖版 PNG, 返回 BytesIO。"""
    W = 720
    pad = 28
    # 预渲染: 先算高度
    birth = chart["birth"]
    pillars = chart["pillars"]
    day_master = chart["day_master"]
    pattern = chart["pattern"]
    use_gods = chart["use_gods"]
    relations = chart["relations"]
    dayun = chart["dayun"]
    wuxing = chart["wuxing"]

    # 区块高度估计
    y = pad
    line = 26
    title_h = 54
    birth_h = 30
    birth_corr_h = 20 if birth.get("corrected") else 0
    grid_h = 248          # 四柱
    wx_h = 70
    dm_h = 30 + max(1, len(day_master.get("special_candidates", [])) or 0) * 22 + 8
    pat_h = 30 + max(1, len(pattern.get("candidates", [])) or 0) * 20 + \
        max(1, len(pattern.get("special_candidates", [])) or 0) * 20 + 8
    ug_h = 60
    rel_h = 30 + (22 if relations else 0)
    dy_rows = (len(dayun["list"]) + 3) // 4
    dy_h = 30 + 8 + 46 * dy_rows + 26
    footer_h = 46
    H = pad * 2 + title_h + birth_h + birth_corr_h + grid_h + wx_h + dm_h + pat_h + ug_h + rel_h + dy_h + footer_h

    img = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # ---- 标题 ----
    _text(draw, (W // 2, y), "八 字 命 盘 · 子 平 排 盘", 30, fill=TITLE_COLOR, anchor="ma")
    y += title_h

    # ---- 出生信息 ----
    birth_line = f"公历 {birth['solar']}　{birth['gender']}"
    if birth.get("city"):
        birth_line += f"　{birth['city']}"
    if birth.get("is_lunar") and birth.get("lunar_desc"):
        birth_line += f"　(农历 {birth['lunar_desc']})"
    _text(draw, (pad, y), birth_line, 17, fill=SUB_COLOR, anchor="la")
    if birth.get("corrected"):
        lo = birth.get("longitude_offset", 0.0) or 0.0
        eq = birth.get("equation_offset", 0.0) or 0.0
        solar_c = birth.get("solar_corrected")
        sc_str = solar_c.strftime("%Y-%m-%d %H:%M") if solar_c else ""
        corr = f"真太阳时校正: {sc_str}　(经度{lo:+.1f}分 均时差{eq:+.1f}分)"
        _text(draw, (pad, y + 22), corr, 13, fill=(90, 120, 90), anchor="la")
    y += birth_h + birth_corr_h

    # 分隔线
    def hline(yy):
        draw.line([(pad, yy), (W - pad, yy)], fill=LINE_COLOR, width=1)

    hline(y)
    y += 12

    # ---- 四柱 ----
    _text(draw, (pad, y), "【四柱八字】", 19, fill=TITLE_COLOR, anchor="la")
    y += 30
    col_w = (W - 2 * pad) / 4
    headers = ["年柱", "月柱", "日柱", "时柱"]
    # 表头
    for i, hname in enumerate(headers):
        cx = pad + col_w * i + col_w / 2
        color = DAY_MASTER_COLOR if hname == "日柱" else SUB_COLOR
        _text(draw, (cx, y), hname, 16, fill=color, anchor="ma")
    y += 26
    # 天干(大)
    for i, p in enumerate(pillars):
        cx = pad + col_w * i + col_w / 2
        color = DAY_MASTER_COLOR if p["label"] == "日" else TEXT_COLOR
        _text(draw, (cx, y + 20), p["gan"], 40, fill=color, anchor="ma")
    y += 50
    # 天干十神
    for i, p in enumerate(pillars):
        cx = pad + col_w * i + col_w / 2
        _text(draw, (cx, y), p["gan_deity"], 15, fill=SUB_COLOR, anchor="ma")
    y += 26
    # 地支(大)
    for i, p in enumerate(pillars):
        cx = pad + col_w * i + col_w / 2
        color = DAY_MASTER_COLOR if p["label"] == "日" else TEXT_COLOR
        _text(draw, (cx, y + 20), p["zhi"], 40, fill=color, anchor="ma")
    y += 50
    # 地支本气十神
    for i, p in enumerate(pillars):
        cx = pad + col_w * i + col_w / 2
        _text(draw, (cx, y), p["zhi_deity"], 15, fill=SUB_COLOR, anchor="ma")
    y += 26
    # 藏干(本气/中气/余气 + 十神)
    for i, p in enumerate(pillars):
        cx = pad + col_w * i + col_w / 2
        hidden = p["hidden"]
        label = "、".join(f"{h['stem']}({h['deity']})" for h in hidden)
        _text(draw, (cx, y), label, 12, fill=(140, 140, 150), anchor="ma")
    y += 32

    # ---- 五行分布 ----
    hline(y)
    y += 12
    _text(draw, (pad, y), "【五行分布】", 19, fill=TITLE_COLOR, anchor="la")
    y += 30
    maxv = max(wuxing.values()) or 1
    bx = pad
    bw = (W - 2 * pad - 4 * 14) / 5
    for wx in ["木", "火", "土", "金", "水"]:
        v = wuxing[wx]
        cx = bx + bw / 2
        _text(draw, (cx, y), f"{wx} {v:.1f}", 15, fill=WX_COLOR[wx], anchor="ma")
        bar_h = int((v / maxv) * 30) + 2
        draw.rectangle([bx + 6, y + 22, bx + bw - 6, y + 22 + 30], fill=PANEL_COLOR)
        draw.rectangle([bx + 6, y + 22 + 30 - bar_h, bx + bw - 6, y + 22 + 30], fill=WX_COLOR[wx])
        bx += bw + 14
    y += 22 + 30 + 12

    # ---- 日主旺衰 ----
    hline(y)
    y += 12
    _text(draw, (pad, y), "【日主与旺衰】", 19, fill=TITLE_COLOR, anchor="la")
    y += 28
    dm_txt = f"日主 {day_master['day_gan']}({day_master['day_element']})　{day_master['status']}　置信度 {day_master['confidence']}"
    _text(draw, (pad, y), dm_txt, 16, fill=DAY_MASTER_COLOR, anchor="la")
    y += 24
    _text(draw, (pad, y), f"月令: {day_master['month_judgment']}", 14, fill=SUB_COLOR, anchor="la")
    y += 22
    if day_master.get("special_candidates"):
        for sc in day_master["special_candidates"]:
            _text(draw, (pad + 6, y), f"· {sc}", 13, fill=(170, 110, 40), anchor="la")
            y += 20
    y += 6

    # ---- 格局 ----
    hline(y)
    y += 12
    _text(draw, (pad, y), "【格局】", 19, fill=TITLE_COLOR, anchor="la")
    y += 28
    sel = pattern["selected"]
    _text(draw, (pad, y), f"暂取: {sel['pattern']}　({sel['stem']}{sel['deity']}/{sel.get('level','本气')})", 16, fill=TEXT_COLOR, anchor="la")
    y += 22
    for c in pattern.get("candidates", [])[:6]:
        _text(draw, (pad + 6, y), f"· {c['pattern']}[{c['stem']}{c['deity']}/{c.get('level','')}]", 13, fill=SUB_COLOR, anchor="la")
        y += 20
    for sc in pattern.get("special_candidates", []):
        _text(draw, (pad + 6, y), f"· {sc}", 13, fill=(170, 110, 40), anchor="la")
        y += 20
    y += 6

    # ---- 喜用神 ----
    hline(y)
    y += 12
    _text(draw, (pad, y), "【喜用神参考】(格局/扶抑/调候分列)", 19, fill=TITLE_COLOR, anchor="la")
    y += 26
    fuyi = "；".join(f"{e}({r})" for e, r in use_gods.get("fuyi", []))
    _text(draw, (pad, y), f"扶抑: {fuyi}", 14, fill=SUB_COLOR, anchor="la")
    y += 22
    ce, cr = use_gods.get("climate", (None, ""))
    climate_txt = (ce + "，" if ce else "") + cr
    _text(draw, (pad, y), f"调候: {climate_txt}", 14, fill=SUB_COLOR, anchor="la")
    y += 26

    # ---- 地支关系 ----
    hline(y)
    y += 12
    _text(draw, (pad, y), "【地支关系】", 19, fill=TITLE_COLOR, anchor="la")
    y += 28
    if relations:
        _text(draw, (pad, y), "、".join(relations), 14, fill=SUB_COLOR, anchor="la")
    else:
        _text(draw, (pad, y), "未见明显三合/三会/六合/六冲/刑害", 14, fill=SUB_COLOR, anchor="la")
    y += 26

    # ---- 大运 ----
    hline(y)
    y += 12
    dirc = "顺" if dayun["forward"] else "逆"
    _text(draw, (pad, y), f"【大运】(起运 {dayun['start_age_years']}岁{dayun['start_age_months']}月 · {dirc}排)", 19, fill=TITLE_COLOR, anchor="la")
    y += 30
    # 每行 4 柱
    seq = dayun["list"]
    rows = (len(seq) + 3) // 4
    for r in range(rows):
        chunk = seq[r * 4:(r + 1) * 4]
        x = pad
        for item in chunk:
            _text(draw, (x, y), f"{item['age']}岁", 13, fill=SUB_COLOR, anchor="la")
            _text(draw, (x + 46, y + 1), item["ganzhi"], 22, fill=TEXT_COLOR, anchor="la")
            _text(draw, (x + 46, y + 26), item["deity"], 13, fill=WX_COLOR.get(use_gods.get("pattern_element", "木"), SUB_COLOR), anchor="la")
            x += 165
        y += 46
    y += 10

    # ---- 免责声明 ----
    hline(y)
    y += 8
    disclaimer = "本命盘由开源子平八字引擎排盘, 仅供传统文化研究参考, 不构成任何医疗/投资/婚恋建议。"
    _text(draw, (pad, y), disclaimer, 12, fill=(160, 160, 168), anchor="la")
    y += 18
    _text(draw, (pad, y), "命运在手, 修行在己。", 12, fill=(160, 160, 168), anchor="la")

    out = io.BytesIO()
    img.save(out, format="PNG")
    out.seek(0)
    return out

# ---------------------------------------------------------------- 紫微斗数盘面
ZIWEI_BG = (250, 249, 245)
ZIWEI_CELL = (255, 255, 255)
ZIWEI_MING_BG = (253, 246, 227)
ZIWEI_SHEN_BG = (238, 245, 252)
ZIWEI_LINE = (216, 214, 208)
ZIWEI_STAR = (36, 44, 66)
ZIWEI_LOOSE = (150, 150, 156)
ZIWEI_GOOD = (34, 120, 78)
ZIWEI_BAD = (186, 62, 52)
ZIWEI_HUA = {"禄": (34, 130, 74), "权": (36, 88, 170),
             "科": (140, 92, 26), "忌": (190, 48, 48)}

# 标准十二宫盘位: 行 x 列 -> 地支索引, -1 为中央信息区
_ZW_GRID = (
    (5, 6, 7, 8),
    (4, -1, -1, 9),
    (3, -1, -1, 10),
    (2, 1, 0, 11),
)

_ZW_MAIN_ORDER = ("紫微", "天机", "太阳", "武曲", "天同", "廉贞",
                  "天府", "太阴", "贪狼", "巨门", "天相", "天梁", "七杀", "破军")


def _zw_pack(draw, items, font_size, max_w, sep=" "):
    """把星名按宽度拼成多行。"""
    font = _font(font_size)
    rows, cur = [], ""
    for it in items:
        trial = it if not cur else cur + sep + it
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            rows.append(cur)
            cur = it
    if cur:
        rows.append(cur)
    return rows


def _zw_main_star(draw, cx, y, name, hua, size=19):
    """主星居中绘制, 四化以小字紧随其右。"""
    w1 = draw.textlength(name, font=_font(size))
    w2 = (draw.textlength(hua, font=_font(11)) + 3) if hua else 0
    x = cx - (w1 + w2) / 2
    _text(draw, (x, y), name, size, fill=ZIWEI_STAR, anchor="la")
    if hua:
        _text(draw, (x + w1 + 3, y + 5), hua, 11,
              fill=ZIWEI_HUA.get(hua, ZIWEI_STAR), anchor="la")


def render_ziwei_card(chart: dict) -> io.BytesIO:
    """紫微斗数盘面图(4x4 十二宫 + 中央信息区)。"""
    CELL = 228
    PAD = 14
    TOP = 104
    W = CELL * 4 + PAD * 2
    BOT = 52
    H = TOP + CELL * 4 + PAD + BOT
    img = Image.new("RGB", (W, H), ZIWEI_BG)
    draw = ImageDraw.Draw(img)

    # ---- 标题 ----
    yy = f"{chart['yin_yang']}{chart['gender']}"
    _text(draw, (PAD, 26), "紫 微 斗 数", 30, fill=TITLE_COLOR, anchor="la")
    _text(draw, (PAD, 68), f"{yy} · {chart['ju_name']} · 命主{chart['ming_zhu']}"
                           f" · 身主{chart['shen_zhu']}", 15, fill=SUB_COLOR, anchor="la")
    _text(draw, (W - PAD, 68), f"{chart['lunar']} {chart['hour_zhi']}时",
          15, fill=SUB_COLOR, anchor="ra")
    draw.line([(PAD, 96), (W - PAD, 96)], fill=ZIWEI_LINE, width=1)

    zhi_to_palace = {p["zhi"]: p for p in chart["palaces"]}

    # ---- 十二宫 ----
    for r, row in enumerate(_ZW_GRID):
        for c, zhi in enumerate(row):
            if zhi < 0:
                continue
            x0 = PAD + c * CELL
            y0 = TOP + r * CELL
            p = zhi_to_palace[zhi]
            is_ming = p["index"] == 0
            is_shen = chart["shen_zhi"] == zhi
            bg = ZIWEI_MING_BG if is_ming else (ZIWEI_SHEN_BG if is_shen else ZIWEI_CELL)
            draw.rectangle([x0, y0, x0 + CELL, y0 + CELL], fill=bg, outline=ZIWEI_LINE, width=1)
            if is_ming:
                draw.rectangle([x0, y0, x0 + CELL, y0 + CELL], outline=(206, 168, 68), width=3)

            # 左上: 地支 + 宫干
            _text(draw, (x0 + 12, y0 + 9), p["zhi_name"], 20, fill=TITLE_COLOR, anchor="la")
            _text(draw, (x0 + 36, y0 + 15), p["gan"], 12, fill=ZIWEI_LOOSE, anchor="la")
            # 右上: 宫名
            name_fill = (176, 128, 30) if is_ming else ((46, 104, 168) if is_shen else ZIWEI_LOOSE)
            _text(draw, (x0 + CELL - 12, y0 + 12), p["name"], 14, fill=name_fill, anchor="ra")

            inner_w = CELL - 24
            y = y0 + 40

            # 中央第一行: 主星 / 空宫
            main = sorted(p["main"], key=lambda s: _ZW_MAIN_ORDER.index(s) if s in _ZW_MAIN_ORDER else 99)
            if main:
                for s in main[:2]:
                    _zw_main_star(draw, x0 + CELL // 2, y, s, p["hua"].get(s))
                    y += 24
            else:
                _text(draw, (x0 + CELL // 2, y), "空宫", 16, fill=(184, 182, 176), anchor="ma")
                y += 21
                opp = chart["palaces"][(p["index"] + 6) % 12]
                borrow = " ".join(opp["main"]) or "无主星"
                _text(draw, (x0 + CELL // 2, y), f"借 {borrow}", 11, fill=ZIWEI_LOOSE, anchor="ma")
                y += 16

            # 辅煞星: 两列排布, 吉绿煞红
            col_w = (CELL - 24) // 2
            items = [(s, ZIWEI_GOOD, p["hua"].get(s)) for s in p["lucky"]]
            items += [(s, ZIWEI_BAD, p["hua"].get(s)) for s in p["malefic"]]
            y_start = y
            for i, (nm, col, hu) in enumerate(items):
                ry = y_start + (i // 2) * 17
                if ry > y0 + CELL - 30:
                    break
                rx = x0 + 12 + (i % 2) * col_w
                _text(draw, (rx, ry), nm, 12, fill=col, anchor="la")
                if hu:
                    _text(draw, (rx + draw.textlength(nm, font=_font(12)) + 2, ry + 1),
                          hu, 9, fill=ZIWEI_HUA.get(hu, col), anchor="la")

            # 右下: 大限
            ds = p.get("daxian")
            if ds:
                _text(draw, (x0 + CELL - 12, y0 + CELL - 16),
                      f"{ds[0]}-{ds[1]}", 12, fill=ZIWEI_LOOSE, anchor="rd")

    # ---- 中央信息区 ----
    cx0 = PAD + CELL
    cy0 = TOP + CELL
    cw = CELL * 2
    draw.rectangle([cx0, cy0, cx0 + cw, cy0 + cw], fill=(247, 246, 241), outline=ZIWEI_LINE, width=1)
    mid = cx0 + cw // 2

    _text(draw, (mid, cy0 + 34), f"{yy}", 26, fill=TITLE_COLOR, anchor="ma")
    _text(draw, (mid, cy0 + 72), chart["ju_name"], 17, fill=(150, 108, 40), anchor="ma")
    draw.line([(cx0 + 40, cy0 + 104), (cx0 + cw - 40, cy0 + 104)], fill=ZIWEI_LINE, width=1)

    rows = [
        ("公历", chart["solar"]),
        ("农历", chart["lunar"].replace("农历", "")),
        ("命宫", f"{chart['ming']['zhi_name']}（{chart['ming']['key']}）"),
        ("身宫", f"{chart['shen_key']} · 在{chart['shen_palace']}"),
        ("命主", chart["ming_zhu"]),
        ("身主", chart["shen_zhu"]),
        ("起限", f"{chart['ju_num']} 岁{'顺行' if chart['forward'] else '逆行'}"),
    ]
    y = cy0 + 122
    for k, v in rows:
        _text(draw, (cx0 + 46, y), k, 13, fill=ZIWEI_LOOSE, anchor="la")
        _text(draw, (cx0 + 100, y), v, 14, fill=ZIWEI_STAR, anchor="la")
        y += 26

    # 生年四化
    y += 8
    draw.line([(cx0 + 40, y - 8), (cx0 + cw - 40, y - 8)], fill=ZIWEI_LINE, width=1)
    _text(draw, (mid, y + 2), f"生年四化（{chart['y_gan']}干）", 13, fill=ZIWEI_LOOSE, anchor="ma")
    y += 28
    for i, key in enumerate(("禄", "权", "科", "忌")):
        col = i % 2
        row_i = i // 2
        px = cx0 + 62 + col * (cw // 2 - 30)
        py = y + row_i * 26
        _text(draw, (px, py), key, 15, fill=ZIWEI_HUA[key], anchor="la")
        _text(draw, (px + 22, py + 2), chart["sihua"][key], 14, fill=ZIWEI_STAR, anchor="la")

    # ---- 页脚 ----
    fy = H - BOT + 14
    foot = "小小辰辰 · 紫微斗数"
    _text(draw, (PAD, fy), foot, 12, fill=ZIWEI_LOOSE, anchor="la")
    _text(draw, (W - PAD, fy), "通行排法 · 仅供传统文化参考", 12, fill=ZIWEI_LOOSE, anchor="ra")

    out = io.BytesIO()
    img.save(out, format="PNG")
    out.seek(0)
    return out


# ---------------------------------------------------------------- 奇门遁甲盘面
QIMEN_BG = (250, 249, 245)
QIMEN_CELL = (255, 255, 255)
QIMEN_JI_BG = (243, 249, 243)
QIMEN_MID_BG = (246, 245, 240)
QIMEN_LINE = (214, 212, 206)
QIMEN_STAR = (36, 44, 66)
QIMEN_DOOR = (52, 78, 120)
QIMEN_JI_DOOR = (30, 116, 74)
QIMEN_SHEN = (128, 96, 148)
QIMEN_GAN_T = (188, 74, 52)     # 天盘干(红)
QIMEN_GAN_D = (54, 96, 164)     # 地盘干(蓝)
QIMEN_LOOSE = (152, 150, 146)
QIMEN_FU = (196, 158, 62)       # 值符宫金框

# 九宫格显示顺序(巽离坤 / 震中兑 / 艮坎乾)
_QIMEN_GRID = (
    (4, 9, 2),
    (3, 5, 7),
    (8, 1, 6),
)


def render_qimen_card(chart: dict) -> io.BytesIO:
    """奇门遁甲九宫盘面图。"""
    CELL = 278
    PAD = 16
    TOP = 128
    BOT = 58
    W = CELL * 3 + PAD * 2
    H = TOP + CELL * 3 + BOT
    img = Image.new("RGB", (W, H), QIMEN_BG)
    draw = ImageDraw.Draw(img)

    yin_yang = "阳遁" if chart["yang"] else "阴遁"
    _text(draw, (PAD, 22), "奇 门 遁 甲", 30, fill=TITLE_COLOR, anchor="la")
    _text(draw, (PAD, 64),
          f"{chart['ju_name']} · 拆补法 · 转盘 · {chart['jieqi']}{chart['yuan']}",
          15, fill=SUB_COLOR, anchor="la")
    _text(draw, (W - PAD, 64),
          f"{chart['solar']} {chart['clock']}", 15, fill=SUB_COLOR, anchor="ra")
    _text(draw, (PAD, 92),
          f"{chart['year_gz']}年 {chart['month_gz']}月 {chart['day_gz']}日 "
          f"{chart['time_gz']}时 · 旬首{chart['xun']}",
          13, fill=QIMEN_LOOSE, anchor="la")
    _text(draw, (W - PAD, 92),
          f"值符{chart['fu_star']} · 值使{chart['fu_door']}",
          13, fill=QIMEN_LOOSE, anchor="ra")
    draw.line([(PAD, 118), (W - PAD, 118)], fill=QIMEN_LINE, width=1)

    for r, row in enumerate(_QIMEN_GRID):
        for c, g in enumerate(row):
            x0 = PAD + c * CELL
            y0 = TOP + r * CELL
            p = chart["by_gong"][g]
            is_mid = g == 5
            is_fu = (not is_mid) and g == chart["fu_land"]
            bg = QIMEN_MID_BG if is_mid else (QIMEN_JI_BG if p["ji"] else QIMEN_CELL)
            draw.rectangle([x0, y0, x0 + CELL, y0 + CELL], fill=bg,
                           outline=QIMEN_LINE, width=1)
            if is_fu:
                draw.rectangle([x0, y0, x0 + CELL, y0 + CELL],
                               outline=QIMEN_FU, width=3)

            _text(draw, (x0 + 12, y0 + 9), p["name"], 14, fill=QIMEN_LOOSE, anchor="la")
            _text(draw, (x0 + CELL - 12, y0 + 9), p["fangwei"], 12,
                  fill=QIMEN_LOOSE, anchor="ra")

            if is_mid:
                _text(draw, (x0 + CELL // 2, y0 + CELL // 2 - 30), "天禽",
                      26, fill=QIMEN_STAR, anchor="ma")
                _text(draw, (x0 + CELL // 2, y0 + CELL // 2 + 6), "寄坤二宫",
                      14, fill=QIMEN_LOOSE, anchor="ma")
                _text(draw, (x0 + CELL // 2, y0 + CELL // 2 + 36),
                      f"地盘 {p['gan_di'] or '—'}", 16, fill=QIMEN_GAN_D, anchor="ma")
                continue

            # 神
            if p["shen"]:
                _text(draw, (x0 + CELL // 2, y0 + 38), p["shen"], 17,
                      fill=(QIMEN_FU if p["shen"] == "值符" else QIMEN_SHEN), anchor="ma")
            # 星
            _text(draw, (x0 + CELL // 2, y0 + 72), p["star"], 26,
                  fill=QIMEN_STAR, anchor="ma")
            # 门
            _text(draw, (x0 + CELL // 2, y0 + 118), p["door"], 26,
                  fill=(QIMEN_JI_DOOR if p["ji"] else QIMEN_DOOR), anchor="ma")
            # 天地盘干
            _text(draw, (x0 + CELL // 2 - 34, y0 + CELL - 62),
                  f"天 {p['gan_tian'] or '—'}", 17, fill=QIMEN_GAN_T, anchor="ma")
            _text(draw, (x0 + CELL // 2 + 34, y0 + CELL - 62),
                  f"地 {p['gan_di'] or '—'}", 17, fill=QIMEN_GAN_D, anchor="ma")

    fy = TOP + CELL * 3 + 12
    tips = chart["patterns"][:2]
    for i, t in enumerate(tips):
        txt = t if len(t) <= 46 else t[:45] + "…"
        _text(draw, (PAD, fy + i * 18), "· " + txt, 12, fill=SUB_COLOR, anchor="la")

    out = io.BytesIO()
    img.save(out, format="PNG")
    out.seek(0)
    return out


# ---------------------------------------------------------------- 大六壬盘面
LIUREN_BG = (250, 249, 245)
_ZHI12 = "子丑寅卯辰巳午未申酉戌亥"
LIUREN_CELL = (255, 255, 255)
LIUREN_LINE = (214, 212, 206)
LIUREN_TIAN = (38, 48, 74)
LIUREN_DI = (158, 156, 150)
LIUREN_SHEN_C = (132, 96, 150)
LIUREN_QIN = (46, 110, 120)
LIUREN_CHUAN = (196, 158, 62)
LIUREN_KONG = (196, 194, 188)


def render_liuren_card(chart: dict) -> io.BytesIO:
    """大六壬天地盘 + 四课三传图。"""
    W = 940
    PAD = 16
    CELL = (W - PAD * 2) // 4          # 227
    CELL_H = 196
    TOP = 104
    KE_H = 96
    CH_H = 92
    grid_y = TOP + KE_H + CH_H + 24
    H = grid_y + CELL_H * 3 + 56
    img = Image.new("RGB", (W, H), LIUREN_BG)
    draw = ImageDraw.Draw(img)

    _text(draw, (PAD, 20), "大 六 壬", 30, fill=TITLE_COLOR, anchor="la")
    _text(draw, (PAD, 64),
          f"月将 {_ZHI12[chart['yuejiang']]}（{chart['yuejiang_name']}）"
          f"加 {chart['shi_name']}时 · {chart['zhou']} · 课体 {chart['method']}",
          15, fill=SUB_COLOR, anchor="la")
    _text(draw, (W - PAD, 64),
          f"{chart['solar']} {chart['clock']}", 15, fill=SUB_COLOR, anchor="ra")
    _text(draw, (PAD, 88),
          f"{chart['day_gz']}日 {chart['time_gz']}时 · 贵人{chart['guiren']}"
          f"（{'顺行' if chart['forward'] else '逆行'}）"
          f" · 旬空{''.join(_ZHI12[z] for z in chart['xunkong'])}"
          f" · 驿马{_ZHI12[chart['ma']]}",
          13, fill=LIUREN_DI, anchor="la")
    draw.line([(PAD, 100), (W - PAD, 100)], fill=LIUREN_LINE, width=1)

    # ---- 四课 ----
    ke = chart["ke"]
    for i, k in enumerate(ke):
        x0 = PAD + i * CELL
        y0 = TOP
        draw.rectangle([x0 + 3, y0, x0 + CELL - 3, y0 + KE_H - 8],
                       fill=LIUREN_CELL, outline=LIUREN_LINE, width=1)
        _text(draw, (x0 + CELL // 2, y0 + 6), f"{('一', '二', '三', '四')[i]}课",
              12, fill=LIUREN_DI, anchor="ma")
        _text(draw, (x0 + CELL // 2, y0 + 22), k["up_name"], 26,
              fill=LIUREN_TIAN, anchor="ma")
        down = k["down_label"]
        if k["no"] == 1:
            down = f"{down}({_ZHI12[k['down']]})"
        _text(draw, (x0 + CELL // 2, y0 + 54), down, 14, fill=LIUREN_DI, anchor="ma")
        _text(draw, (x0 + CELL // 2, y0 + 73),
              f"{k['jiang']} · {k['liuqin']}", 12, fill=LIUREN_QIN, anchor="ma")

    # ---- 三传 ----
    cy = TOP + KE_H
    for i, ch in enumerate(chart["chuan"]):
        x0 = PAD + i * CELL
        draw.rectangle([x0 + 3, cy, x0 + CELL - 3, cy + CH_H - 8],
                       fill=(253, 250, 240), outline=LIUREN_CHUAN, width=1)
        label = ("初传", "中传", "末传")[i]
        _text(draw, (x0 + CELL // 2, cy + 6), label, 12, fill=LIUREN_CHUAN, anchor="ma")
        _text(draw, (x0 + CELL // 2, cy + 22), ch["name"], 26,
              fill=LIUREN_TIAN, anchor="ma")
        tip = f"临{ch['lin_name']} · {ch['jiang']}"
        _text(draw, (x0 + CELL // 2, cy + 54), tip, 12, fill=LIUREN_SHEN_C, anchor="ma")
        tail = ch["liuqin"] + ("·空" if ch["kong"] else "") + ("·马" if ch["ma"] else "")
        _text(draw, (x0 + CELL // 2, cy + 70), tail, 12, fill=LIUREN_QIN, anchor="ma")

    # ---- 十二宫天地盘 ----
    chuan_pos = {ch["lin"]: ("初", "中", "末")[i] for i, ch in enumerate(chart["chuan"])}
    for i in range(12):
        r, c = i // 4, i % 4
        x0 = PAD + c * CELL
        y0 = grid_y + r * CELL_H
        mark = chuan_pos.get(i)
        bg = (253, 250, 240) if mark else LIUREN_CELL
        draw.rectangle([x0, y0, x0 + CELL, y0 + CELL_H], fill=bg,
                       outline=LIUREN_LINE, width=1)
        if mark:
            draw.rectangle([x0, y0, x0 + CELL, y0 + CELL_H],
                           outline=LIUREN_CHUAN, width=3)
        # 左上: 地盘支
        _text(draw, (x0 + 10, y0 + 8), _ZHI12[i], 15, fill=LIUREN_DI, anchor="la")
        # 右上: 天将
        _text(draw, (x0 + CELL - 10, y0 + 9), chart["jiang"][i], 13,
              fill=LIUREN_SHEN_C, anchor="ra")
        # 中央: 天盘支
        is_kong = chart["tianpan"][i] in chart["xunkong"]
        _text(draw, (x0 + CELL // 2, y0 + CELL_H // 2 - 32),
              _ZHI12[chart["tianpan"][i]], 48,
              fill=(LIUREN_KONG if is_kong else LIUREN_TIAN), anchor="ma")
        if mark:
            _text(draw, (x0 + CELL // 2, y0 + CELL_H - 30), mark, 14,
                  fill=LIUREN_CHUAN, anchor="ma")

    # ---- 页脚 ----
    fy = H - 40
    tip = chart["notes"][1] if len(chart["notes"]) > 1 else ""
    _text(draw, (PAD, fy), tip[:52], 12, fill=SUB_COLOR, anchor="la")
    _text(draw, (W - PAD, fy), "通行九宗门排法 · 仅供传统文化参考", 12,
          fill=LIUREN_DI, anchor="ra")

    out = io.BytesIO()
    img.save(out, format="PNG")
    out.seek(0)
    return out


# ---------------------------------------------------------------- 金口诀盘面
JJ_BG = (250, 249, 245)
JJ_CELL = (255, 255, 255)
JJ_LINE = (214, 212, 206)
JJ_LABEL = (246, 244, 238)
JJ_GAN_C = (188, 74, 52)      # 人元(干)
JJ_SHEN_C = (128, 96, 148)    # 贵神(天将)
JJ_JIANG_C = (46, 78, 132)    # 将神(支)
JJ_FEN_C = (38, 112, 88)      # 地分(支)
JJ_WANG_C = (32, 122, 82)     # 旺相
JJ_RUO_C = (158, 156, 150)    # 休囚死
JJ_NOTE = (128, 126, 122)


_JJ_JI = frozenset(("贵人", "青龙", "六合", "太常"))
_JJ_XIONG = frozenset(("白虎", "玄武", "勾陈", "天空", "螣蛇"))


def render_jinjue_card(c: dict) -> io.BytesIO:
    """金口诀四位课盘面（人元/贵神/将神/地分 竖排）。"""
    W = 880
    PAD = 18
    ROW = 122
    TOP = 156
    TABLE_W = W - PAD * 2
    H = TOP + ROW * 4 + 132
    img = Image.new("RGB", (W, H), JJ_BG)
    draw = ImageDraw.Draw(img)

    _text(draw, (PAD, 20), "金 口 诀", 30, fill=TITLE_COLOR, anchor="la")
    _text(draw, (W - PAD, 26),
          f"{c['solar']} {c['clock']}", 15, fill=SUB_COLOR, anchor="ra")
    _text(draw, (PAD, 64),
          f"{c['year_gz']}年 {c['month_gz']}月 {c['day_gz']}日 {c['time_gz']}时"
          f" · 月令{c['ling']}当令 · 旬空"
          + "".join(_ZHI12[z] for z in c["xunkong"]),
          14, fill=SUB_COLOR, anchor="la")
    _text(draw, (PAD, 90),
          f"月将 {_ZHI12[c['yuejiang']]}（{c['yuejiang_name']}） · {c['zhou']}"
          f" · 贵人乘{c['guiren']}临{c['guiren_pos']}"
          f"（{'顺行' if c['forward'] else '逆行'}）",
          13, fill=JJ_NOTE, anchor="la")
    _text(draw, (W - PAD, 90),
          f"地分 {c['fen_name']}（{c['fen_fangwei']}）", 14, fill=JJ_FEN_C, anchor="ra")
    _text(draw, (PAD, 116),
          (c["fen_src"] or "") + " · 四位自上而下：人元 / 贵神 / 将神 / 地分",
          12, fill=JJ_NOTE, anchor="la")
    draw.line([(PAD, 142), (W - PAD, 142)], fill=JJ_LINE, width=1)

    colors = (JJ_GAN_C, JJ_SHEN_C, JJ_JIANG_C, JJ_FEN_C)
    for i, s in enumerate(c["siwei"]):
        x0 = PAD
        y0 = TOP + i * ROW
        y1 = y0 + ROW - 8
        draw.rectangle([x0, y0, x0 + TABLE_W, y1], fill=JJ_CELL,
                       outline=JJ_LINE, width=1)
        # 左侧位名
        draw.rectangle([x0, y0, x0 + 104, y1], fill=JJ_LABEL, outline=JJ_LINE, width=1)
        _text(draw, (x0 + 52, y0 + ROW // 2 - 26), s["pos"], 20,
              fill=colors[i], anchor="mm")
        _text(draw, (x0 + 52, y0 + ROW // 2 + 4), s["note"], 11,
              fill=JJ_NOTE, anchor="mm")
        # 大字
        _text(draw, (x0 + 104 + 92, y0 + ROW // 2 - 10), s["val"], 52,
              fill=colors[i], anchor="mm")
        # 五行 / 旺衰
        _text(draw, (x0 + 300, y0 + 34), s["wx"], 22, fill=SUB_COLOR, anchor="la")
        ws_color = JJ_WANG_C if s["ws"] in ("旺", "相") else JJ_RUO_C
        _text(draw, (x0 + 300, y0 + 68), s["ws"], 22, fill=ws_color, anchor="la")
        # 右侧信息
        info = []
        if s["nai"]:
            info.append(f"纳音 {s['nai']}")
        if i == 0:
            info.append(f"日干{c['day_gan']}起五子元遁至{c['fen_name']}")
        elif i == 1:
            info.append(f"起于{c['guiren_pos']}位，{'顺' if c['forward'] else '逆'}数至地分")
        elif i == 2:
            info.append("月将加时，地分上临之支")
        else:
            info.append("求测方位所定，全课之根")
        for j, t in enumerate(info):
            _text(draw, (x0 + 356, y0 + 34 + j * 26), t, 13, fill=JJ_NOTE, anchor="la")
        # 右侧吉凶标记
        if i == 1:
            mark = "吉将" if c["gui_shen"] in _JJ_JI else (
                "凶将" if c["gui_shen"] in _JJ_XIONG else "平神")
            mk_c = JJ_WANG_C if mark == "吉将" else (JJ_GAN_C if mark == "凶将" else JJ_NOTE)
            _text(draw, (x0 + TABLE_W - 16, y0 + ROW // 2 - 10), mark, 15,
                  fill=mk_c, anchor="ra")

    # ---- 底部：五动 + 要点 ----
    fy = TOP + ROW * 4 + 6
    draw.line([(PAD, fy), (W - PAD, fy)], fill=JJ_LINE, width=1)
    dong = "　".join(f"{n}·{h}" for n, h, _ in c["dong"])
    _text(draw, (PAD, fy + 12), "五动：" + (dong or "无"), 14,
          fill=TITLE_COLOR, anchor="la")
    _text(draw, (PAD, fy + 40), "课体：" + "；".join(c["keti"][:2])[:56], 13,
          fill=SUB_COLOR, anchor="la")
    for i, n in enumerate(c["notes"][:2]):
        _text(draw, (PAD, fy + 66 + i * 22), "· " + n[:50], 12,
              fill=JJ_NOTE, anchor="la")

    out = io.BytesIO()
    img.save(out, format="PNG")
    out.seek(0)
    return out


# ---------------------------------------------------------------- 玄空飞星盘
_XK_C_BG = (250, 249, 245)
_XK_C_CELL = (255, 255, 255)
_XK_C_LINE = (214, 212, 206)
_XK_C_NAME = {1: "坎", 2: "坤", 3: "震", 4: "巽", 5: "中",
              6: "乾", 7: "兑", 8: "艮", 9: "离"}
_XK_C_FANG = {1: "正北", 2: "西南", 3: "正东", 4: "东南", 5: "中宫",
              6: "西北", 7: "正西", 8: "东北", 9: "正南"}
_XK_C_SHAN = (54, 96, 164)     # 山星(蓝)
_XK_C_XIANG = (188, 74, 52)    # 向星(红)
_XK_C_YUN = (150, 146, 138)    # 运星(灰)
_XK_C_ZUO = (196, 158, 62)
_XK_C_XIANG2 = (46, 122, 96)
_XK_C_HIT = (253, 250, 238)

# 洛书九宫布局(巽离坤 / 震中兑 / 艮坎乾)
_XK_C_GRID = ((4, 9, 2), (3, 5, 7), (8, 1, 6))


def render_xuankong_card(c: dict) -> io.BytesIO:
    """玄空飞星九宫盘(山星左上 / 向星右上 / 运星居中)。"""
    CELL = 250
    PAD = 16
    TOP = 148
    BOT = 132
    W = CELL * 3 + PAD * 2
    H = TOP + CELL * 3 + BOT
    img = Image.new("RGB", (W, H), _XK_C_BG)
    draw = ImageDraw.Draw(img)

    zi, xi, yun = c["zuo"], c["xiang"], c["yun"]
    _text(draw, (PAD, 20), "玄 空 飞 星", 30, fill=TITLE_COLOR, anchor="la")
    _text(draw, (W - PAD, 26),
          f"{zi['shan']}山{xi['shan']}向", 22, fill=_XK_C_XIANG, anchor="ra")
    _text(draw, (PAD, 64),
          f"{yun['name']}（{yun['start']}–{yun['end']}）· {c['geju']}",
          16, fill=SUB_COLOR, anchor="la")
    _text(draw, (PAD, 90),
          f"坐 {zi['shan']}（{zi['gong_name']}·{zi['yuan']}·{zi['yinyang']}）"
          f" {zi['du']}°　向 {xi['shan']}（{xi['gong_name']}·{xi['yuan']}·"
          f"{xi['yinyang']}） {xi['du']}°",
          13, fill=_XK_C_YUN, anchor="la")
    _text(draw, (PAD, 114),
          f"{c['liunian_year']}年{c['liunian_star']}入中 · 左上=山星 右上=向星 中=运星"
          + (f" · {c['parse_note']}" if c["parse_note"] else ""),
          12, fill=_XK_C_YUN, anchor="la")
    draw.line([(PAD, 138), (W - PAD, 138)], fill=_XK_C_LINE, width=1)

    pan_by_gong = {g["gong"]: g for g in c["gongs"]}
    for r, row in enumerate(_XK_C_GRID):
        for col, g in enumerate(row):
            p = pan_by_gong[g]
            x0 = PAD + col * CELL
            y0 = TOP + r * CELL
            hot = p["shan"] == yun["star"] or p["xiang"] == yun["star"]
            draw.rectangle([x0, y0, x0 + CELL, y0 + CELL],
                           fill=(_XK_C_HIT if hot else _XK_C_CELL),
                           outline=_XK_C_LINE, width=1)
            if p["is_zuo"]:
                draw.rectangle([x0, y0, x0 + CELL, y0 + CELL],
                               outline=_XK_C_ZUO, width=3)
            if p["is_xiang"]:
                draw.rectangle([x0 + 3, y0 + 3, x0 + CELL - 3, y0 + CELL - 3],
                               outline=_XK_C_XIANG2, width=2)
            # 山星(左上)
            _text(draw, (x0 + 16, y0 + 12), str(p["shan"]), 26,
                  fill=_XK_C_SHAN, anchor="la")
            _text(draw, (x0 + 16, y0 + 44), p["shan_qi"], 11,
                  fill=_XK_C_SHAN, anchor="la")
            # 向星(右上)
            _text(draw, (x0 + CELL - 16, y0 + 12), str(p["xiang"]), 26,
                  fill=_XK_C_XIANG, anchor="ra")
            _text(draw, (x0 + CELL - 16, y0 + 44), p["xiang_qi"], 11,
                  fill=_XK_C_XIANG, anchor="ra")
            # 运星(中)
            _text(draw, (x0 + CELL // 2, y0 + CELL // 2 - 6), str(p["yun"]), 46,
                  fill=_XK_C_YUN, anchor="mm")
            # 底部宫名
            _text(draw, (x0 + CELL // 2, y0 + CELL - 44),
                  f"{_XK_C_NAME[g]}宫", 15, fill=SUB_COLOR, anchor="ma")
            _text(draw, (x0 + CELL // 2, y0 + CELL - 24),
                  "" if g == 5 else _XK_C_FANG[g], 11, fill=_XK_C_YUN, anchor="ma")
            if p["is_zuo"]:
                _text(draw, (x0 + CELL // 2, y0 + CELL - 72), "坐", 13,
                      fill=_XK_C_ZUO, anchor="ma")
            elif p["is_xiang"]:
                _text(draw, (x0 + CELL // 2, y0 + CELL - 72), "向", 13,
                      fill=_XK_C_XIANG2, anchor="ma")

    fy = TOP + CELL * 3 + 10
    draw.line([(PAD, fy), (W - PAD, fy)], fill=_XK_C_LINE, width=1)
    _text(draw, (PAD, fy + 10), "格局：" + c["geju"], 14,
          fill=TITLE_COLOR, anchor="la")
    tips = c["notes"][:3]
    for i, t in enumerate(tips):
        txt = t if len(t) <= 58 else t[:57] + "…"
        _text(draw, (PAD, fy + 36 + i * 20), "· " + txt, 12,
              fill=_XK_C_YUN, anchor="la")
    _text(draw, (W - PAD, fy + 10), "金锁：坎坤震巽宜砂，乾兑艮离宜水", 11,
          fill=_XK_C_YUN, anchor="ra")

    out = io.BytesIO()
    img.save(out, format="PNG")
    out.seek(0)
    return out


# ---------------------------------------------------------------- 太乙神数盘面
TY_BG = (250, 249, 245)
TY_CELL = (255, 255, 255)
TY_MID = (246, 245, 240)
TY_LINE = (214, 212, 206)
TY_LOOSE = (152, 150, 146)
TY_STAR = (36, 44, 66)
TY_MEN = (52, 78, 120)
TY_MEN_JI = (30, 116, 74)
TY_MEN_XIONG = (176, 66, 48)
TY_WHO = (128, 96, 148)
TY_TAIYI = (196, 158, 62)
TY_JIANG = (46, 100, 150)

# 太乙九宫方位布局（宫号与洛书不同：乾1 / 离2 / 艮3 / 震4 / 中5 / 兑6 / 坤7 / 坎8 / 巽9）
_TY_GRID = (
    (9, 2, 7),
    (4, 5, 6),
    (3, 8, 1),
)
_TY_GUA = {1: "乾", 2: "离", 3: "艮", 4: "震", 5: "中",
           6: "兑", 7: "坤", 8: "坎", 9: "巽"}
_TY_FANG = {1: "西北", 2: "正南", 3: "东北", 4: "正东", 5: "中央",
            6: "正西", 7: "西南", 8: "正北", 9: "东南"}
_TY_QI = {1: "绝阳", 2: "易气", 3: "和", 4: "绝气", 5: "枢纽",
          6: "绝气", 7: "和", 8: "易气", 9: "绝阴"}


def render_taiyi_card(c: dict) -> io.BytesIO:
    """太乙神数岁计九宫盘（三式之首）。"""
    CELL = 262
    PAD = 16
    TOP = 152
    BOT = 118
    W = CELL * 3 + PAD * 2
    H = TOP + CELL * 3 + BOT
    img = Image.new("RGB", (W, H), TY_BG)
    draw = ImageDraw.Draw(img)

    _text(draw, (PAD, 20), "太 乙 神 数", 30, fill=TITLE_COLOR, anchor="la")
    _text(draw, (W - PAD, 26), f"{c['year_gz']}年 · 岁计", 20,
          fill=TY_MEN, anchor="ra")
    _text(draw, (PAD, 64),
          f"积年 {c['jinian']} · {c['yuan']}{c['ji']} · {c['yin_yang']}第"
          f" {c['ju']} 局 · 太乙临 {c['taiyi_gong']}宫"
          f"（{c['taiyi_gua']}·{c['taiyi_fang']}）",
          15, fill=SUB_COLOR, anchor="la")
    _text(draw, (PAD, 92),
          f"主算 {c['zhu_suan']}·{c['zhu_shu']}　客算 {c['ke_suan']}·{c['ke_shu']}"
          f"　值使 {c['zhi_shi']}门",
          14, fill=TY_STAR, anchor="la")
    _text(draw, (PAD, 118),
          f"文昌 {c['wenchang']}({c['wenchang_pos']})　"
          f"始击 {c['shiji']}({c['shiji_pos']})　计神 {c['ji_shen']}({c['ji_shen_pos']})",
          13, fill=TY_LOOSE, anchor="la")
    draw.line([(PAD, 144), (W - PAD, 144)], fill=TY_LINE, width=1)

    by_gong = {p["gong"]: p for p in c["palaces"]}
    for r, row in enumerate(_TY_GRID):
        for col, g in enumerate(row):
            x0 = PAD + col * CELL
            y0 = TOP + r * CELL
            p = by_gong.get(g)
            is_mid = (g == 5)
            is_ty = (g == c["taiyi_gong"])
            bg = TY_MID if is_mid else TY_CELL
            draw.rectangle([x0, y0, x0 + CELL, y0 + CELL], fill=bg,
                           outline=TY_LINE, width=1)
            if is_ty:
                draw.rectangle([x0, y0, x0 + CELL, y0 + CELL],
                               outline=TY_TAIYI, width=3)

            # 左上：宫号 + 卦
            _text(draw, (x0 + 12, y0 + 10), f"{g} {_TY_GUA[g]}", 15,
                  fill=TY_LOOSE, anchor="la")
            _text(draw, (x0 + CELL - 12, y0 + 10), _TY_FANG[g], 12,
                  fill=TY_LOOSE, anchor="ra")

            if is_mid:
                _text(draw, (x0 + CELL // 2, y0 + CELL // 2 - 24), "中宫", 24,
                      fill=TY_LOOSE, anchor="ma")
                _text(draw, (x0 + CELL // 2, y0 + CELL // 2 + 8), "太乙不居", 14,
                      fill=TY_LOOSE, anchor="ma")
                _text(draw, (x0 + CELL // 2, y0 + CELL // 2 + 38), _TY_QI[5], 13,
                      fill=TY_LOOSE, anchor="ma")
                continue

            men = p["men"] if p else ""
            mc = (TY_MEN_JI if p and p["men_ji"] else
                  (TY_MEN_XIONG if p and p["men_xiong"] else TY_MEN))
            _text(draw, (x0 + CELL // 2, y0 + 52), f"{men}门" if men else "", 22,
                  fill=mc, anchor="ma")

            who = p["who"] if p else []
            if "太乙" in who:
                _text(draw, (x0 + CELL // 2, y0 + 112), "太 乙", 30,
                      fill=TY_TAIYI, anchor="ma")
                rest = [w for w in who if w != "太乙"]
            else:
                rest = who
            if rest:
                _text(draw, (x0 + CELL // 2, y0 + 160), " ".join(rest[:3]), 14,
                      fill=TY_WHO, anchor="ma")
                if len(rest) > 3:
                    _text(draw, (x0 + CELL // 2, y0 + 182), " ".join(rest[3:6]), 14,
                          fill=TY_WHO, anchor="ma")

            _text(draw, (x0 + CELL // 2, y0 + CELL - 30), _TY_QI[g], 12,
                  fill=TY_LOOSE, anchor="ma")

    fy = TOP + CELL * 3 + 8
    draw.line([(PAD, fy), (W - PAD, fy)], fill=TY_LINE, width=1)
    tips = c["geju"][:2]
    for i, t in enumerate(tips):
        txt = t if len(t) <= 40 else t[:39] + "…"
        _text(draw, (PAD, fy + 12 + i * 22), "· " + txt, 13, fill=SUB_COLOR, anchor="la")
    _text(draw, (W - PAD, fy + 12),
          f"主大将{c['zhu_jiang']} 主参将{c['zhu_can']}　"
          f"客大将{c['ke_jiang']} 客参将{c['ke_can']}", 12,
          fill=TY_JIANG, anchor="ra")

    out = io.BytesIO()
    img.save(out, format="PNG")
    out.seek(0)
    return out


QZ_BG = (250, 249, 245)
QZ_CELL = (255, 255, 255)
QZ_LINE = (214, 212, 206)
QZ_MING_BG = (253, 245, 226)
QZ_SHEN_BG = (237, 244, 252)
QZ_TITLE_C = (36, 44, 66)
QZ_LOOSE = (154, 152, 148)
QZ_STAR_C = {
    "日": (198, 120, 26), "月": (74, 118, 166), "水": (100, 132, 154),
    "金": (170, 138, 52), "火": (190, 66, 52), "木": (42, 114, 74),
    "土": (138, 100, 56), "罗": (146, 70, 90), "计": (112, 88, 144),
    "孛": (64, 88, 124), "气": (86, 124, 90),
}
QZ_DIG_C = {"庙": (34, 120, 78), "旺": (34, 120, 78),
            "落": (186, 62, 52), "弱": (186, 62, 52)}


def _qz_star_chip(draw, x, y, name, size=20):
    """画一颗星曜：色点 + 单字。返回占用宽度。"""
    col = QZ_STAR_C.get(name, QZ_TITLE_C)
    draw.ellipse([x, y + size // 2 - 3, x + 7, y + size // 2 + 4], fill=col)
    _text(draw, (x + 12, y), name, size, fill=col, anchor="la")
    return 12 + size


def render_qizheng_card(c: dict) -> io.BytesIO:
    """七政四余十二宫盘（十一曜躔度 · 命身宫）。"""
    CW, CH = 236, 186
    PAD = 16
    TOP = 166
    BOT = 176
    W = CW * 4 + PAD * 2
    H = TOP + CH * 3 + BOT
    img = Image.new("RGB", (W, H), QZ_BG)
    draw = ImageDraw.Draw(img)

    b = c["birth"]
    ming = c["ming"]
    shen = c["shen"]

    _text(draw, (PAD, 18), "七 政 四 余", 30, fill=TITLE_COLOR, anchor="la")
    _text(draw, (W - PAD, 26), "果老星宗 · 十一曜", 15, fill=QZ_LOOSE, anchor="ra")

    pil = " ".join(c["pillars"])
    _text(draw, (PAD, 62), pil, 22, fill=QZ_TITLE_C, anchor="la")
    _text(draw, (W - PAD, 66),
          f"{b['solar']}　{b['gender']}" + (f"　{b['city']}" if b["city"] else ""),
          14, fill=SUB_COLOR, anchor="ra")

    _text(draw, (PAD, 96),
          f"真太阳时 {c['solar_time']}"
          + (f"（经度差{c['lon_off']:+.0f}分 均时差{c['eq_off']:+.0f}分）"
             if c["corrected"] else "（未校正）"),
          13, fill=QZ_LOOSE, anchor="la")

    _text(draw, (PAD, 120),
          f"命宫 {ming['zhi']}宫·{ming['xingzuo']}　命度 "
          f"{ming['su']}宿{ming['su_du_txt']}　命宫主 {ming['ruler']}"
          f"　命度主 {ming['du_zhu']}",
          14, fill=QZ_TITLE_C, anchor="la")
    _text(draw, (PAD, 143),
          f"身宫 {shen['zhi']}宫·{shen['xingzuo']}　身宫主 {shen['ruler']}"
          f"　　日干 {c['day_gan']}（{c['day_wx']}）　恩/用/仇/难已标于曜后",
          13, fill=SUB_COLOR, anchor="la")

    # ---- 十二宫格
    for g in c["gongwei"]:
        k = g["idx"]
        r, col = divmod(k, 4)
        x0 = PAD + col * CW
        y0 = TOP + r * CH
        is_ming = (k == 0)
        is_shen = (g["gong"] == shen["gong"])
        bg = QZ_MING_BG if is_ming else (QZ_SHEN_BG if is_shen else QZ_CELL)
        draw.rectangle([x0, y0, x0 + CW, y0 + CH], fill=bg, outline=QZ_LINE, width=1)
        if is_ming:
            draw.rectangle([x0, y0, x0 + CW, y0 + CH], outline=(196, 158, 62), width=2)
        elif is_shen:
            draw.rectangle([x0, y0, x0 + CW, y0 + CH], outline=(122, 158, 196), width=2)

        _text(draw, (x0 + 12, y0 + 9), g["name"], 18,
              fill=(176, 122, 32) if is_ming else QZ_TITLE_C, anchor="la")
        _text(draw, (x0 + CW - 12, y0 + 12),
              f"{g['zhi']}·{g['xingzuo']}", 12, fill=QZ_LOOSE, anchor="ra")

        stars = g["stars"]
        if not stars:
            _text(draw, (x0 + CW // 2, y0 + 92), "空", 18, fill=(208, 206, 202),
                  anchor="ma")
        else:
            cx, cy = x0 + 14, y0 + 46
            for i, s in enumerate(stars):
                if i and i % 3 == 0:
                    cx = x0 + 14
                    cy += 34
                w = _qz_star_chip(draw, cx, cy, s, 21)
                cx += w + 26
                if cx > x0 + CW - 50:
                    cx = x0 + 14
                    cy += 34
                if cy > y0 + CH - 66:
                    break
            for i, s in enumerate(stars):
                p = next(x for x in c["planets"] if x["name"] == s)
                tag = p["dig"] if p["dig"] and p["dig"] != "平" else ""
                if tag:
                    _text(draw, (x0 + 14 + (i % 3) * 66, y0 + 46 + (i // 3) * 34 + 24),
                          tag, 11, fill=QZ_DIG_C.get(tag, QZ_LOOSE), anchor="la")

        _text(draw, (x0 + 12, y0 + CH - 24),
              f"宫主 {g['ruler']}" + ("　身宫" if is_shen else ""), 12,
              fill=(122, 158, 196) if is_shen else QZ_LOOSE, anchor="la")

    # ---- 十一曜躔度
    fy = TOP + CH * 3 + 8
    draw.line([(PAD, fy), (W - PAD, fy)], fill=QZ_LINE, width=1)
    _text(draw, (PAD, fy + 8), "十一曜躔度", 13, fill=QZ_TITLE_C, anchor="la")
    colw = (W - PAD * 2) // 6
    for i, p in enumerate(c["planets"]):
        r, col = divmod(i, 6)
        x = PAD + col * colw
        y = fy + 30 + r * 30
        col_c = QZ_STAR_C.get(p["name"], QZ_TITLE_C)
        _text(draw, (x, y), p["name"], 15, fill=col_c, anchor="la")
        _text(draw, (x + 18, y + 2),
              f"{p['zhi']}{p['gong_du']:.2f}° {p['su']}{p['su_du']:.1f}", 12,
              fill=SUB_COLOR, anchor="la")

    gy = fy + 30 + 2 * 30 + 4
    for i, t in enumerate(c["geju"][:2]):
        txt = t if len(t) <= 52 else t[:51] + "…"
        _text(draw, (PAD, gy + i * 20), "· " + txt, 12, fill=SUB_COLOR, anchor="la")

    out = io.BytesIO()
    img.save(out, format="PNG")
    out.seek(0)
    return out
