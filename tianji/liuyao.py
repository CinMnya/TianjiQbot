"""六爻纳甲：装卦、六亲、世应与文本排盘。"""

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
from .xiaoliuren import _split_tokens
from .gua import gua_from_yao, gua_info, najia, BAGUA_YAO
from .bazi import ZHI_WX, GAN_WX
from .meihua import _SHENG, _KE


# ---------------------------------------------------------------------------
# 六爻（纳甲装卦）
# ---------------------------------------------------------------------------
_LIU_SHEN = ["青龙", "朱雀", "勾陈", "螣蛇", "白虎", "玄武"]
# 六神按日干起: 甲乙青龙、丙丁朱雀、戊勾陈、己螣蛇、庚辛白虎、壬癸玄武
_LS_START = {"甲": 0, "乙": 0, "丙": 1, "丁": 1, "戊": 2,
             "己": 3, "庚": 4, "辛": 4, "壬": 5, "癸": 5}
_YAO_POS = ["初", "二", "三", "四", "五", "上"]
# 动爻通用提示（爻位 -> 提示）
_YAO_TIP = {
    0: "事之始，根基未稳，宜缓图不宜急进",
    1: "内卦之中，多主家宅与自身内部事务",
    2: "内卦之末，进退交界，防过犹不及",
    3: "外卦之初，出门与外务起步，宜先立信",
    4: "外卦之中，主事之位，得中宜守正",
    5: "事之终，收尾防亢，见好即收",
}


def _liuqin(gong_wx: str, zhi: str) -> str:
    """以卦宫五行为「我」，配该爻地支的六亲。"""
    wx = ZHI_WX[zhi]
    if wx == gong_wx:
        return "兄弟"
    if _SHENG[gong_wx] == wx:
        return "子孙"
    if _KE[gong_wx] == wx:
        return "妻财"
    if _KE[wx] == gong_wx:
        return "官鬼"
    return "父母"


def _yao_name(idx: int, yang: bool) -> str:
    """爻位名: 初九/初六、九二/六二 … 上九/上六。"""
    num = "九" if yang else "六"
    if idx == 0:
        return f"初{num}"
    if idx == 5:
        return f"上{num}"
    return f"{num}{_YAO_POS[idx]}"


def _coins_to_value(tok: str) -> int:
    """一组铜钱(三枚) -> 6/7/8/9。正=阳面。"""
    t = (tok.replace("字", "正").replace("背", "反")
            .replace("阳", "正").replace("阴", "反"))
    n = t.count("正")
    if n == 0:
        return 6      # 三反 · 老阴(动)
    if n == 1:
        return 7      # 一正二反 · 少阳
    if n == 2:
        return 8      # 二正一反 · 少阴
    return 9          # 三正 · 老阳(动)


def _time_gua(dt: datetime):
    """时间起卦(六爻式): 年支+农历月+日 定上卦, 再加时支定下卦与动爻。"""
    lunar = Solar.fromDate(dt).getLunar()
    year_zhi = ZHI.index(lunar.getYearZhi())
    month = abs(lunar.getMonth())
    day = lunar.getDay()
    hour_zhi = ((dt.hour + 1) // 2) % 12
    up_num = (year_zhi + 1 + month + day) % 8 or 8
    low_num = (year_zhi + 1 + month + day + hour_zhi + 1) % 8 or 8
    dong = (year_zhi + 1 + month + day + hour_zhi + 1) % 6 or 6
    return up_num, low_num, dong, f"农历{month}月{day}日 {ZHI[hour_zhi]}时"


_NUM_TRIGRAM = {1: "乾", 2: "兑", 3: "离", 4: "震", 5: "巽", 6: "坎", 7: "艮", 8: "坤"}
_GUA_SYMBOLS = {"乾": "☰", "兑": "☱", "离": "☲", "震": "☳",
                "巽": "☴", "坎": "☵", "艮": "☶", "坤": "☷"}


def liuyao_toss() -> tuple:
    """模拟摇一次铜钱(三枚)，返回 (6-9 的数, 正面数, 三枚正反描述)。

    传统以「有字一面」为阳：三正=老阳9、二正=少阴8、一正=少阳7、三反=老阴6。
    """
    faces = []
    for _ in range(3):
        faces.append("正" if random.random() < 0.5 else "反")
    n_pos = faces.count("正")
    desc = "".join(faces)
    return 6 + n_pos, n_pos, desc


def _yao_kind(value: int) -> str:
    return {6: "老阴(动)", 7: "少阳", 8: "少阴", 9: "老阳(动)"}.get(value, "—")


def _yao_bar(value: int) -> str:
    return "▅▅▅▅▅" if value in (7, 9) else "▅▅　▅▅"


def liuyao_cast(values, dt: datetime | None = None, src: str = "手工六爻") -> dict:
    """六爻装卦(结构化)。values 为自初爻起的 6 个 6-9 整数。"""
    dt = dt or datetime.now()
    values = [int(v) for v in list(values)[:6]]
    if len(values) != 6 or any(v not in (6, 7, 8, 9) for v in values):
        raise ValueError("六爻需要 6 个 6-9 的爻值")

    yaos = [v in (7, 9) for v in values]
    dongs = [i for i, v in enumerate(values) if v in (6, 9)]
    ben_name = gua_from_yao([1 if v else 0 for v in yaos])
    bian_yaos = [not v if i in dongs else v for i, v in enumerate(yaos)]
    bian_name = gua_from_yao([1 if v else 0 for v in bian_yaos])
    ben, bian = gua_info(ben_name), gua_info(bian_name)

    try:
        lunar = Solar.fromYmdHms(dt.year, dt.month, dt.day,
                                 dt.hour, dt.minute, 0).getLunar()
        y_gz, m_gz = lunar.getYearInGanZhi(), lunar.getMonthInGanZhi()
        d_gz, h_gz = lunar.getDayInGanZhi(), lunar.getTimeInGanZhi()
    except Exception:
        y_gz = m_gz = d_gz = h_gz = ""

    gong_wx = ben["palace_wx"]
    ben_nj = najia(ben_name)
    bian_nj = najia(bian_name)
    liuqin = [_liuqin(gong_wx, ben_nj[i][1][1]) for i in range(6)]

    return {
        "values": values,
        "yaos": yaos,
        "dongs": dongs,
        "ben_name": ben_name,
        "bian_name": bian_name,
        "ben": ben,
        "bian": bian,
        "gong_wx": gong_wx,
        "ben_nj": ben_nj,
        "bian_nj": bian_nj,
        "liuqin": liuqin,
        "shi": ben["shi"],
        "ying": ben["ying"],
        "day_gan": d_gz[0] if d_gz else "甲",
        "day_gz": d_gz,
        "month_gz": m_gz,
        "year_gz": y_gz,
        "hour_gz": h_gz,
        "month_wx": ZHI_WX.get(m_gz[1], "") if len(m_gz) >= 2 else "",
        "day_wx": ZHI_WX.get(d_gz[1], "") if len(d_gz) >= 2 else "",
        "day_gan_wx": GAN_WX.get(d_gz[0], "") if d_gz else "",
        "dt": dt,
        "src": src,
    }


def format_liuyao(d: dict) -> str:
    """把 liuyao_cast 的结果排成文字卦盘。"""
    dt = d["dt"]
    yaos, dongs = d["yaos"], d["dongs"]
    ben_name, bian_name = d["ben_name"], d["bian_name"]
    ben, bian = d["ben"], d["bian"]
    gong_wx = d["gong_wx"]
    ben_nj, bian_nj = d["ben_nj"], d["bian_nj"]
    ls0 = _LS_START.get(d["day_gan"], 0)

    lines = [
        f"【六爻 · {ben_name} 之 {bian_name}】"
        if dongs else f"【六爻 · {ben_name}（六爻安静）】",
        f"起卦：{d['src']}",
        f"　　{dt.strftime('%Y-%m-%d %H:%M')}"
        f"（{d['year_gz']}年 {d['month_gz']}月 {d['day_gz']}日 {d['hour_gz']}时）",
        f"本卦：{ben_name}（{ben['palace']}宫·{gong_wx}）"
        + (f"｜变卦：{bian_name}（{bian['palace']}宫·{bian['palace_wx']}）" if dongs else ""),
        f"动爻：{'、'.join(_yao_name(i, yaos[i]) for i in dongs)}" if dongs else "动爻：无",
        "────────────────",
        "六神　六亲　爻位　纳甲　卦爻",
    ]
    for i in range(5, -1, -1):
        _pos, gz, _yang = ben_nj[i]
        shen = _LIU_SHEN[(ls0 + i) % 6]
        shi = "世" if ben["shi"] == i + 1 else ("应" if ben["ying"] == i + 1 else "　")
        row = (f"{shen}　{_liuqin(gong_wx, gz[1])}　{_yao_name(i, yaos[i])}　"
               f"{gz}　{_yao_bar(d['values'][i])} {shi}")
        if i in dongs:
            _b, bgz, _bb = bian_nj[i]
            row += f" ○→ {bgz} {_liuqin(gong_wx, bgz[1])}"
        lines.append(row)

    lines.append("────────────────")
    lines.append(f"卦意：{ben['meaning']}")
    if dongs:
        lines.append("动爻提示：" + "；".join(_YAO_TIP[i] for i in dongs))
        if bian_name != ben_name:
            lines.append(f"变卦意：{bian['meaning']}")
    else:
        lines.append("动爻提示：六爻安静，事态暂无明显变数，宜守现状再看后续。")

    count = {}
    for q in d["liuqin"]:
        count[q] = count.get(q, 0) + 1
    order = ["父母", "兄弟", "子孙", "妻财", "官鬼"]
    lines.append("六亲分布：" + "、".join(f"{q}×{count[q]}" for q in order if q in count)
                 + "；" + "、".join(f"缺{q}" for q in order if q not in count))
    return "\n".join(lines)


def liuyao_from_arg(arg: str = "") -> dict:
    """把参数解析成结构化卦（六组铜钱 / 六个 6-9 数字 / 日期时间 / 日期+卦值）。

    解析不出六爻格式时抛 ValueError —— 绝不退化成「时间起卦」，
    这样用户输入的问题才不会被误当成起卦指令。
    """
    arg = (arg or "").strip()
    now = datetime.now()
    dt = now
    values = None
    src = ""

    # 1) 日期时间
    m = re.search(r"(\d{4})\s*[-/年.]\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})", arg)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hm = re.search(r"(\d{1,2})\s*[:：]\s*(\d{1,2})", arg)
        hh, mi = (int(hm.group(1)), int(hm.group(2))) if hm else (now.hour, now.minute)
        if not (0 <= hh <= 23 and 0 <= mi <= 59):
            raise ValueError("时间超出范围")
        dt = datetime(y, mo, d, hh, mi)
        src = f"{y}-{mo:02d}-{d:02d} {hh:02d}:{mi:02d}"
        arg = arg.replace(m.group(0), "").strip()

    # 2) 六个铜钱组 / 六个 6-9 数字
    tokens = _split_tokens(arg)
    if len(tokens) >= 6:
        try:
            nums = [int(t) for t in tokens[:6]]
            if all(n in (6, 7, 8, 9) for n in nums):
                values = nums
            else:
                raise ValueError
        except ValueError:
            values = [_coins_to_value(t) for t in tokens[:6]]
        src = (src + " · 手动六爻") if src else "手动六爻"

    if values is None and not src:
        raise ValueError("不是六爻格式")

    if values is None:
        # 只给了日期时间 -> 用该时刻时间起卦
        up_num, low_num, dong, note = _time_gua(dt)
        low_yaos = list(BAGUA_YAO[_NUM_TRIGRAM[low_num]])
        up_yaos = list(BAGUA_YAO[_NUM_TRIGRAM[up_num]])
        yaos = [bool(v) for v in low_yaos + up_yaos]
        values = [9 if (v and i == dong - 1) else (7 if v else (6 if i == dong - 1 else 8))
                  for i, v in enumerate(yaos)]
        src = f"{src} · 时间起卦（{note}）"

    return liuyao_cast(values, dt, src)


def liuyao(arg: str = "", strict: bool = False) -> str:
    """六爻起卦 + 纳甲装卦。支持: 六组铜钱 / 六个 6-9 数字 / 日期时间 / 默认现在。

    strict=True 时, 参数既不是六爻格式也不是时间格式就抛 ValueError,
    不退化成「时间起卦」——避免用户输入的问题被误当成起卦指令。
    """
    text = (arg or "").strip()
    if text:
        try:
            d = liuyao_from_arg(text)
        except ValueError:
            if strict:
                raise
            d = liuyao_auto()          # 旧行为: 解析不出就按当前时间起卦
    else:
        d = liuyao_auto()

    lines = format_liuyao(d).split("\n")
    lines.append("※ 六爻须结合用神取用、月日生克与旬空冲合；这里给出卦象与装卦结构，"
                 "吉凶倾向见下方本地解读。")
    lines.append("※ 一事一占，同一件事不要反复起卦。")
    return "\n".join(lines)


def liuyao_auto(dt: datetime | None = None) -> dict:
    """时间起卦(结构化), 供互动流程复用。"""
    dt = dt or datetime.now()
    up_num, low_num, dong, note = _time_gua(dt)
    up, low = _NUM_TRIGRAM[up_num], _NUM_TRIGRAM[low_num]
    yaos = [bool(v) for v in (list(BAGUA_YAO[low]) + list(BAGUA_YAO[up]))]
    values = [9 if (v and i == dong - 1) else (7 if v else (6 if i == dong - 1 else 8))
              for i, v in enumerate(yaos)]
    return liuyao_cast(values, dt, f"时间起卦（{note}）")


def liuyao_panel(sess: dict) -> str:
    """摇卦互动面板文字。sess: {question, values}。"""
    values = sess.get("values") or []
    q = (sess.get("question") or "").strip()
    n = len(values)
    lines = [
        "【六爻 · 摇卦】",
        f"问题：{q or '（还没输入，先点「输入问题」）'}",
        f"进度：已摇 {n} / 6 爻",
        "────────────────",
    ]
    for i in range(6):
        if i < n:
            v = values[i]
            lines.append(f"{_yao_name(i, v in (7, 9))}　{_yao_bar(v)}　{_yao_kind(v)}")
        else:
            lines.append(f"{_YAO_POS[i]}爻　· · ·　未摇")
    lines.append("────────────────")
    if n < 6:
        lines.append("点「摇铜钱」摇下一爻，六爻齐了点「起卦」喵～")
    else:
        lines.append("六爻已成，点「起卦」看结果喵～")
    lines.append("※ 心中默念所问之事，一事一占。")
    return "\n".join(lines)
