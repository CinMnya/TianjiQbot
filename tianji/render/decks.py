"""牌占图片渲染（Pillow）：塔罗 / 雷诺曼 / 泰式塔罗牌面。"""

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

from .charts import _font, _text, TITLE_COLOR, SUB_COLOR


TC_BG = (247, 245, 240)
TC_CARD = (255, 255, 255)
TC_LINE = (208, 204, 196)
TC_MAJOR = (146, 118, 52)
TC_MINOR = (108, 118, 132)
TC_UP = (46, 122, 84)
TC_REV = (186, 74, 58)
TC_MUTE = (150, 147, 141)


_THAI_FONT_CANDIDATES = [
    "C:/Windows/Fonts/leelawui.ttf",
    "C:/Windows/Fonts/Leelawadee UI.ttf",
    "C:/Windows/Fonts/tahoma.ttf",
    "C:/Windows/Fonts/angsauc.ttf",
]

_THAI_FONTS = {}


def _thai_font(size):
    """泰文字形字体（中文字体不含泰文，会渲染成方块）。"""
    if size not in _THAI_FONTS:
        for path in _THAI_FONT_CANDIDATES:
            try:
                _THAI_FONTS[size] = ImageFont.truetype(path, size)
                break
            except Exception:  # noqa: BLE001
                continue
        else:
            _THAI_FONTS[size] = _font(size)
    return _THAI_FONTS[size]


def _tc_wrap(draw, txt, size, max_w):
    """按像素宽度把文本折成多行（连续 ASCII 视为单词不拆开）。"""
    font = _font(size)
    tokens = re.findall(r"[A-Za-z0-9]+|[^A-Za-z0-9]", str(txt))
    lines, cur = [], ""
    for tk in tokens:
        if tk == " " and not cur:
            continue
        trial = cur + tk
        if draw.textlength(trial, font=font) > max_w and cur:
            lines.append(cur.strip())
            cur = "" if tk == " " else tk
        else:
            cur = trial
    if cur.strip():
        lines.append(cur.strip())
    return lines


def _tc_face(card, cw, chh):
    """渲染一张牌面（未旋转）。card: dict(name,en,kw,reversed,major,num,thai?)"""
    img = Image.new("RGB", (cw, chh), TC_CARD)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([1, 1, cw - 2, chh - 2], radius=10,
                        outline=TC_LINE, width=2)
    major = card.get("major")
    col = TC_MAJOR if major else TC_MINOR
    y = 18
    # 顶部：编号 / 元素带
    if card.get("plain"):
        top = f"第{card['num']}张"
    elif major and card.get("num") is not None:
        top = f"{card['num']} · 大阿尔卡纳"
    else:
        top = "小阿尔卡纳"
    if card.get("thai"):
        d.text((cw // 2, y), card["thai"], font=_thai_font(17),
               fill=TC_MUTE, anchor="ma")
        y += 28
    elif top:
        _text(d, (cw // 2, y), top, 13, fill=TC_MUTE, anchor="ma")
        y += 24
    # 主名（可两行）
    for ln in _tc_wrap(d, card["name"], 26, cw - 24)[:2]:
        _text(d, (cw // 2, y), ln, 26, fill=col, anchor="ma")
        y += 34
    _text(d, (cw // 2, y), card["en"], 13, fill=TC_MUTE, anchor="ma")
    y += 30
    d.line([(cw // 3, y), (cw - cw // 3, y)], fill=TC_LINE, width=1)
    y += 14
    # 牌义
    for ln in _tc_wrap(d, card["kw"], 16, cw - 32)[:8]:
        _text(d, (cw // 2, y), ln, 16, fill=(70, 68, 64), anchor="ma")
        y += 24
    # 底部：正逆位徽章（雷诺曼等 plain 牌不设）
    if card.get("plain"):
        return img
    tag = "逆位" if card.get("reversed") else "正位"
    tagc = TC_REV if card.get("reversed") else TC_UP
    bw = 84
    d.rounded_rectangle([cw // 2 - bw // 2, chh - 44, cw // 2 + bw // 2, chh - 14],
                        radius=8, outline=tagc, width=2)
    _text(d, (cw // 2, chh - 29), tag, 17, fill=tagc, anchor="mm")
    return img


def _tc_sheet(title, subtitle, cards, footer, render_fn, cw, chh, gap=22,
              pad=26):
    n = len(cards)
    w = pad * 2 + n * cw + (n - 1) * gap
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    reserved = 150 if w >= 620 else 0
    sub_lines = _tc_wrap(probe, subtitle, 15, w - pad * 2 - reserved)[:2]
    head = 104 + 24 * len(sub_lines)
    foot = 92
    h = head + chh + foot
    img = Image.new("RGB", (w, h), TC_BG)
    d = ImageDraw.Draw(img)
    _text(d, (pad, 20), title, 26, fill=TITLE_COLOR, anchor="la")
    for i, ln in enumerate(sub_lines):
        _text(d, (pad, 60 + i * 24), ln, 15, fill=SUB_COLOR, anchor="la")
    _text(d, (w - pad, 30), "仅供文化娱乐参考", 12, fill=TC_MUTE, anchor="ra")
    x = pad
    for c in cards:
        face = render_fn(c, cw, chh)
        img.paste(face, (x, head))
        x += cw + gap
    fy = head + chh + 18
    d.line([(pad, fy), (w - pad, fy)], fill=TC_LINE, width=1)
    for i, ln in enumerate(_tc_wrap(d, footer, 14, w - pad * 2)[:3]):
        _text(d, (pad, fy + 12 + i * 22), ln, 14, fill=SUB_COLOR, anchor="la")
    out = io.BytesIO()
    img.save(out, format="PNG")
    out.seek(0)
    return out


def render_tarot_card(c: dict) -> io.BytesIO:
    """塔罗牌阵图。逆位牌旋转 180 度。"""
    qs = f"问题：{c['question']}" if c["question"] else "心中默念所问之事"
    sub = f"{c['spread']} · {qs}"
    n_rev = sum(1 for p in c["cards"] if p["reversed"])
    n_major = sum(1 for p in c["cards"] if p["major"])
    footer = (f"{' · '.join(c['positions'])}    "
              f"正位 {len(c['cards']) - n_rev} / 逆位 {n_rev} / "
              f"大阿尔卡纳 {n_major} 张    抽牌 {c['time']}")

    def rf(card, cw, chh):
        face = _tc_face(card, cw, chh)
        return face.rotate(180) if card.get("reversed") else face

    return _tc_sheet("塔罗占卜", sub, c["cards"], footer, rf, 186, 300)


_ORIG_LN_FACE = _tc_face


def _ln_face(card, cw, chh):
    return _ORIG_LN_FACE({**card, "plain": True}, cw, chh)


def render_lenormand_card(c: dict) -> io.BytesIO:
    """雷诺曼卡线图（不设逆位）。"""
    qs = f"问题：{c['question']}" if c["question"] else "心中默念所问之事"
    sub = f"{c['spread']} · {qs} · 从左到右连读"
    footer = f"{' · '.join(c['positions'])}    抽卡 {c['time']}"
    return _tc_sheet("雷诺曼占卜", sub, c["cards"], footer, _ln_face,
                     170, 260)


def render_thaitarot_card(c: dict) -> io.BytesIO:
    """泰式塔罗图。"""
    qs = f"问题：{c['question']}" if c["question"] else "心中默念所问之事"
    sub = f"泰语语境 RWS 大阿尔卡纳 · {qs}"
    n_rev = sum(1 for p in c["cards"] if p["reversed"])
    footer = (f"{' · '.join(p['pos'] for p in c['cards'])}    "
              f"正位 {len(c['cards']) - n_rev} / 逆位 {n_rev}    抽牌 {c['time']}")

    def rf(card, cw, chh):
        face = _tc_face(card, cw, chh)
        return face.rotate(180) if card.get("reversed") else face

    return _tc_sheet("泰式塔罗", sub, c["cards"], footer, rf, 260, 330)
