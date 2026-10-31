"""太乙神数（岁计 · 八将 · 主客算）。"""

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


TAIYI_JINIAN_BASE = 1936557   # 1937281(开元十二年=724) - 724

# 太乙九宫（宫号, 卦, 门, 方位, 分野, 宫气）—— 太乙宫号与洛书数不同
TAIYI_GONG = {
    1: ("乾", "天门", "西北", "冀州·并州", "绝阳"),
    2: ("离", "火门", "正南", "荆州·豫州", "易气"),
    3: ("艮", "鬼门", "东北", "青州", "和"),
    4: ("震", "日门", "正东", "徐州", "绝气"),
    5: ("中", "中宫", "中央", "京畿", "枢纽"),
    6: ("兑", "月门", "正西", "雍州", "绝气"),
    7: ("坤", "人门", "西南", "梁州·益州", "和"),
    8: ("坎", "水门", "正北", "兖州", "易气"),
    9: ("巽", "风门", "东南", "扬州", "绝阴"),
}

# 太乙行宫次序（不入中五宫）
TAIYI_SEQ = (1, 2, 3, 4, 6, 7, 8, 9)
TAIYI_OPP = {1: 9, 9: 1, 2: 8, 8: 2, 3: 7, 7: 3, 4: 6, 6: 4}

# 十六神（名, 所临, 正宫宫号或 None）
TAIYI_SHEN16 = (
    ("地主", "子", None), ("阳德", "丑", None), ("和德", "艮", 3),
    ("吕申", "寅", None), ("高丛", "卯", None), ("太阳", "辰", None),
    ("大炅", "巽", 9), ("大神", "巳", None), ("大威", "午", None),
    ("天道", "未", None), ("大武", "坤", 7), ("武德", "申", None),
    ("太簇", "酉", None), ("阴主", "戌", None), ("阴德", "乾", 1),
    ("大义", "亥", None),
)

# 八门固定宫位（开乾、休坎、生艮、伤震、杜巽、景离、死坤、惊兑）
TAIYI_MEN = ("开", "休", "生", "伤", "杜", "景", "死", "惊")
TAIYI_MEN_GONG = {"开": 1, "休": 8, "生": 3, "伤": 4, "杜": 9, "景": 2, "死": 7, "惊": 6}
TAIYI_MEN_JI = ("开", "休", "生")
TAIYI_MEN_XIONG = ("死", "伤", "杜")

# 十二支序（子=0）
TAIYI_ZHI = "子丑寅卯辰巳午未申酉戌亥"
TAIYI_GAN = "甲乙丙丁戊己庚辛壬癸"
TAIYI_YUAN = ("甲子元", "丙子元", "戊子元", "庚子元", "壬子元")
TAIYI_JI = ("第一纪", "第二纪", "第三纪", "第四纪", "第五纪", "第六纪")


def _ty_gz(index: int) -> str:
    return TAIYI_GAN[index % 10] + TAIYI_ZHI[index % 12]


def _shen_of_zhi(zhi: str) -> int:
    """十二支 → 十六神索引。"""
    for i, (_, z, _) in enumerate(TAIYI_SHEN16):
        if z == zhi:
            return i
    return 0


def _step_shen(start: int, n: int, extra) -> int:
    """自 start 顺行数 n 步（起点算 1），途经 extra 中的神位时重留一次。"""
    idx = start
    cnt = 1
    while cnt < n:
        idx = (idx + 1) % 16
        cnt += 1
        if cnt >= n:
            break
        if idx in extra:
            cnt += 1
    return idx


def _step_gong(gong: int, n: int, forward: bool = True) -> int:
    """按太乙宫序走 n 步（n 可负）。"""
    i = TAIYI_SEQ.index(gong)
    if not forward:
        n = -n
    return TAIYI_SEQ[(i + n) % 8]


def _count_suan(start_shen: int, taiyi_gong: int) -> tuple:
    """自某神起，顺行累加沿途正宫宫号，至太乙前一宫止。返回 (算数, 明细)。"""
    gong = TAIYI_SHEN16[start_shen][2]
    total = gong if gong else 1
    detail = [f"{'正宫' + str(gong) if gong else '间神起1'}"]
    if gong == taiyi_gong:
        # 起于太乙本宫，不再前行
        detail.append("起于太乙宫")
        return total, " ".join(detail)
    idx = start_shen
    guard = 0
    while guard < 16:
        guard += 1
        idx = (idx + 1) % 16
        g = TAIYI_SHEN16[idx][2]
        if g is None:
            continue
        if g == 5:
            continue
        if g == taiyi_gong:
            break
        total += g
        detail.append(f"+{g}({TAIYI_GONG[g][0]})")
    return total, " ".join(detail)


def _jiang_gong(suan: int) -> int:
    """算数 → 大将宫：满十去之；十、二十、三十以九除取余。"""
    if suan in (10, 20, 30):
        r = suan % 9
        return r if r else 9
    r = suan % 10
    return r if r else 9


def _can_gong(jiang: int) -> int:
    v = jiang * 3
    r = v % 10
    if r == 0:
        r = 9 if v % 10 == 0 and v // 10 in (1, 2, 3) else 9
    return r if r in TAIYI_SEQ else r


def _san_cai(suan: int) -> str:
    """三才算：无十为无天、无五为无地、无一为无人。"""
    s = str(suan)
    tian = "有天" if suan >= 10 else "无天"
    di = "有地" if "5" in s else "无地"
    ren = "有人" if "1" in s else "无人"
    return "·".join((tian, di, ren))


def _yin_yang_shu(suan: int) -> str:
    if suan in (3, 9):
        return "重阳"
    if suan in (2, 6):
        return "重阴"
    if suan in (1, 7):
        return "阴中重阳"
    if suan in (4, 8):
        return "阳中重阴"
    if suan in (11, 13, 37):
        return "单孤之阳"
    if suan == 24:
        return "孤阴"
    if suan in (14, 18):
        return "上和"
    if suan in (12, 16, 21, 27, 34, 38):
        return "下和"
    if suan in (22, 26, 29, 32, 36):
        return "次和"
    return "常算"


def cast_taiyi(when: str = "") -> dict:
    """太乙岁计起局。when 可传年份（如 2026 / 2026-10-24）或留空取今年。"""
    import re
    from datetime import datetime
    now = datetime.now()
    year = now.year
    when = (when or "").strip()
    m = re.search(r"(1\d{3}|20\d{2}|21\d{2})", when)
    if m:
        year = int(m.group(1))
    yue = now.month
    m2 = re.search(r"(?:年[-/.]?)(\d{1,2})[-/月]", when)
    if m2:
        try:
            yue = int(m2.group(1))
        except Exception:
            pass
    if year < 1:
        year = now.year

    jinian = TAIYI_JINIAN_BASE + year
    yuan_l = jinian % 360
    yuan = yuan_l // 72
    ji = yuan_l // 60
    ju = jinian % 72
    if ju == 0:
        ju = 72

    # 岁计用阳遁
    yin_yang = "阳遁"
    r24 = ju % 24
    if r24 == 0:
        r24 = 24
    steps = (r24 - 1) // 3          # 0..7
    taiyi_gong = TAIYI_SEQ[steps]

    # 天目（文昌）：入局数 % 18，阳遁自武德起、阴遁自吕申起
    n18 = ju % 18
    if n18 == 0:
        n18 = 18
    if yin_yang == "阳遁":
        start_shen = 11                     # 武德（申）
        extra = {14, 10}                    # 乾、坤重留
    else:
        start_shen = 3                      # 吕申（寅）
        extra = {2, 6}                      # 艮、巽重留
    wenchang = _step_shen(start_shen, n18, extra)

    # 计神：岁计，子年起寅、丑年起丑、寅年起子（逆推）
    year_gz = _ty_gz(year - 4)                # 公元 4 年为甲子
    year_zhi = TAIYI_ZHI.index(year_gz[1])
    ji_shen_zhi = (2 - year_zhi) % 12
    ji_shen = _shen_of_zhi(TAIYI_ZHI[ji_shen_zhi])

    # 始击（客目）：计神加和德，天目所乘
    shiji = (wenchang + 2 - ji_shen) % 16

    # 主客算
    zhu_suan, zhu_detail = _count_suan(wenchang, taiyi_gong)
    ke_suan, ke_detail = _count_suan(shiji, taiyi_gong)
    zhu_jiang = _jiang_gong(zhu_suan)
    ke_jiang = _jiang_gong(ke_suan)
    zhu_can = (zhu_jiang * 3) % 10 or 9
    ke_can = (ke_jiang * 3) % 10 or 9

    # 八门：开门加太乙，顺布八宫
    men = {}
    base = TAIYI_SEQ.index(taiyi_gong)
    for i, m_ in enumerate(TAIYI_MEN):
        men[TAIYI_SEQ[(base + i) % 8]] = m_

    # 值使门：积年 % 240 // 30
    zhi_shi = TAIYI_MEN[(jinian % 240) // 30]

    # 格局
    ge = []
    if shiji == wenchang:
        ge.append("掩（始击与天目同宫）")
    if TAIYI_SHEN16[shiji][2] == taiyi_gong:
        ge.append("掩（始击与太乙同宫）")
    if zhu_jiang == taiyi_gong:
        ge.append("囚（主大将同太乙）")
    if ke_jiang == taiyi_gong:
        ge.append("囚（客大将同太乙）")
    if TAIYI_SHEN16[wenchang][2] == TAIYI_OPP.get(taiyi_gong, 0):
        ge.append("对（天目冲太乙）")
    if zhu_jiang == TAIYI_OPP.get(taiyi_gong, 0):
        ge.append("格（主大将与太乙相对）")
    if TAIYI_SHEN16[shiji][2] in (
            _step_gong(taiyi_gong, 1), _step_gong(taiyi_gong, -1)):
        ge.append("击（始击在太乙左右）")
    for label, g in (("主大将", zhu_jiang), ("客大将", ke_jiang),
                     ("文昌", TAIYI_SHEN16[wenchang][2]),
                     ("始击", TAIYI_SHEN16[shiji][2])):
        if g in (_step_gong(taiyi_gong, 1), _step_gong(taiyi_gong, -1)):
            ge.append(f"迫（{label}临太乙前后）")
    if zhu_suan == 5 or ke_suan == 5:
        ge.append("杜塞（五算出而无门无将）")
    if not ge:
        ge.append("无掩迫囚击，三才算和")

    # 落宫
    place = {i: [] for i in TAIYI_SEQ}
    place[taiyi_gong].append("太乙")
    for label, idx in (("文昌", wenchang), ("始击", shiji), ("计神", ji_shen)):
        g = TAIYI_SHEN16[idx][2]
        if g in place:
            place[g].append(label)
    for label, g in (("主大将", zhu_jiang), ("主参将", zhu_can),
                     ("客大将", ke_jiang), ("客参将", ke_can)):
        if g in place:
            place[g].append(label)

    palaces = []
    for g in TAIYI_SEQ:
        gua, door, fang, fenye, qi = TAIYI_GONG[g]
        palaces.append({
            "gong": g, "gua": gua, "door": door, "fang": fang,
            "fenye": fenye, "qi": qi, "men": men.get(g, ""),
            "men_ji": men.get(g) in TAIYI_MEN_JI,
            "men_xiong": men.get(g) in TAIYI_MEN_XIONG,
            "who": place[g],
            "is_taiyi": g == taiyi_gong,
        })

    return {
        "year": year, "year_gz": year_gz,
        "jinian": jinian,
        "yuan": TAIYI_YUAN[yuan], "ji": TAIYI_JI[ji],
        "ju": ju, "yin_yang": yin_yang,
        "taiyi_gong": taiyi_gong,
        "taiyi_gua": TAIYI_GONG[taiyi_gong][0],
        "taiyi_fang": TAIYI_GONG[taiyi_gong][2],
        "wenchang": TAIYI_SHEN16[wenchang][0],
        "wenchang_pos": TAIYI_SHEN16[wenchang][1],
        "wenchang_gong": TAIYI_SHEN16[wenchang][2],
        "shiji": TAIYI_SHEN16[shiji][0],
        "shiji_pos": TAIYI_SHEN16[shiji][1],
        "shiji_gong": TAIYI_SHEN16[shiji][2],
        "ji_shen": TAIYI_SHEN16[ji_shen][0],
        "ji_shen_pos": TAIYI_SHEN16[ji_shen][1],
        "zhu_suan": zhu_suan, "zhu_detail": zhu_detail,
        "ke_suan": ke_suan, "ke_detail": ke_detail,
        "zhu_jiang": zhu_jiang, "zhu_can": zhu_can,
        "ke_jiang": ke_jiang, "ke_can": ke_can,
        "zhi_shi": zhi_shi, "men": men,
        "geju": ge, "palaces": palaces,
        "zhu_san_cai": _san_cai(zhu_suan),
        "ke_san_cai": _san_cai(ke_suan),
        "zhu_shu": _yin_yang_shu(zhu_suan),
        "ke_shu": _yin_yang_shu(ke_suan),
        "note": "按《太乙金镜式经》岁计口径；月/日/时计各派入局法不同，此处不作推算。",
    }


def format_taiyi(c: dict) -> str:
    from datetime import datetime
    lines = [
        f"## 太乙神数 · {c['year_gz']}年岁计",
        "",
        f"**积年** {c['jinian']}（上元甲子起算）· {c['yuan']}{c['ji']}",
        f"**入局** {c['yin_yang']}第 {c['ju']} 局 · 太乙临 {c['taiyi_gong']}宫"
        f"（{c['taiyi_gua']}·{c['taiyi_fang']}）",
        "",
        "**八将落宫**",
        f"· 太乙：{c['taiyi_gong']}宫（{c['taiyi_gua']}，{TAIYI_GONG[c['taiyi_gong']][4]}）",
        f"· 文昌(天目)：{c['wenchang']}·{c['wenchang_pos']}"
        + (f"，临{c['wenchang_gong']}宫" if c['wenchang_gong'] else "（间神）"),
        f"· 始击(客目)：{c['shiji']}·{c['shiji_pos']}"
        + (f"，临{c['shiji_gong']}宫" if c['shiji_gong'] else "（间神）"),
        f"· 计神：{c['ji_shen']}·{c['ji_shen_pos']}",
        f"· 主大将 {c['zhu_jiang']}宫　主参将 {c['zhu_can']}宫",
        f"· 客大将 {c['ke_jiang']}宫　客参将 {c['ke_can']}宫",
        "",
        f"**主算 {c['zhu_suan']}** · {c['zhu_shu']} · {c['zhu_san_cai']} · "
        f"{'长算' if c['zhu_suan'] >= 11 else '短算'}",
        f"　算路：{c['zhu_detail']}",
        f"**客算 {c['ke_suan']}** · {c['ke_shu']} · {c['ke_san_cai']} · "
        f"{'长算' if c['ke_suan'] >= 11 else '短算'}",
        f"　算路：{c['ke_detail']}",
        "",
        f"**八门**（开门加太乙顺布）· 值使门 **{c['zhi_shi']}门**",
    ]
    for p in c["palaces"]:
        mark = "　← 太乙" if p["is_taiyi"] else ""
        who = ("　" + "/".join(p["who"])) if p["who"] else ""
        lines.append(f"· {p['gong']}宫{p['gua']}（{p['fang']}）{p['men']}门"
                     f"·{p['qi']}{who}{mark}")
    lines += ["", "**格局**"]
    for g in c["geju"]:
        lines.append(f"· {g}")
    lines += ["", f"（{c['note']}）"]
    return "\n".join(lines)


def taiyi(when: str = "") -> str:
    return format_taiyi(cast_taiyi(when))
