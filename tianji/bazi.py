"""八字（子平）排盘引擎：四柱排盘、十神、旺衰、格局、用神与文字排盘输出。"""

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

from .sxtwl_compat import (GAN, ZHI, GZ, Day, Time, _JQ_ORDER, fromSolar, fromLunar, toJD, getShiGz, getJieQiByYear)
from .sxtwl_compat import sxtwl  # noqa: F401  (兼容层自身以 sxtwl 别名被引擎引用)


GAN = "甲乙丙丁戊己庚辛壬癸"
ZHI = "子丑寅卯辰巳午未申酉戌亥"
GAN_WX = {"甲":"木","乙":"木","丙":"火","丁":"火","戊":"土","己":"土","庚":"金","辛":"金","壬":"水","癸":"水"}
ZHI_WX = {"子":"水","丑":"土","寅":"木","卯":"木","辰":"土","巳":"火","午":"火","未":"土","申":"金","酉":"金","戌":"土","亥":"水"}
GAN_YANG = set("甲丙戊庚壬")   # 阳干
# 地支藏干(主气,中气,余气)
CANG = {
    "子":["癸"], "丑":["己","癸","辛"], "寅":["甲","丙","戊"], "卯":["乙"],
    "辰":["戊","乙","癸"], "巳":["丙","庚","戊"], "午":["丁","己"], "未":["己","丁","乙"],
    "申":["庚","壬","戊"], "酉":["辛"], "戌":["戊","辛","丁"], "亥":["壬","甲"],
}
# 五行生克
SHENG = {"木":"火","火":"土","土":"金","金":"水","水":"木"}   # 我生
KE    = {"木":"土","土":"水","水":"火","火":"金","金":"木"}   # 我克
# 十二节(用于起大运, 只取节不取气)
JIE_NAMES = {"立春","惊蛰","清明","立夏","芒种","小暑","立秋","白露","寒露","立冬","大雪","小寒"}

HIDDEN_LEVELS = ("本气", "中气", "余气")
SUPPORT_DEITIES = {"比肩", "劫财", "正印", "偏印"}
OUTPUT_DEITIES = {"食神", "伤官"}
WEALTH_DEITIES = {"正财", "偏财"}
OFFICER_DEITIES = {"正官", "七杀"}
PATTERN_NAMES = {
    "正官": "正官格", "七杀": "七杀格",
    "正财": "正财格", "偏财": "偏财格",
    "正印": "正印格", "偏印": "偏印格",
    "食神": "食神格", "伤官": "伤官格",
}
JIANLU_BRANCH = {
    "甲":"寅", "乙":"卯", "丙":"巳", "丁":"午", "戊":"巳",
    "己":"午", "庚":"申", "辛":"酉", "壬":"亥", "癸":"子",
}
SEASON_BY_BRANCH = {
    **{z: "春" for z in "寅卯辰"},
    **{z: "夏" for z in "巳午未"},
    **{z: "秋" for z in "申酉戌"},
    **{z: "冬" for z in "亥子丑"},
}
STEM_COMBINATIONS = {"甲":"己", "己":"甲", "乙":"庚", "庚":"乙", "丙":"辛", "辛":"丙", "丁":"壬", "壬":"丁", "戊":"癸", "癸":"戊"}
STEM_COMBINATION_ELEMENT = {frozenset("甲己"):"土", frozenset("乙庚"):"金", frozenset("丙辛"):"水", frozenset("丁壬"):"木", frozenset("戊癸"):"火"}

BRANCH_SIX_COMBINES = {frozenset(x) for x in ("子丑", "寅亥", "卯戌", "辰酉", "巳申", "午未")}
BRANCH_SIX_CLASHES = {frozenset(x) for x in ("子午", "丑未", "寅申", "卯酉", "辰戌", "巳亥")}
BRANCH_SIX_HARMS = {frozenset(x) for x in ("子未", "丑午", "寅巳", "卯辰", "申亥", "酉戌")}
BRANCH_THREE_COMBINES = {
    frozenset("申子辰"): ("申子辰", "水"), frozenset("亥卯未"): ("亥卯未", "木"),
    frozenset("寅午戌"): ("寅午戌", "火"), frozenset("巳酉丑"): ("巳酉丑", "金"),
}
BRANCH_THREE_MEETINGS = {
    frozenset("亥子丑"): ("亥子丑", "水"), frozenset("寅卯辰"): ("寅卯辰", "木"),
    frozenset("巳午未"): ("巳午未", "火"), frozenset("申酉戌"): ("申酉戌", "金"),
}


def shishen(day_gan, other):
    """other 相对 日主 day_gan 的十神。"""
    if other == day_gan_placeholder:
        pass
    dw, ow = GAN_WX[day_gan], GAN_WX[other]
    same_pol = (day_gan in GAN_YANG) == (other in GAN_YANG)
    if dw == ow:
        return "比肩" if same_pol else "劫财"
    if SHENG[dw] == ow:            # 我生 -> 食伤
        return "食神" if same_pol else "伤官"
    if KE[dw] == ow:              # 我克 -> 财
        return "偏财" if same_pol else "正财"
    if KE[ow] == dw:              # 克我 -> 官杀
        return "七杀" if same_pol else "正官"
    return "偏印" if same_pol else "正印"   # 生我 -> 印


day_gan_placeholder = None


def gz_str(o):
    return GAN[o.tg] + ZHI[o.dz]


def equation_of_time_minutes(local_dt):
    """NOAA 近似公式计算均时差（分钟）。"""
    days_in_year = 366 if calendar.isleap(local_dt.year) else 365
    fractional_hour = local_dt.hour + local_dt.minute / 60.0 + local_dt.second / 3600.0
    gamma = 2.0 * math.pi / days_in_year * (
        local_dt.timetuple().tm_yday - 1 + (fractional_hour - 12.0) / 24.0
    )
    return 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2.0 * gamma)
        - 0.040849 * math.sin(2.0 * gamma)
    )


def solar_time_adjust(local_dt, lon, tz_offset=8.0):
    """把当地钟表时间校正为真太阳时，并保留日期跨越。

    使用 NOAA 的时间偏移公式：均时差 + 4×经度 - 60×时区。
    ``tz_offset`` 是出生时当地相对 UTC 的小时偏移；中国标准时间为 +8。
    """
    if lon is None:
        return local_dt, 0.0, 0.0
    longitude_offset = 4.0 * lon - 60.0 * tz_offset
    equation_offset = equation_of_time_minutes(local_dt)
    total_offset = longitude_offset + equation_offset
    return local_dt + timedelta(minutes=total_offset), longitude_offset, equation_offset


def calculate_ganzhi(local_dt, lon=None, tz_offset=8.0):
    """返回真太阳时、校正量与年/月/日/时干支对象。"""
    solar_dt, longitude_offset, equation_offset = solar_time_adjust(local_dt, lon, tz_offset)
    day = sxtwl.fromSolar(solar_dt.year, solar_dt.month, solar_dt.day)
    yGZ, mGZ, dGZ = day.getYearGZ(), day.getMonthGZ(), day.getDayGZ()
    # sxtwl 官方接口直接接收 0-23 小时，并在 23 时区分晚子时；不可四舍五入。
    hGZ = day.getHourGZ(solar_dt.hour)
    return solar_dt, longitude_offset, equation_offset, (yGZ, mGZ, dGZ, hGZ)


def source_element(element):
    """返回生 ``element`` 的五行。"""
    return next(k for k, v in SHENG.items() if v == element)


def controller_element(element):
    """返回克 ``element`` 的五行。"""
    return next(k for k, v in KE.items() if v == element)


def wuxing_distribution(pillars):
    """只做可复核的五行出现分布，不据此直接判旺衰。"""
    score = {"木":0.0, "火":0.0, "土":0.0, "金":0.0, "水":0.0}
    for _, g, z in pillars:
        score[GAN_WX[g]] += 1.0
        hidden = CANG[z]
        weights = [1.0] + [0.5] * (len(hidden) - 1)
        for stem, weight in zip(hidden, weights):
            score[GAN_WX[stem]] += weight
    return score


def analyze_day_master(pillars):
    """以月令为提纲，结合通根和透干给出可解释的旺衰候选。"""
    day_gan = pillars[2][1]
    day_element = GAN_WX[day_gan]
    month_branch = pillars[1][2]
    month_main = CANG[month_branch][0]
    month_deity = shishen(day_gan, month_main)

    if month_deity in {"比肩", "劫财"}:
        month_judgment, evidence_score = "得令（比劫当令）", 3.0
    elif month_deity in {"正印", "偏印"}:
        month_judgment, evidence_score = "得月令之生（印星当令）", 2.0
    elif month_deity in OUTPUT_DEITIES:
        month_judgment, evidence_score = "失令且泄身（食伤当令）", -1.75
    elif month_deity in WEALTH_DEITIES:
        month_judgment, evidence_score = "失令且耗身（财星当令）", -1.25
    else:
        month_judgment, evidence_score = "失令受制（官杀当令）", -2.5

    roots = []
    for label, _, branch in pillars:
        for index, hidden_stem in enumerate(CANG[branch]):
            if GAN_WX[hidden_stem] == day_element:
                roots.append({
                    "pillar": label, "branch": branch, "stem": hidden_stem,
                    "level": HIDDEN_LEVELS[index], "index": index,
                })
                evidence_score += (1.75, 1.0, 0.5)[index]
                break

    supportive_stems, draining_stems = [], []
    position_factor = {"年":0.8, "月":1.2, "时":1.0}
    for label, stem, _ in pillars:
        if label == "日":
            continue
        deity = shishen(day_gan, stem)
        item = {"pillar": label, "stem": stem, "deity": deity}
        factor = position_factor[label]
        if deity in SUPPORT_DEITIES:
            supportive_stems.append(item)
            evidence_score += factor * (1.0 if deity in {"比肩", "劫财"} else 0.8)
        else:
            draining_stems.append(item)
            if deity in OFFICER_DEITIES:
                evidence_score -= factor
            elif deity in OUTPUT_DEITIES:
                evidence_score -= factor * 0.75
            else:
                evidence_score -= factor * 0.65

    # 非月支只取主气作辅助证据；同类根已在上面计入，不重复计算。
    for label, _, branch in pillars:
        if label == "月":
            continue
        main_deity = shishen(day_gan, CANG[branch][0])
        if main_deity in {"正印", "偏印"}:
            evidence_score += 0.6
        elif main_deity in OFFICER_DEITIES:
            evidence_score -= 0.6
        elif main_deity in OUTPUT_DEITIES:
            evidence_score -= 0.45
        elif main_deity in WEALTH_DEITIES:
            evidence_score -= 0.35

    if evidence_score >= 3.0:
        status = "偏旺"
    elif evidence_score <= -3.0:
        status = "偏弱"
    else:
        status = "中和"
    confidence = "高" if abs(evidence_score) >= 5.0 else "中" if abs(evidence_score) >= 2.5 else "低"

    special_candidates = []
    if status == "偏弱" and not roots and not supportive_stems:
        special_candidates.append("从弱格候选（须再核对合化、制化与岁运，不能仅凭无根定从）")
    if status == "偏旺" and not draining_stems:
        special_candidates.append("专旺格候选（须再核对气势是否纯粹）")

    return {
        "day_gan": day_gan,
        "day_element": day_element,
        "month_branch": month_branch,
        "month_main": month_main,
        "month_deity": month_deity,
        "month_judgment": month_judgment,
        "roots": roots,
        "supportive_stems": supportive_stems,
        "draining_stems": draining_stems,
        "status": status,
        "confidence": confidence,
        "special_candidates": special_candidates,
    }


def analyze_pattern(pillars, day_analysis):
    """按月令藏干及透干列出常规格局候选，并标记特殊格局复核项。"""
    day_gan = day_analysis["day_gan"]
    month_branch = day_analysis["month_branch"]
    month_hidden = CANG[month_branch]
    transparent = []
    for index, stem in enumerate(month_hidden):
        positions = [label for label, visible, _ in pillars if label != "日" and visible == stem]
        if positions:
            transparent.append({
                "stem": stem, "deity": shishen(day_gan, stem),
                "level": HIDDEN_LEVELS[index], "index": index, "positions": positions,
            })

    selected = transparent[0] if transparent else {
        "stem": month_hidden[0], "deity": shishen(day_gan, month_hidden[0]),
        "level": "本气", "index": 0, "positions": [],
    }
    selected_deity = selected["deity"]
    if selected_deity in PATTERN_NAMES:
        pattern_name = PATTERN_NAMES[selected_deity]
    elif month_branch == JIANLU_BRANCH[day_gan]:
        pattern_name = "建禄格"
    else:
        pattern_name = "月劫格"

    candidates = []
    source_items = list(transparent)
    if not any(item["stem"] == month_hidden[0] for item in source_items):
        source_items.append({
            "stem": month_hidden[0], "deity": shishen(day_gan, month_hidden[0]),
            "level": "本气", "index": 0, "positions": [],
        })
    for item in source_items:
        deity = item["deity"]
        if deity in PATTERN_NAMES:
            name = PATTERN_NAMES[deity]
        elif month_branch == JIANLU_BRANCH[day_gan]:
            name = "建禄格"
        else:
            name = "月劫格"
        candidates.append({**item, "pattern": name})

    # 三合、三会若覆盖月支，可能改变月令取用；只列候选，不擅自认定成化。
    branch_set = {branch for _, _, branch in pillars}
    for relation_name, relation_map in (("三合", BRANCH_THREE_COMBINES), ("三会", BRANCH_THREE_MEETINGS)):
        for combo, (_, element) in relation_map.items():
            if combo <= branch_set and month_branch in combo:
                transformed_stem = next(
                    (stem for stem in month_hidden if GAN_WX[stem] == element),
                    next(stem for stem in GAN if GAN_WX[stem] == element),
                )
                deity = shishen(day_gan, transformed_stem)
                name = PATTERN_NAMES.get(deity, "建禄格" if month_branch == JIANLU_BRANCH[day_gan] else "月劫格")
                if not any(item["stem"] == transformed_stem and item["pattern"] == name for item in candidates):
                    candidates.append({
                        "stem": transformed_stem, "deity": deity, "level": f"{relation_name}{element}候选",
                        "index": 0, "positions": [], "pattern": name,
                    })

    special_candidates = list(day_analysis["special_candidates"])
    combining_stem = STEM_COMBINATIONS[day_gan]
    combination_positions = [
        label for label, stem, _ in pillars if label != "日" and stem == combining_stem
    ]
    if combination_positions:
        combination_element = STEM_COMBINATION_ELEMENT[frozenset((day_gan, combining_stem))]
        special_candidates.append(
            f"{day_gan}{combining_stem}合化{combination_element}候选（{combining_stem}见于{'、'.join(combination_positions)}干；须核对化神得令与有无破局）"
        )

    confidence = "高" if len(candidates) == 1 and selected["index"] == 0 and selected["positions"] else "中" if len(candidates) == 1 else "低"
    return {
        "month_hidden": [
            {"stem": stem, "deity": shishen(day_gan, stem), "level": HIDDEN_LEVELS[index]}
            for index, stem in enumerate(month_hidden)
        ],
        "transparent": transparent,
        "selected": {**selected, "pattern": pattern_name},
        "candidates": candidates,
        "confidence": confidence,
        "special_candidates": special_candidates,
    }


def analyze_branch_relations(pillars):
    """列出可客观识别的地支关系；是否成化留给格局层判断。"""
    labels = [(label, branch) for label, _, branch in pillars]
    branches = [branch for _, branch in labels]
    branch_set = set(branches)
    relations = []

    for combo, (name, element) in BRANCH_THREE_COMBINES.items():
        if combo <= branch_set:
            relations.append(f"{name}三合{element}局")
    for combo, (name, element) in BRANCH_THREE_MEETINGS.items():
        if combo <= branch_set:
            relations.append(f"{name}三会{element}方")

    for i, (left_label, left) in enumerate(labels):
        for right_label, right in labels[i + 1:]:
            pair = frozenset((left, right))
            position = f"{left_label}{left}-{right_label}{right}"
            if pair in BRANCH_SIX_COMBINES:
                relations.append(f"{position}六合")
            if pair in BRANCH_SIX_CLASHES:
                relations.append(f"{position}六冲")
            if pair in BRANCH_SIX_HARMS:
                relations.append(f"{position}相害")
            if pair == frozenset("子卯"):
                relations.append(f"{position}相刑")

    if set("寅巳申") <= branch_set:
        relations.append("寅巳申三刑")
    if set("丑未戌") <= branch_set:
        relations.append("丑未戌三刑")
    for branch in "辰午酉亥":
        if branches.count(branch) >= 2:
            relations.append(f"{branch}{branch}自刑")
    return relations


def analyze_use_gods(pillars, day_analysis, pattern_analysis):
    """分开给出格局、扶抑与调候三种口径，避免把“用神”混成一个答案。"""
    day_element = day_analysis["day_element"]
    resource = source_element(day_element)
    output = SHENG[day_element]
    wealth = KE[day_element]
    officer = controller_element(day_element)
    status = day_analysis["status"]
    selected = pattern_analysis["selected"]

    if status == "偏弱":
        has_officer_pressure = day_analysis["month_deity"] in OFFICER_DEITIES or any(
            item["deity"] in OFFICER_DEITIES for item in day_analysis["draining_stems"]
        )
        first_reason = "印星通关官杀并生身" if has_officer_pressure else "印星生扶日主"
        fuyi = [(resource, first_reason), (day_element, "比劫帮身并固根")]
    elif status == "偏旺":
        fuyi = [(output, "食伤泄秀"), (wealth, "财星耗身并承接食伤"), (officer, "官杀制身")]
    else:
        pattern_element = GAN_WX[selected["stem"]]
        fuyi = [(pattern_element, "日主近中和，优先围绕格局成败取用")]

    season = SEASON_BY_BRANCH[day_analysis["month_branch"]]
    if season == "夏":
        climate = ("水", "夏令先看润燥降温；仍须服从全局制化")
    elif season == "冬":
        climate = ("火", "冬令先看暖局解寒；仍须服从全局制化")
    else:
        climate = (None, f"{season}令不设机械调候单字，结合寒暖燥湿复核")

    return {
        "pattern_stem": selected["stem"],
        "pattern_deity": selected["deity"],
        "pattern_element": GAN_WX[selected["stem"]],
        "fuyi": fuyi,
        "climate": climate,
    }



# --- 节气辅助 ---
_JQ_ORDER = ["冬至","小寒","大寒","立春","雨水","惊蛰","春分","清明","谷雨","立夏","小满","芒种",
             "夏至","小暑","大暑","立秋","处暑","白露","秋分","寒露","霜降","立冬","小雪","大雪"]

def _jq_name(i):
    try:
        return _JQ_ORDER[int(i) % 24]
    except Exception:
        return str(i)

def _days_to_jie(y, m, d, hh, mm, forward):
    """生日到 顺行下一节 / 逆行上一节 的天数。"""
    t = sxtwl.Time(); t.Y, t.M, t.D = y, m, d; t.h, t.m, t.s = hh, mm, 0
    bjd = sxtwl.toJD(t)
    jies = []
    for yy in (y - 1, y, y + 1):
        for info in sxtwl.getJieQiByYear(yy):
            nm = _jq_name(info.jqIndex)
            if nm in JIE_NAMES:
                jies.append((info.jd, nm))
    jies.sort()
    if forward:
        nxt = [jd for jd, nm in jies if jd > bjd]
        return (nxt[0] - bjd) if nxt else 0.0
    else:
        prv = [jd for jd, nm in jies if jd < bjd]
        return (bjd - prv[-1]) if prv else 0.0





# ======================= 出生信息解析 + 排盘封装 =======================

WUXING_ORDER = ["木", "火", "土", "金", "水"]

# ---------------------------------------------------------------- 错误类型


class BaziError(Exception):
    """用户输入问题或引擎不可用, message 可直接回复给用户。"""


# ---------------------------------------------------------------- 出生信息


@dataclass
class BirthInfo:
    year: int
    month: int
    day: int
    hour: int
    minute: int
    gender: str                 # 男 / 女
    city: Optional[str] = None
    longitude: Optional[float] = None   # 东经为正, None 表示不做真太阳时校正
    tz_offset: float = 8.0
    is_lunar: bool = False
    lunar_desc: Optional[str] = None    # 农历原文, 用于回显


# 常见城市经度表(东经). 用于真太阳时校正; 查不到的城市按标准时间排盘。
CITY_LONGITUDE = {
    "北京": 116.4, "上海": 121.5, "天津": 117.2, "重庆": 106.5,
    "哈尔滨": 126.6, "长春": 125.3, "沈阳": 123.4, "大连": 121.6,
    "石家庄": 114.5, "唐山": 118.2, "秦皇岛": 119.6, "保定": 115.5,
    "太原": 112.5, "济南": 117.0, "青岛": 120.4, "烟台": 121.4,
    "郑州": 113.6, "洛阳": 112.4, "合肥": 117.3, "南京": 118.8,
    "苏州": 120.6, "无锡": 120.3, "常州": 119.9, "南通": 120.9,
    "扬州": 119.4, "徐州": 117.2, "杭州": 120.2, "宁波": 121.6,
    "温州": 120.7, "绍兴": 120.6, "嘉兴": 120.8, "金华": 119.7,
    "台州": 121.4, "湖州": 120.1, "福州": 119.3, "厦门": 118.1,
    "泉州": 118.6, "南昌": 115.9, "九江": 116.0, "赣州": 114.9,
    "武汉": 114.3, "长沙": 113.0, "宜昌": 111.3, "岳阳": 113.1,
    "广州": 113.3, "深圳": 114.1, "珠海": 113.6, "汕头": 116.7,
    "湛江": 110.3, "南宁": 108.4, "桂林": 110.3, "柳州": 109.4,
    "海口": 110.3, "三亚": 109.5, "成都": 104.0, "绵阳": 104.7,
    "贵阳": 106.6, "昆明": 102.7, "大理": 100.2, "丽江": 100.2,
    "西安": 108.9, "宝鸡": 107.1, "兰州": 103.8, "天水": 105.7,
    "西宁": 101.8, "银川": 106.3, "乌鲁木齐": 87.6, "喀什": 75.9,
    "拉萨": 91.1, "呼和浩特": 111.7, "包头": 109.8, "鄂尔多斯": 109.8,
    "香港": 114.2, "澳门": 113.5,
}

# ---------------------------------------------------------------- 解析工具

CN_NUM = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
          "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}

PERIOD_AFTERNOON = {"下午", "午后", "傍晚", "晚上", "夜里", "夜间", "晚", "夜"}
PERIOD_NIGHT = {"晚上", "夜里", "夜间", "晚", "夜"}
PERIOD_MORNING = {"凌晨", "早上", "早晨", "清晨", "上午", "早", "晨"}

# 时辰 -> 该时辰的起始小时
SHICHEN = {
    "子时": 0, "丑时": 1, "寅时": 3, "卯时": 5, "辰时": 7, "巳时": 9,
    "午时": 11, "未时": 13, "申时": 15, "酉时": 17, "戌时": 19, "亥时": 21,
}
SHICHEN_SPECIAL = {"早子时": 0, "晚子时": 23, "子夜": 23}


def _cn_to_int(s: str) -> int:
    """中文小写数字 -> int, 支持 0-99: 十 / 十一 / 二十 / 二十三 / 三十。"""
    s = s.strip()
    if not s:
        raise BaziError("数字识别失败")
    if s.isdigit():
        return int(s)
    if s == "十":
        return 10
    total, section = 0, 0
    for ch in s:
        if ch in CN_NUM:
            section = CN_NUM[ch]
        elif ch == "十":
            section = (section or 1) * 10
            total += section
            section = 0
        else:
            raise BaziError(f"无法识别的数字: {s}")
    return total + section


def _validate_hm(hour: int, minute: int) -> Tuple[int, int]:
    if not (0 <= hour <= 23):
        raise BaziError(f"小时 {hour} 超出范围(0-23)")
    if not (0 <= minute <= 59):
        raise BaziError(f"分钟 {minute} 超出范围(0-59)")
    return hour, minute


def _parse_time(text: str) -> Tuple[int, int]:
    """从文本中解析出生时刻, 返回 (hour, minute)。"""
    # 去空格版本(供时辰/点 分支使用, 处理 "下午 3 点半" 这类带空格写法)
    text_ns = text.replace("：", ":").replace(" ", "")
    # HH:MM 必须在保留空格的原文里匹配, 否则 "1990-02-04 8:00" 会被拼成
    # "1990-02-048:00" 而误把 "48:00" 当成时分。
    text_colon = text.replace("：", ":")
    # 1) 早/晚子时等特殊时辰
    for name, h in SHICHEN_SPECIAL.items():
        if name in text_ns:
            return h, 0
    # 2) 普通时辰(午时/申时...)
    for name, h in SHICHEN.items():
        if name in text_ns:
            return h, 0
    # 3) HH:MM
    m = re.search(r"(\d{1,2})\s*:\s*(\d{1,2})", text_colon)
    if m:
        return _validate_hm(int(m.group(1)), int(m.group(2)))
    # 4) 下午3点半 / 3点30分 / 15点 / 十点
    m = re.search(
        r"(凌晨|早上|早晨|清晨|上午|中午|下午|午后|傍晚|晚上|夜里|夜间|晚|夜)?"
        r"(\d{1,2}|[零〇一二两三四五六七八九十]+)点"
        r"(半|(\d{1,2}|[零〇一二两三四五六七八九十]+)分?)?",
        text_ns,
    )
    if m:
        period, h_raw, half, min_raw = m.groups()
        hour = _cn_to_int(h_raw)
        minute = 30 if half else (_cn_to_int(min_raw) if min_raw else 0)
        if period in PERIOD_AFTERNOON:
            if hour < 12:
                hour += 12
            elif hour == 12 and period in PERIOD_NIGHT:
                hour = 0  # 晚上12点 -> 次日0点
        elif period in PERIOD_MORNING and hour == 12:
            hour = 0  # 凌晨12点 -> 0点
        return _validate_hm(hour, minute)
    raise BaziError("无法识别出生时间, 请使用如 14:30、下午3点半、申时 的格式")


def _cn_month(s: str) -> int:
    s = s.strip()
    if s.startswith("正"):
        return 1
    if s.startswith("冬"):
        return 11
    if s.startswith("腊"):
        return 12
    month = _cn_to_int(s)
    if not (1 <= month <= 12):
        raise BaziError(f"农历月份无效: {s}月")
    return month


def _cn_day(s: str) -> int:
    s = s.strip().rstrip("日号")
    if not s:
        raise BaziError("农历日期识别失败")
    if s.startswith("初"):
        return _cn_to_int(s[1:])
    if s.startswith("三十"):
        return 30
    if s.startswith("廿"):
        return 20 + _cn_to_int(s[1:])
    if s.startswith("二十"):
        return 20 + (_cn_to_int(s[2:]) if len(s) > 2 else 0)
    if s.startswith("十"):
        return 10 + (_cn_to_int(s[1:]) if len(s) > 1 else 10)
    day = _cn_to_int(s)
    if not (1 <= day <= 30):
        raise BaziError(f"农历日期无效: {s}")
    return day


def _parse_gender(text: str) -> Optional[str]:
    low = text.lower()
    for kw, g in (("乾造", "男"), ("坤造", "女"), ("男性", "男"), ("女性", "女"),
                  ("男生", "男"), ("女生", "女"), ("男孩", "男"), ("女孩", "女"),
                  ("男的", "男"), ("女的", "女"), ("男", "男"), ("女", "女"),
                  ("male", "男"), ("female", "女")):
        if kw in low:
            return g
    return None


def _parse_city(text: str) -> Tuple[Optional[str], Optional[float]]:
    best = None
    for name, lon in CITY_LONGITUDE.items():
        if name in text and (best is None or len(name) > len(best[0])):
            best = (name, lon)
    return best if best else (None, None)


def _lunar_to_solar(year: int, month: int, day: int, is_leap: bool) -> Tuple[int, int, int]:
    """农历 -> 公历, 借助 sxtwl。"""
    if not (1900 <= year <= 2100):
        raise BaziError("农历排盘目前支持 1900-2100 年, 超出范围请用公历")
    try:
        import sxtwl
        lunar = sxtwl.fromLunar(year, month, day, is_leap)
        return lunar.getSolarYear(), lunar.getSolarMonth(), lunar.getSolarDay()
    except BaziError:
        raise
    except Exception as exc:
        raise BaziError(f"农历日期转换失败: {exc}")


def parse_birth_info(text: str) -> BirthInfo:
    """把 '1990-05-20 14:30 男 北京' / '农历1990年四月初三 下午3点半 女' 解析成 BirthInfo。"""
    text = (text or "").strip()
    if not text:
        raise BaziError("请提供出生信息, 例如: 八字 1990-05-20 14:30 男 北京")

    is_lunar = any(k in text for k in ("农历", "阴历", "夏历"))
    lunar_desc = None
    if is_lunar:
        m = re.search(
            r"(\d{4})\s*年\s*(闰?)([正一二三四五六七八九十冬腊]+)\s*月\s*([初一二三四五六七八九十廿]+)\s*[日号]?",
            text,
        )
        if not m:
            raise BaziError("无法识别农历生日, 请使用如 农历1990年四月初三 的格式")
        ly, leap, lmonth, lday = int(m.group(1)), m.group(2) == "闰", m.group(3), m.group(4)
        lunar_month = _cn_month(lmonth)
        lunar_day = _cn_day(lday)
        lunar_desc = f"农历{ly}年{'闰' if leap else ''}{lmonth}月{lday}"
        year, month, day = _lunar_to_solar(ly, lunar_month, lunar_day, leap)
    else:
        m = re.search(r"(\d{4})\s*[-/年.]\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})\s*日?", text)
        if not m:
            raise BaziError("无法识别出生日期, 请使用如 1990-05-20 或 1990年5月20日 的格式")
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            datetime(year, month, day)
        except ValueError:
            raise BaziError(f"日期无效: {year}-{month}-{day}")
        if not (1900 <= year <= 2100):
            raise BaziError("出生年份请控制在 1900-2100 之间")

    hour, minute = _parse_time(text)
    gender = _parse_gender(text)
    if gender is None:
        raise BaziError("请说明性别(男/女), 例如: 八字 1990-05-20 14:30 男")
    city, longitude = _parse_city(text)

    return BirthInfo(
        year=year, month=month, day=day, hour=hour, minute=minute,
        gender=gender, city=city, longitude=longitude,
        is_lunar=is_lunar, lunar_desc=lunar_desc,
    )


# ---------------------------------------------------------------- 排盘


def cast_chart(birth: BirthInfo) -> dict:
    """调用开源引擎排盘, 返回结构化命盘(供渲染层使用)。"""
    local_dt = datetime(birth.year, birth.month, birth.day, birth.hour, birth.minute)
    try:
        solar_dt, lon_off, eq_off, (yGZ, mGZ, dGZ, hGZ) = calculate_ganzhi(
            local_dt, birth.longitude, birth.tz_offset
        )
    except Exception as exc:
        raise BaziError(f"排盘计算失败: {exc}")

    day_gan = GAN[dGZ.tg]
    raw_pillars = [
        ("年", GAN[yGZ.tg], ZHI[yGZ.dz]),
        ("月", GAN[mGZ.tg], ZHI[mGZ.dz]),
        ("日", GAN[dGZ.tg], ZHI[dGZ.dz]),
        ("时", GAN[hGZ.tg], ZHI[hGZ.dz]),
    ]

    pillars: List[dict] = []
    for label, gan, zhi in raw_pillars:
        hidden = [
            {"stem": stem, "deity": shishen(day_gan, stem), "level": HIDDEN_LEVELS[i]}
            for i, stem in enumerate(CANG[zhi])
        ]
        pillars.append({
            "label": label,
            "gan": gan,
            "zhi": zhi,
            "gan_deity": "日主" if label == "日" else shishen(day_gan, gan),
            "zhi_deity": shishen(day_gan, CANG[zhi][0]),
            "hidden": hidden,
        })

    day_analysis = analyze_day_master(raw_pillars)
    pattern_analysis = analyze_pattern(raw_pillars, day_analysis)
    relations = analyze_branch_relations(raw_pillars)
    use_gods = analyze_use_gods(raw_pillars, day_analysis, pattern_analysis)
    wuxing = wuxing_distribution(raw_pillars)

    # 起大运: 阳男阴女顺行, 阴男阳女逆行; 天数 ÷3 得起运岁数
    yang_year = GAN[yGZ.tg] in GAN_YANG
    forward = (yang_year and birth.gender == "男") or (not yang_year and birth.gender == "女")
    days_to = _days_to_jie(birth.year, birth.month, birth.day, birth.hour, birth.minute, forward)
    start_age = days_to / 3.0
    yrs = int(start_age)
    mos = int(round((start_age - yrs) * 12))
    if mos >= 12:
        yrs, mos = yrs + 1, mos - 12

    seq, idx_g, idx_z = [], mGZ.tg, mGZ.dz
    step = 1 if forward else -1
    for _ in range(8):
        idx_g = (idx_g + step) % 10
        idx_z = (idx_z + step) % 12
        seq.append(GAN[idx_g] + ZHI[idx_z])
    dayun = [
        {"age": yrs + 10 * i, "ganzhi": gz, "deity": shishen(day_gan, gz[0])}
        for i, gz in enumerate(seq)
    ]

    return {
        "birth": {
            "solar": f"{birth.year}-{birth.month:02d}-{birth.day:02d} "
                     f"{birth.hour:02d}:{birth.minute:02d}",
            "gender": birth.gender,
            "city": birth.city,
            "longitude": birth.longitude,
            "is_lunar": birth.is_lunar,
            "lunar_desc": birth.lunar_desc,
            "solar_corrected": solar_dt,
            "longitude_offset": lon_off,
            "equation_offset": eq_off,
            "corrected": birth.longitude is not None,
        },
        "pillars": pillars,
        "wuxing": wuxing,
        "day_master": day_analysis,
        "pattern": pattern_analysis,
        "relations": relations,
        "use_gods": use_gods,
        "dayun": {
            "forward": forward,
            "yang_year": yang_year,
            "days_to_jie": days_to,
            "start_age_years": yrs,
            "start_age_months": mos,
            "list": dayun,
        },
    }


# ----------------------------------------------------------------  文字摘要(图片失败时回退)


def format_text(chart: dict) -> str:
    """把命盘结构化成一段便于在 QQ 群发的文字摘要。"""
    birth = chart["birth"]
    pillars = chart["pillars"]
    four = " ".join(f"{p['gan']}{p['zhi']}" for p in pillars)
    lines = [
        f"公历 {birth['solar']}　{birth['gender']}",
        f"四柱: {four}",
        f"日主 {chart['day_master']['day_gan']}({chart['day_master']['day_element']})　{chart['day_master']['status']}　置信度 {chart['day_master']['confidence']}",
        f"格局: {chart['pattern']['selected']['pattern']}",
        f"起运 {chart['dayun']['start_age_years']}岁{chart['dayun']['start_age_months']}月　{'顺' if chart['dayun']['forward'] else '逆'}排",
        "大运: " + " ".join(f"{d['age']}岁{d['ganzhi']}" for d in chart["dayun"]["list"][:6]),
        "※ 仅供传统文化参考，不构成医疗/投资/婚恋建议。",
    ]
    return "\n".join(lines)


# ----------------------------------------------------------------  CLI 自测
