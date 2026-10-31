"""生肖配对（六合/三合/相冲/相刑/相害）。"""

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

from .scenecommon import *  # noqa: F401,F403


def _hp_sx_of(tok: str):
    tok = tok.strip().lstrip("属")
    if tok in _SC_SX_ZHI:
        return _SC_SX_ZHI[tok]
    if tok in _SC_ZHI_SX:
        return tok
    raise ValueError(f"看不懂生肖「{tok}」喵")


def shengxiao(arg: str = "") -> str:
    """生肖配对。参数: 龙鸡 / 龙鸡配 / 属龙 属鸡。"""
    text = (arg or "").strip()
    toks = [t for t in re.split(r"[\s,，、]+", text) if t]
    # 支持连写「龙鸡」「属龙属鸡」：拆成单字
    chars = []
    for t in toks:
        t = t.replace("属", "")
        chars.extend(list(t))
    chars = [c for c in chars if c in _SC_SX_ZHI or c in _SC_ZHI_SX]
    if len(chars) != 2:
        raise ValueError("用法：生肖配对 龙鸡 / 生肖配对 属龙 属鸡")
    z1, z2 = _hp_sx_of(chars[0]), _hp_sx_of(chars[1])
    rel = _hp_rel(z1, z2)
    score = 3
    for r in rel:
        score += {"六合": 2, "三合": 2, "值": 1, "冲": -2, "刑": -1, "害": -1}.get(r, 0)
    stars = "★" * max(1, min(5, score)) + "☆" * (5 - max(1, min(5, score)))
    verdict = "、".join(rel) if rel else "平（无冲合刑害）"
    duan = "；".join(_HP_SX_DUAN.get(r, "") for r in rel if r in _HP_SX_DUAN) \
        or "无特殊关系，相处全凭经营，好处是没有宿命包袱。"
    lines = [
        f"【生肖配对】{_SC_ZHI_SX[z1]}（{z1}）× {_SC_ZHI_SX[z2]}（{z2}）",
        f"关系：{verdict}",
        f"断语：{duan}",
        f"合拍指数：{stars}",
        "※ 生肖只看年支一层，真正的合盘要看八字日主与夫妻宫。" + _SC_NOTE.replace("※ ", "\n※ ", 1),
    ]
    return "\n".join(lines)


_HP_LIN_DUAN = {
    1: "领导者/开创者，独立要强", 2: "协调者/共情者，敏感细腻",
    3: "表达者/创意者，活泼爱玩", 4: "执行者/务实派，稳定靠谱",
    5: "自由派/冒险家，怕被束缚", 6: "责任者/照顾者，家庭至上",
    7: "思考者/研究者，需要独处", 8: "掌局者/事业咖，目标导向",
    9: "理想主义者，格局大心也软",
}


def _hp_life_path(y: int, m: int, d: int) -> int:
    n = y // 10000 + y % 10000 + m + d
    # 逐位求和迭代到一位数
    while n > 9:
        n = sum(int(c) for c in str(n))
    return n


def lingshu(arg: str = "") -> str:
    """生命灵数配对。参数: 1990-05-20 1992-08-15。"""
    nums = re.findall(r"(\d{4})\s*[-/年.]\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})", (arg or "").strip())
    if len(nums) != 2:
        raise ValueError("用法：灵数配对 1990-05-20 1992-08-15（两份公历生日）")
    (y1, m1, d1), (y2, m2, d2) = [(int(a), int(b), int(c)) for a, b, c in nums]
    n1, n2 = _hp_life_path(y1, m1, d1), _hp_life_path(y2, m2, d2)
    score = 3
    if n1 == n2:
        rel = "同数（本命共振）"
        score += 1
        duan = f"两个{n1}号人：{_HP_LIN_DUAN[n1]}。像照镜子，默契满分，但要防同一个坑一起跳。"
    elif n1 + n2 == 10:
        rel = "互补数（相加成十）"
        score += 2
        duan = f"{n1}号人×{n2}号人是经典互补组合——{_HP_LIN_DUAN[n1]}，而对方{_HP_LIN_DUAN[n2]}，正好接住彼此的短处。"
    elif abs(n1 - n2) == 1:
        rel = "相邻数（一路人）"
        score += 1
        duan = f"相邻灵数节奏相近：{_HP_LIN_DUAN[n1]}，对方{_HP_LIN_DUAN[n2]}，像并排走的两条路。"
    elif abs(n1 - n2) == 4:
        rel = "对冲数（互相较劲）"
        score -= 1
        duan = f"{n1}号与{n2}号天然互相较劲：{_HP_LIN_DUAN[n1]} vs {_HP_LIN_DUAN[n2]}，斗嘴是日常，定了边界反而长久。"
    else:
        rel = "异质数（互相好奇）"
        duan = f"{n1}号人{_HP_LIN_DUAN[n1]}，{n2}号人{_HP_LIN_DUAN[n2]}，差异大、新鲜感也大，磨合期别急着下结论。"
    stars = "★" * max(1, min(5, score)) + "☆" * (5 - max(1, min(5, score)))
    lines = [
        f"【生命灵数配对】",
        f"甲方 {y1}-{m1:02d}-{d1:02d} → 灵数 {n1}号（{_HP_LIN_DUAN[n1]}）",
        f"乙方 {y2}-{m2:02d}-{d2:02d} → 灵数 {n2}号（{_HP_LIN_DUAN[n2]}）",
        f"关系：{rel}",
        f"断语：{duan}",
        f"合拍指数：{stars}",
        _SC_NOTE,
    ]
    return "\n".join(lines)


# ---- 取自原合盘批的生肖配对数据 ----

_HP_SX_DUAN = {
    "六合": "六合是暗中的默契，平时不显山露水，关键时候总能为对方兜底。",
    "三合": "三合是明面上的合拍，三观相近、玩得来，是别人羡慕的一对/一伙。",
    "值": "同生肖，脾性相像，懂得彼此，但也容易把一样的毛病放大。",
    "冲": "相冲是正面碰撞，磁场强、吸引也快，吵得凶也爱得深，全看谁先低头。",
    "刑": "相刑是暗耗，小事上互相别扭，说不上谁错，就是不舒服。",
    "害": "相害是背地里使绊子，防第三方掺和与口舌，透明沟通可解。",
}

# ---- 取自原合盘批的生肖关系工具 ----

def _hp_rel(z1: str, z2: str) -> list:
    """两地支关系词列表。"""
    out = []
    if z1 == z2:
        out.append("值")
    if _SC_LIUHE.get(z1) == z2:
        out.append("六合")
    g1 = [t for t in _SC_SANHE if z1 in t]
    if g1 and z2 in g1[0]:
        out.append("三合")
    if _SC_CHONG.get(z1) == z2:
        out.append("冲")
    if _SC_XING.get(z1) == z2 or _SC_XING.get(z2) == z1:
        out.append("刑")
    if _SC_HAI.get(z1) == z2:
        out.append("害")
    return out


def _hp_life_path(y: int, m: int, d: int) -> int:
    n = y // 10000 + y % 10000 + m + d
    # 逐位求和迭代到一位数
    while n > 9:
        n = sum(int(c) for c in str(n))
    return n
