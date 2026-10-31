"""本地 AI 解读（离线规则引擎）：对排盘文本做传统文化解读，不联网。"""

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


AI_HEAD = "## 本地 AI 解读"
AI_FOOT = "> 离线规则引擎生成，不联网、无外部大模型参与；仅供传统文化参考。"

# ---------------------------------------------------------------- 基础知识表
_WX = {
    "木": ("生长、直率、爱计划", "教育、内容、成长型行业",
           "说话太直，容易不留余地", "肝胆、眼目、筋络"),
    "火": ("热忱、外放、心思快", "传播、销售、表演，以及需要曝光的岗位",
           "沉不住气，热度来得快去得也快", "心血管与睡眠"),
    "土": ("稳、厚、扛得住", "运营、行政、地产、供应链等需要耐心的岗位",
           "容易过度承担，不太会拒绝", "脾胃与肌肉"),
    "金": ("果决、重规则、有分寸", "金融、法务、工程、管理",
           "太讲效率，容易显得冷硬", "肺与呼吸道、皮肤"),
    "水": ("灵活、善观察、想得多", "研究、策略、贸易，以及需要应变的岗位",
           "想得比做得多，容易内耗", "肾与泌尿、耳"),
}

_WX_SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
_WX_KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
_WX_BEI_SHENG = {v: k for k, v in _WX_SHENG.items()}
_WX_BEI_KE = {v: k for k, v in _WX_KE.items()}

_DIR_WX = {"东": "木", "南": "火", "西": "金", "北": "水", "中": "土",
           "东南": "木", "正东": "木", "正南": "火", "正西": "金", "正北": "水",
           "东北": "土", "西南": "土", "西北": "金"}

_SHISHEN = {
    "比肩": "自立与同辈并肩，看重公平，也容易在分账、分工上起摩擦",
    "劫财": "敢抢敢上，朋友多，但破财往往也来自人情与合伙",
    "食神": "会表达、懂享受，靠手艺与口碑吃饭，日子过得松弛",
    "伤官": "聪明外露、点子多，不喜被管；锋芒要收，才走得更远",
    "正财": "踏实攒钱，重视稳定收入，钱来得慢但守得住",
    "偏财": "机会嗅觉灵，敢博一把，起伏也大，宜留后手",
    "正官": "守规矩、有责任感，适合在体系里靠资历往上走",
    "七杀": "压力感强、抗压强，敢啃硬骨头，但容易把自己逼太紧",
    "正印": "重学习与庇护，靠专业与文凭立身，慢热但后劲足",
    "偏印": "想法偏门、悟性高，适合技术或冷门领域，易孤",
}

_ZW_STAR = {
    "紫微": ("尊贵、要面子、天生想主导", "管理、统筹、需要拍板的位置"),
    "天机": ("机敏、多思、爱策划", "策略、咨询、技术、需要动脑的活"),
    "太阳": ("热忱、爱付出、怕被无视", "对外、公关、教育、需要露脸的岗位"),
    "武曲": ("果决、务实、重执行", "财务、工程、销售，讲结果的地方"),
    "天同": ("温和、重享受、怕压力", "服务、福利、稳定型岗位更顺手"),
    "廉贞": ("有个性、爱憎分明、敢闯", "业务、创意、需要魄力的方向"),
    "天府": ("稳重、会过日子、能守", "管理、财会、后勤与资源调配"),
    "太阴": ("细腻、内敛、重情感", "设计、内容、财务、需要耐心的细活"),
    "贪狼": ("多才多艺、欲望强、爱交际", "娱乐、营销、多元经营"),
    "巨门": ("善辩、口才佳、易起口舌", "法律、教学、谈单、需要说话的职业"),
    "天相": ("重情面、讲形象、善辅助", "协调、行政、助理与对外服务"),
    "天梁": ("老成、爱照顾人、清高", "医疗、教育、顾问、监督类岗位"),
    "七杀": ("冲劲足、敢独断、能扛事", "创业、开拓、需要打硬仗的场合"),
    "破军": ("破旧立新、变动大、敢舍", "转型、改革、从零搭台的活"),
}

_ZW_BAD = {
    "擎羊": "容易硬碰硬，冲动时先停三秒",
    "陀罗": "事情容易拖，给自己定死线",
    "火星": "脾气上来得快，事后容易后悔",
    "铃星": "心里憋着不说，久了会内耗",
    "地空": "想得很多但抓不实，多落地少空想",
    "地劫": "钱与精力容易漏，做好预算",
    "天刑": "讲原则是好事，别太较真",
    "天姚": "人缘好但也招是非，边界要清楚",
}

_LY_LIUQIN = {
    "父母": ("文书、学业、合同、房子、长辈", "文件、审批、长辈意见是这事的关节"),
    "兄弟": ("同辈、竞争、朋友、合伙", "竞争者与身边人是这卦的变量"),
    "子孙": ("子女、健康、福气、解忧、宠物", "轻松与否、能不能松口气，看这一头"),
    "妻财": ("钱财、物品、收益、妻子（男问）", "钱与实物、以及可支配的资源是重点"),
    "官鬼": ("工作、职位、官非、疾病、丈夫（女问）", "压力、责任与外部规则是重点"),
}

_LY_TOPIC = {
    "父母": "考试、文书、审批这一类事",
    "妻财": "钱、收益、实物这一类事",
    "官鬼": "工作、职位、压力与规则这一类事",
    "子孙": "健康、子女、解忧这一类事",
    "兄弟": "朋友、竞争、合作这一类事",
}

_LY_KW = [
    ("父母", ("考", "学", "试", "证", "论文", "合同", "房", "资料", "文书", "签", "文件", "批", "通知")),
    ("妻财", ("财", "钱", "赚", "生意", "投资", "工资", "薪", "买", "卖", "业绩", "收入", "债", "回款", "订单")),
    ("官鬼", ("工作", "职", "升", "面试", "事业", "老板", "领导", "官", "纠纷", "病", "男", "老公", "丈夫", "考编")),
    ("子孙", ("健康", "身体", "医", "药", "孩子", "子女", "怀孕", "宠物", "平安", "手术")),
    ("兄弟", ("朋友", "同事", "合作", "合伙", "竞争", "对手", "兄弟", "姐", "哥")),
]

_XLR = {
    "大安": ("稳、静、守成", "事情本身不急，稳住就是赢",
             "先把手头的事做扎实，别急着开新摊子"),
    "留连": ("拖、黏、反复", "事情容易拖长，中间会反复一两次",
             "别催，也别在这时候硬推；把能控的部分先控住"),
    "速喜": ("快、喜、有信", "消息来得快，多半是往好的方向",
             "该出手就出手，犹豫反而错过窗口"),
    "赤口": ("口舌、争执", "容易起口角或被人误解",
             "把话说清、留书面记录，别在气头上定事"),
    "小吉": ("和、顺、得助", "有人帮，事情顺水推舟",
             "主动去问、去谈，贵人常在身边"),
    "空亡": ("空、落、无果", "眼下这条路可能走不到底",
             "换个方向或换个时间点，别硬耗"),
}

_JIANCHU = {
    "建": "适合开局、立规矩、谈长期合作",
    "除": "适合清理、断舍离、把旧账了结",
    "满": "适合收尾、结账、办庆典",
    "平": "适合日常事务、修补、走流程",
    "定": "适合签约、定方案、定亲",
    "执": "适合较真的事：验收、维权、追责",
    "破": "适合拆解与补救，别在今日开新局",
    "危": "适合排风险、做预案，不宜冒进",
    "成": "适合成交、落地、办喜事",
    "收": "适合收钱、收纳、总结复盘",
    "开": "适合开张、开业、开工、见人",
    "闭": "适合闭门整理、静养，不宜对外拓展",
}


def _grab(text: str, pattern: str, default: str = "") -> str:
    m = re.search(pattern, text or "")
    return m.group(1) if m else default


def _para(title: str, body: str) -> str:
    return f"**{title}**：{body}"


def _wrap(topic: str, paras, extra: str = "") -> str:
    blocks = [p for p in paras if p]
    out = [f"{AI_HEAD} · {topic}", ""]
    out.extend(blocks)
    if extra:
        out.extend(["", extra])
    out.extend(["", AI_FOOT])
    return "\n".join(out)


# ---------------------------------------------------------------- 八字
def for_bazi(chart: dict) -> str:
    dm = chart.get("day_master") or {}
    wx = chart.get("wuxing") or {}
    elem = dm.get("day_element") or ""
    gan = dm.get("day_gan") or ""
    status = dm.get("status") or ""
    nature, career, risk, body = _WX.get(elem, ("—", "—", "—", "—"))

    use = chart.get("use_gods") or {}
    fuyi = [w for w, _r in (use.get("fuyi") or [])]
    reason = "、".join(f"{w}（{r}）" for w, r in (use.get("fuyi") or []))
    pattern = ((chart.get("pattern") or {}).get("selected") or {}).get("pattern") or ""

    paras = []

    head = f"{gan}{elem}日主，{status or '格局平'}，月令{dm.get('month_branch', '')}"
    if pattern:
        head += f"，取{pattern}"
    head += "。"
    if fuyi:
        head += f"喜用落在{'、'.join(fuyi)}，顺着这几个字去安排环境与选择，阻力会小很多。"
    paras.append(_para("一句话", head))

    paras.append(_para(
        "性格底色",
        f"日主{elem}的人，底色是{nature}。{dm.get('month_judgment', '')}"
        f"这句话的意思是：你身上最吃力的那个环节，往往也是你最用力的地方。"
        f"{'日主偏弱，做事更依赖环境与贵人，先把班子搭好再谈扩张。' if status == '偏弱' else ''}"
        f"{'日主偏旺，主见强、能量足，但要留心用力过猛与不听劝。' if status == '偏旺' else ''}"
        f"{'日主中和，是最省力的结构，稳住节奏就能走远。' if status in ('中和', '平衡') else ''}"
    ))

    # 五行偏枯
    if wx:
        hi = max(wx, key=lambda k: wx[k])
        lo = min(wx, key=lambda k: wx[k])
        gap = ""
        if wx[hi] - wx[lo] >= 1.8:
            gap = (f"五行里{hi}最重（{wx[hi]:.1f}）、{lo}最轻（{wx[lo]:.1f}），"
                   f"结构偏{hi}。{hi}太过时容易把{ELEM_TRAP.get(hi, '某一面')}用过头，"
                   f"日常可以刻意补一点{lo}的生活面向（{ELEM_FILL.get(lo, '')}）。")
        else:
            gap = f"五行分布相对平均（{hi}{wx[hi]:.1f}、{lo}{wx[lo]:.1f}），不算偏枯，属于好调的结构。"
        paras.append(_para("结构上的偏与补", gap))

    # 十神主题
    deity = dm.get("month_deity") or ""
    if deity in _SHISHEN:
        paras.append(_para(
            "月令十神",
            f"月令{dm.get('month_main', '')}为{deity}——{_SHISHEN[deity]}。"
            "这一条往往决定你做事最自然的姿势：顺着它做事省力，逆着它做事费力。"
        ))

    paras.append(_para(
        "事业与钱",
        f"{'按喜用走，适合' + career + '。' if career != '—' else ''}"
        f"{'用神在' + '、'.join(fuyi) + '，择业与择城都可以往这几个五行对应的方向偏一点。' if fuyi else ''}"
        "钱这件事上，先把现金流做稳，再谈杠杆；命理只给倾向，不替你算账。"
    ))

    paras.append(_para(
        "关系里的短板",
        f"{risk}。这不是缺点，是用力过头的表现。"
        "和人相处时，把「我要说明白」换成「我先听完」，很多摩擦会自己消失。"
    ))

    paras.append(_para(
        "身体与作息",
        f"{body}是需要留意的部分。"
        f"{'偏弱的结构不宜长期熬夜硬扛，睡眠比补品有用。' if status == '偏弱' else '能量足但别透支，规律作息比猛练更划算。'}"
    ))

    # 大运
    dy = chart.get("dayun") or {}
    lst = dy.get("list") or []
    if lst:
        birth = (chart.get("birth") or {}).get("solar") or ""
        y = _grab(birth, r"(\d{4})")
        age = None
        if y:
            import datetime as _dt
            age = _dt.date.today().year - int(y)
        cur = None
        if age:
            for item in lst:
                if age >= item.get("age", 0):
                    cur = item
        if cur:
            paras.append(_para(
                "当前大运",
                f"走到{cur.get('age')}岁起的{cur.get('ganzhi')}运（{cur.get('deity')}）。"
                f"{_SHISHEN.get(cur.get('deity', ''), '这一步的主题，是把你已有的一面放大')}。"
                "大运看十年，具体到某一年还要看流年，别把十年的事压在一天里。"
            ))
    return _wrap("八字", paras)


ELEM_TRAP = {"木": "计划与扩张", "火": "热情与表达", "土": "承担与守成",
             "金": "规则与效率", "水": "思虑与变通"}
ELEM_FILL = {
    "木": "养点绿植、早起散步、把想法写下来",
    "火": "晒太阳、见人、把话说出来",
    "土": "定时吃饭、把家收拾干净、做长线的事",
    "金": "整理清单、断舍离、把边界说清",
    "水": "多喝水、早睡、留白想事",
}


# ---------------------------------------------------------------- 紫微
def for_ziwei(chart: dict) -> str:
    palaces = chart.get("palaces") or []
    by = {p.get("name"): p for p in palaces}
    ming = by.get("命宫") or chart.get("ming") or {}
    main = list(ming.get("main") or [])
    paras = []

    if main:
        txt = "、".join(main)
        kws = [ _ZW_STAR[s][0] for s in main if s in _ZW_STAR ]
        careers = [ _ZW_STAR[s][1] for s in main if s in _ZW_STAR ]
        paras.append(_para("一句话", f"命宫{txt}同守，底色是{'；'.join(kws)}。"))
        paras.append(_para(
            "性格与做法",
            f"你会同时带着两种力量：{'、'.join(kws)}。这不是矛盾，是分工——"
            "遇到要拍板的事用前一种，遇到要沟通的事用后一种。"
            f"{'适合的方向：' + '、'.join(careers) + '。' if careers else ''}"
        ))
    else:
        opp = palaces[(ming.get("index", 0) + 6) % 12] if palaces else {}
        borrow = "、".join(opp.get("main") or []) or "无主星"
        paras.append(_para("一句话", f"命宫无主星，借对宫{borrow}来论，性质会淡一些、也更灵活。"))
        paras.append(_para(
            "性格与做法",
            f"空宫的人适应力强，容易随环境变形，好处是不挑场合，难处是方向感要靠自己立。"
            f"借来的{borrow}给你一个参照，但别把它当死标签。"
        ))

    bad = list(ming.get("malefic") or [])
    if bad:
        tips = [ _ZW_BAD[b] for b in bad if b in _ZW_BAD ]
        paras.append(_para("要留意的地方", f"命宫见{'、'.join(bad)}。" + "；".join(tips) + "。"))

    # 身宫
    shen_key = chart.get("shen_key") or ""
    shen_palace = chart.get("shen_palace") or ""
    if shen_palace:
        paras.append(_para(
            "后半生的重心",
            f"身宫在{shen_palace}（{shen_key}）。身宫主后天用力处——"
            f"你会把越来越多精力放在{shen_palace}代表的事情上，中年之后这一点会更明显。"
        ))

    # 三方四正
    def _stars(name):
        p = by.get(name) or {}
        return "、".join(p.get("main") or []) or "空宫"

    paras.append(_para(
        "事业与财",
        f"官禄宫见{_stars('官禄')}，财帛宫见{_stars('财帛')}，迁移宫见{_stars('迁移')}。"
        "看事业不只是看官禄一格，这三格一起看：能干什么是官禄，值多少钱看财帛，出门顺不顺看迁移。"
    ))

    sihua = chart.get("sihua") or {}
    hua_hits = []
    for key, star in sihua.items():
        for p in palaces:
            if star in (p.get("main") or []) or star in (p.get("lucky") or []):
                hua_hits.append((key, star, p.get("name")))
                break
    if hua_hits:
        parts = []
        for key, star, pname in hua_hits:
            if key == "禄":
                parts.append(f"化禄（{star}）落{pname}——这里最容易得到资源与机会")
            elif key == "权":
                parts.append(f"化权（{star}）落{pname}——这里你想自己说了算，也会因此更累")
            elif key == "科":
                parts.append(f"化科（{star}）落{pname}——这里容易有口碑、文书与名声之助")
            else:
                parts.append(f"化忌（{star}）落{pname}——这里是你反复卡壳、需要慢慢磨的地方")
        paras.append(_para("生年四化", "；".join(parts) + "。"))

    # 当前大限
    age = None
    solar = chart.get("solar") or ""
    y = _grab(solar, r"(\d{4})")
    if y:
        import datetime as _dt
        age = _dt.date.today().year - int(y) + 1
    if age:
        cur = None
        for p in palaces:
            dx = p.get("daxian")
            if dx and dx[0] <= age <= dx[1]:
                cur = p
                break
        if cur:
            stars = "、".join(cur.get("main") or []) or "无主星"
            paras.append(_para(
                "当前大限",
                f"{cur.get('daxian')[0]}-{cur.get('daxian')[1]}岁行{cur.get('name')}限"
                f"（{cur.get('zhi_name')}，{stars}）。这十年的主题落在{cur.get('name')}上，"
                "该格的功课做好了，十年都顺；没做，就会反复回到同一道题。"
            ))
    return _wrap("紫微斗数", paras)


# ---------------------------------------------------------------- 六爻
def _pick_yongshen(question: str):
    q = question or ""
    for name, kws in _LY_KW:
        for kw in kws:
            if kw in q:
                return name, kw
    return "", ""


def _rel(a: str, b: str) -> str:
    """a 对 b 的关系: 生/克/被生/被克/同. """
    if not a or not b:
        return ""
    if a == b:
        return "同"
    if _WX_SHENG.get(a) == b:
        return "生"
    if _WX_KE.get(a) == b:
        return "克"
    if _WX_SHENG.get(b) == a:
        return "被生"
    if _WX_KE.get(b) == a:
        return "被克"
    return ""


def for_liuyao(d: dict, question: str = "") -> str:
    liuqin = d.get("liuqin") or []
    dongs = d.get("dongs") or []
    ben, bian = d.get("ben") or {}, d.get("bian") or {}
    paras = []
    q = (question or "").strip()

    if q:
        paras.append(_para("所问", f"「{q}」"))

    paras.append(_para(
        "卦象",
        f"本卦{ben.get('name') or d.get('ben_name')}（{ben.get('palace', '')}宫），"
        f"{'之' + (bian.get('name') or d.get('bian_name')) if dongs else '六爻安静'}。"
        f"{ben.get('meaning', '')}"
    ))

    # 用神取用
    ys, kw = _pick_yongshen(q)
    if ys:
        paras.append(_para(
            "取用神",
            f"你问的属于{_LY_TOPIC.get(ys, '这一类事')}，按六爻规矩取「{ys}」为用神"
            f"——{_LY_LIUQIN[ys][0]}。"
            f"{_LY_LIUQIN[ys][1]}。"
        ))
        idx = [i for i, qn in enumerate(liuqin) if qn == ys]
        gong_wx = d.get("gong_wx") or ""
        if not idx:
            paras.append(_para(
                "用神不见",
                f"卦里没有{ys}，叫「用神伏藏」。这不等于没希望，而是说事情的关键还没露头："
                "要么条件还没齐，要么对方还没表态。这时候催是没用的，先把能准备的东西准备好。"
            ))
            score = 0
        else:
            # 简易旺衰: 月建/日辰对用神五行的生克
            ys_wx = _liuqin_wx(gong_wx, ys)
            month_wx = d.get("month_wx") or ""
            day_wx = d.get("day_wx") or ""
            score = 0.0
            notes = []
            for label, w in (("月建", month_wx), ("日辰", day_wx)):
                r = _rel(w, ys_wx)
                if r == "同":
                    score += 2
                    notes.append(f"{label}同气（{w}），有力")
                elif r == "生":
                    score += 1.5
                    notes.append(f"{label}生扶（{w}生{ys_wx}），有助")
                elif r == "克":
                    score -= 1.5
                    notes.append(f"{label}相克（{w}克{ys_wx}），受压")
                elif r == "被生":
                    score -= 0.5
                    notes.append(f"{label}泄气（{ys_wx}生{w}），耗力")
                elif r == "被克":
                    score += 0.5
                    notes.append(f"{label}受制（{ys_wx}克{w}），尚可")
            shi = d.get("shi") or 0
            holding = (shi - 1) in idx
            moving = [i for i in idx if i in dongs]
            txt = (f"用神{ys}（{ys_wx}）在卦中现{len(idx)}爻"
                   f"{'，且持世——事在你自己手上' if holding else ''}"
                   f"{'，并且发动，说明事情会变' if moving else '，安静不动，局面暂时定型'}。")
            if notes:
                txt += "；".join(notes) + "。"
            paras.append(_para("用神旺衰", txt))

            # 动爻变化
            if moving:
                bi = moving[0]
                bq = liuqin[bi] if bi < len(liuqin) else ""
                bnj = (d.get("bian_nj") or [None] * 6)[bi]
                if bnj:
                    paras.append(_para(
                        "动爻怎么变",
                        f"用神{_yao_label(bi)}发动，化出{bnj[1]}。"
                        "动就是变，这一爻是整个卦的转折点：往好的方向变要看化神有没有力，"
                        "往坏的方向变也只是阶段性卡顿，不是终局。"
                    ))
            # 忌神
            ke_ys = _ke_of(ys_wx)
            ji_idx = [i for i, qn in enumerate(liuqin)
                      if _liuqin_wx(gong_wx, qn) == ke_ys and i in dongs]
            if ji_idx:
                paras.append(_para(
                    "阻力在哪",
                    f"克用神的{ke_ys}气（{'、'.join(liuqin[i] for i in ji_idx)}）也在发动，"
                    "说明阻力是活的、会来事。对策不是硬顶，而是把这股力量先安顿好——"
                    "该沟通的沟通，该补的手续补齐。"
                ))
    else:
        shi = d.get("shi") or 1
        shi_q = liuqin[shi - 1] if 0 < shi <= len(liuqin) else ""
        ying_q = liuqin[(d.get("ying") or 1) - 1] if 0 < (d.get("ying") or 1) <= len(liuqin) else ""
        paras.append(_para(
            "没写明要问什么",
            f"那就看世应：世爻是{shi_q}（你自己），应爻是{ying_q}（对方或事情本身）。"
            "把问题说得再具体一点，用神才能取得准，结论也会更明确。"
        ))
        score = 0

    # 动爻整体
    if dongs:
        paras.append(_para(
            "变数",
            f"本次有{len(dongs)}个动爻：{'、'.join(_yao_label(i) for i in dongs)}。"
            "动爻多，说明事情还在动、还没定型；动爻少，说明格局已定，只剩执行。"
        ))
    else:
        paras.append(_para(
            "变数",
            "六爻安静，眼下没有新变量进来。这种卦最适合照原计划推进，别自己加戏。"
        ))

    # 倾向
    if q and ys:
        if score >= 1.5:
            verdict = "用神有气，事情整体是往成的方向走，但要看你能不能在对的时间点出力。"
        elif score <= -1.5:
            verdict = "用神受压，眼下硬推代价大。换个时间点、换个切入点，比现在死磕划算。"
        else:
            verdict = "用神不旺不弱，成败主要落在人为：你多做一步，它就往成那边偏一点。"
    else:
        verdict = "卦只是把局势摊开，成不成还要看人怎么走。"
    paras.append(_para(
        "怎么看这个结果",
        verdict + "六爻看的是「这件事在这个时点的势」，不是给你判死刑——"
        "势弱就把节奏放慢，势强就别拖。"
    ))
    paras.append(_para(
        "可以马上做的",
        "把问题拆成「我能控的」和「我控不了的」两堆：能控的今天推进一步，"
        "控不了的先放下。同一件事不要反复起卦，那只会让你更乱。"
    ))
    return _wrap("六爻" + (f" · {q}" if q else ""), paras)


def _liuqin_wx(gong_wx: str, liuqin: str) -> str:
    if not gong_wx:
        return ""
    if liuqin == "兄弟":
        return gong_wx
    if liuqin == "父母":
        return _WX_BEI_SHENG.get(gong_wx, "")
    if liuqin == "子孙":
        return _WX_SHENG.get(gong_wx, "")
    if liuqin == "妻财":
        return _WX_KE.get(gong_wx, "")
    if liuqin == "官鬼":
        return _WX_BEI_KE.get(gong_wx, "")
    return ""


def _ke_of(wx: str) -> str:
    for a, b in _WX_KE.items():
        if b == wx:
            return a
    return ""


def _yao_label(i: int) -> str:
    pos = ["初", "二", "三", "四", "五", "上"]
    return f"{pos[i]}爻" if 0 <= i < 6 else ""


# ---------------------------------------------------------------- 文字类工具
def _for_xlr(text: str) -> str:
    name = _grab(text, r"【小六壬 · (.+?)】")
    wx = _grab(text, r"五行：(\S)")
    direction = _grab(text, r"方位：([^\s　]+)")
    luck = _grab(text, r"落宫：.+?（(.+?)）")
    if not name:
        return ""
    kw, stage, advice = _XLR.get(name, ("", "", ""))
    paras = [
        _para("一句话", f"落{name}宫（{luck or '—'}），关键字是{kw}。"),
        _para("现在的局势", f"{stage}。这不是好坏的问题，是节奏的问题——"
                          "顺势做，事就轻；逆着来，事就重。"),
        _para("怎么做", f"{advice}。小六壬给的是当下这一刻的着力点，事情过了这个点会变，"
                     "所以别拿它当长期判词。"),
    ]
    if wx:
        extra = f"落宫五行属{wx}"
        if direction:
            extra += f"，方位在{direction}"
        extra += "。" + ELEM_FILL.get(wx, "")
        paras.append(_para("借势", extra + "。"))
    return _wrap("小六壬", paras)


def _for_meihua(text: str) -> str:
    ben = _grab(text, r"本卦：(\S+)")
    hu = _grab(text, r"互卦：(\S+)")
    bian = _grab(text, r"变卦：(\S+)")
    ti = _grab(text, r"体卦(\S+?[木火土金水])")
    yong = _grab(text, r"用卦(\S+?[木火土金水])")
    rel = _grab(text, r"｜(.+?)（")
    if not ben:
        return ""
    paras = [
        _para("一句话", f"本卦{ben}，{'互卦' + hu + '，' if hu else ''}"
                      f"{'变卦' + bian + '，' if bian else ''}体{ti}用{yong}。"),
        _para("内外因", f"体卦是{ti}（你自己这一边），用卦是{yong}（事情那一边）。"
                     f"{'体用关系是「' + rel + '」，' if rel else ''}"
                     "体强用弱，主动权在你手上；体弱用强，就得借力或者等时机。"),
        _para("节奏", f"本卦看开头，互卦看过程，变卦看结尾。"
                    f"开头是{ben}，结尾走向{bian or ben}——"
                    "这两者之间的差距，就是你要做的功课。"),
        _para("怎么做", "梅花易数最忌起完卦就等结果。卦给的是「往哪使劲」，"
                     "具体动作还是要你自己落地。"),
    ]
    return _wrap("梅花易数", paras)


def _for_almanac(text: str) -> str:
    yi = _grab(text, r"宜：(.+)")
    ji = _grab(text, r"忌：(.+)")
    jianchu = _grab(text, r"建除：(\S)日")
    zhishen = _grab(text, r"值神：(.+?)（")
    chong = _grab(text, r"冲煞：(.+)")
    if not (yi or ji):
        return ""
    paras = [
        _para("一句话", f"今天是{zhishen or '—'}值神、{jianchu or '—'}日。"
                    f"{_JIANCHU.get(jianchu, '按日常节奏走就好')}。"),
    ]
    if yi:
        paras.append(_para("适合做的", f"{yi}。这些事顺着今天的势，阻力小一些。"))
    if ji:
        paras.append(_para("能避就避", f"{ji}。不是绝对不能做，是做了要多花力气兜底。"))
    if chong:
        paras.append(_para("提醒", f"{chong.replace(chr(12288), '，')}。老黄历的冲煞是按日支来说的，"
                              "对应生肖的人当天容易心浮，重要决定多留一晚再定。"))
    paras.append(_para("怎么用", "黄历是「择时的参考」，不是「今天能不能活」的判决。"
                            "真有非做不可的事，把它做扎实，比挑日子更管用。"))
    return _wrap("黄历", paras)


def _for_huangji(text: str) -> str:
    year_gua = _grab(text, r"值年卦：(\S+)（")
    hui_gua = _grab(text, r"会卦：(\S+)（")
    meaning = _grab(text, r"值年卦：.*?\n\s*卦意：(.+)")
    gong = _grab(text, r"卦宫：(\S+?)（")
    if not year_gua:
        return ""
    paras = [
        _para("一句话", f"值年卦{year_gua}" + (f"，卦宫{gong}" if gong else "") + "。"),
        _para("这一年的主题", (meaning.strip().rstrip("。；;，,") if meaning else "按卦象看，宜稳中求进") + "。"
                          "值年卦讲的是一整年的天时，落到个人身上要打折看——"
                          "它给的是背景色，不是你的剧本。"),
        _para("怎么借势", f"会卦{hui_gua}看大势，年卦看当年。"
                     "大势走向不由个人改，个人要做的是在大势里挑一个顺风的方向。"
                     "跟大势对着走，力气会白花。"),
        _para("提醒", "皇极经世是大尺度推演，用来理解「时代的气质」，"
                   "别拿它算具体某件事的吉凶。"),
    ]
    return _wrap("皇极经世", paras)


def _for_bazhai(text: str) -> str:
    ming_gua = _grab(text, r"命卦：(\S+?)（")
    zhai_gua = _grab(text, r"宅卦：(\S+?)（")
    match = "宅命相配" in text
    good = _grab(text, r"吉方：(.+)")
    bad = _grab(text, r"凶方：(.+)")
    if not ming_gua:
        return ""
    paras = [
        _para("一句话", f"{ming_gua}，{zhai_gua or '—'}，"
                    f"{'宅命相配，住着顺' if match else '宅命不合，需要靠布局补'}。"),
        _para("房间怎么分", f"吉方是{good or '—'}，这些方位优先给大门、主卧、书桌、灶位。"
                       f"凶方是{bad or '—'}，用来做储物、卫生间、走廊这些不需要久留的地方。"),
        _para("不合怎么办", "宅命不合不代表不能住。八宅的解法是「以门与床定吉凶」——"
                       "把最常待的两个位置挪到吉方，效果比换房子现实得多。"),
        _para("别过度", "方位是加分项，不是决定项。采光、通风、通勤、家人作息，"
                    "这些对生活的影响比方位大得多。"),
    ]
    return _wrap("八宅风水", paras)


def _for_qimen(text: str) -> str:
    ju = _grab(text, r"【奇门遁甲】(\S+?) ·")
    jq = _grab(text, r"节气 (\S+?) · (\S+?)（")
    yuan = _grab(text, r"节气 \S+ · (\S+?)（")
    fu_star = _grab(text, r"值符 (\S+?) · 值使")
    fu_door = _grab(text, r"值使 (\S+?) ·")
    land = _grab(text, r"值符\S*?落(\S+?)宫（(\S+?)）")
    land_dir = _grab(text, r"值符\S*?落\S+?宫（(\S+?)）")
    door_land = _grab(text, r"值使\S*?落(\S+?)宫（(\S+?)）")
    door_dir = _grab(text, r"值使\S*?落\S+?宫（(\S+?)）")
    ji = _grab(text, r"三吉门（开/休/生）落宫：(.+)")
    if not ju:
        return ""

    # 盘子气质
    if "天盘伏吟" in text:
        tone = ("这一盘是伏吟局：天盘星各归本位，气场是「静」的。"
                "事情不会一下子推开，多在上一个阶段反复；此时主动出击往往撞空，"
                "守、等、把已有的事做扎实，反而是最快的路。")
    elif "天盘反吟" in text:
        tone = ("这一盘是反吟局：值符落到对冲宫，气场是「翻」的。"
                "计划容易被打乱、旧事重提，变动会比预想的多。"
                "适合处理积压已久、必须动刀的事；不适合临时起意的新计划。")
    elif "人盘伏吟" in text:
        tone = ("这一盘人盘伏吟：门归本位，做事的方向没错，"
                "但推进时要多确认几遍——信息差和来回沟通是主要成本。")
    else:
        tone = ("这一盘星门各得其位，气场相对平顺。"
                "该推进的可以推进，只是别指望一步到位，按节奏走就行。")

    paras = [
        _para("一句话", f"{ju}，{jq}{yuan}起局，值符{fu_star}、值使{fu_door}。{tone}"),
        _para("方位怎么用",
              (f"{ji.rstrip('。')}。" if ji else "此局三吉门未明现。") +
              "奇门讲的是「同一件事，换个方位办，阻力不同」。谈事、面试、约见，"
              "优先选吉门所落的方位；找不到合适的位置，就别硬凑，把内容准备好比方位更实在。"),
        _para("事的两个抓手",
              f"值符{fu_star}落{land or '—'}（{land_dir or '—'}）代表事情的主导力量，"
              f"值使{fu_door}落{door_land or '—'}（{door_dir or '—'}）代表落地执行的环节。"
              "主导方在哪个方位，就先在那个方向上找人、找资源；"
              "执行卡住时，看值使宫的状态——它多代表流程里最费劲的一环。"),
        _para("怎么用",
              "奇门是「时间 + 空间」的参考：选时机、选方位、选切入点。"
              "它不替你决定做什么，只提示「什么时候、往哪边、从哪下手」阻力小一点。"),
    ]
    return _wrap("奇门遁甲", paras)


_LIUREN_QIN = {
    "兄弟": "同辈、伙伴、竞争者，也主「分一份出去」",
    "妻财": "钱、实务、可交付的成果，也主投入与代价",
    "官鬼": "压力、规则、上级与是非，是推着你走的那股力",
    "父母": "文书、凭据、长辈、房子，主「有个依靠」",
    "子孙": "结果、产出、松弛感，主「事情自己长出答案」",
}

_LIUREN_KE = {
    "伏吟": "课体伏吟，天地盘重叠：事情原地打转，推不动也退不掉，多是等消息、等对方先动。",
    "返吟": "课体返吟，天地盘相冲：来回拉扯，同一件事会反复一次，落定之前别急着定性。",
    "昴星": "课体昴星：事从静中起，眼下没什么动静，答案在「等一等」里，急不来。",
    "别责": "课体别责：四课不齐，事情本身不成形，多要借别人的力或换个由头才推得动。",
    "八专": "课体八专：干支同位，事与己身贴得太近，容易当局者迷，宜找个外人问一句。",
    "遥克": "课体遥克：克不贴身，事是隔着一层来的，用力点不在明面上。",
    "涉害": "课体涉害：几处纠缠，得一层层剥开，慢是慢，但每剥一层都有进展。",
    "比用": "课体比用：几处相克，最后取了与日干同类的那一处，事从「和自己像的那一头」起。",
}


def _for_liuren(text: str) -> str:
    yuejiang = _grab(text, r"月将 (\S+?)（")
    shi = _grab(text, r"）加 (\S+?)时")
    ke_ti = _grab(text, r"课体 ([^\s。：]+)")
    kong = _grab(text, r"旬空 (\S+?) ·")
    ma = _grab(text, r"驿马 (\S+?) ·")
    zhou = _grab(text, r"· (昼占|夜占) ·")
    chuan = re.findall(
        r"· (初|中|末)传：(\S+) / (\S+) / 临(\S+) · (\S+?)((?:　[空马])*)\s*$",
        text, re.M)
    if not chuan:
        return ""

    detail = []
    for name, zhi, jiang, lin, qin, tail in chuan:
        tone = _LIUREN_QIN.get(qin, "")
        extra = "（空）" if "空" in tail else ("（马）" if "马" in tail else "")
        detail.append(f"{name}传{zhi}乘{jiang}临{lin}，{qin}{extra}——{tone}")
    chain = "；".join(detail)

    ke_line = ""
    for key, val in _LIUREN_KE.items():
        if key in ke_ti:
            ke_line = val
            break
    if not ke_line:
        ke_line = (f"课体{ke_ti}：四课里有明确的生克，事情有抓手，"
                   "沿着被克的那一处去解，路子是通的。")

    head, mid, last = chuan[0], chuan[1], chuan[2]
    paras = [
        _para("一句话", f"月将{yuejiang}加{shi}时，{zhou or '昼占'}，课体{ke_ti}。{ke_line}"),
        _para("三传怎么读",
              f"{chain}。三传是事情的三段：初传看起因与当下的着力点，"
              f"中传看中间会拐到哪，末传看最后落在什么上。这一盘从「{head[1]}（{head[4]}）」起，"
              f"经「{mid[1]}（{mid[4]}）」，落到「{last[1]}（{last[4]}）」。"),
        _para("要不要动",
              ("三传见驿马（" + ma + "），事有动象，坐着等不如走一趟，"
               "奔走、换线、面谈都比线上耗着强。" if any("马" in c[5] for c in chuan)
               else "三传不见驿马，事偏向「在原地解决」，不必大动干戈，"
                    "把手上的关系和凭据理清更有效。")),
        _para("空亡提醒",
              ("三传逢空（" + kong + "），这一段容易停在口头上：答应得快、兑现得慢。"
               "重要的事留个字面凭据，别只靠一句「没问题」。"
               if any("空" in c[5] for c in chuan)
               else "三传不空，事情是能落地的，该定的时间就定下来，别反复。" )),
        _para("怎么用",
              "大六壬看的是「一件事从起念到落定」的过程。初传是现在该抓的那一头，"
              "末传是它的自然归宿。知道终点大概长什么样，中间就不容易被一时的起伏带偏。"),
    ]
    return _wrap("大六壬", paras)


def _for_jinjue(text: str) -> str:
    if "**金口诀**" not in (text or ""):
        return ""
    ren = _grab(text, r"人元 (\S+) / 贵神")
    gui = _grab(text, r"贵神 (\S+) / 将神")
    jiang = _grab(text, r"将神 (\S+) / 地分")
    fen = _grab(text, r"· 地分 (\S+?)（")
    yuejiang = _grab(text, r"月将 (\S+?)（")
    ling = _grab(text, r"月令 \S+?（(\S+?)当令）")
    zhou = _grab(text, r"· (昼占|夜占) ·")

    siwei = re.findall(r"· (人元|贵神|将神|地分)：(\S+)（(\S+?)）· (\S+)", text)
    d = {p: (v, wx, ws) for p, v, wx, ws in siwei}
    if not d:
        return ""

    rel_k = _grab(text, r"贵神\S{1,2} 与 将神\S{1,2}：(\S+)")
    rel_txt = {
        "克": "贵神压着将神，外力大过内事 —— 顺势借力比硬顶有用",
        "被克": "将神反克贵神，你自己能主导，但要担耗神的代价",
        "生": "贵神生将神，有人在背后替你推一把，别客气",
        "被生": "将神生贵神，你在为别人出力，先看值不值得",
        "比和": "神将同气，事情好成，但也不容易有大变化",
    }.get(rel_k, "")

    def _block(title):
        parts = text.split(f"**{title}**")
        if len(parts) < 2:
            return []
        out = []
        for line in parts[1].split("\n")[1:]:
            if line.startswith("· "):
                out.append(line[2:].strip())
            elif line.strip():
                break
        return out

    dong = _block("五动")
    keti = _block("课体")
    notes = _block("要点")

    dong_line = "；".join(dong) if dong else ""
    if not dong_line:
        dong_line = "本课四位无克，气势平顺，宜守成、先把手上的事做扎实"
    dong_line = dong_line.rstrip("。")

    wx_sum = "、".join(f"{p}{v}（{wx}·{ws}）" for p, (v, wx, ws) in d.items())
    strong = [p + v for p, (v, wx, ws) in d.items() if ws in ("旺", "相")]
    weak = [p + v for p, (v, wx, ws) in d.items() if ws in ("囚", "死")]
    keti_line = "；".join(keti[:3]).rstrip("。") if keti else "课体无特殊冲合，按神将生克直读"

    paras = [
        _para("一句话",
              f"{zhou or '昼占'}，月将{yuejiang}，地分{fen}，四位为"
              f"人元{ren}、贵神{gui}、将神{jiang}、地分{fen}。"
              + (f"{rel_txt}。" if rel_txt else "神将同气，事缓而稳。")),
        _para("四位怎么读",
              f"{wx_sum}。月令{ling}当令，这一课的气在"
              + ("、".join(strong) if strong else "四处都不算旺")
              + ("；相对使不上劲的是" + "、".join(weak) if weak else "")
              + "。人元是眼下的天时与来意，贵神是对方与外力，"
                "将神是事情的走向，地分是你站的那块地。"),
        _para("事落在哪一头",
              f"{dong_line}。金口诀不看单一吉凶，而看四股力往哪边偏："
              "偏在贵神，事情由别人推动；偏在将神，得你自己走一趟；"
              "偏在地分，根子上没理顺，先动窝不如先动心。"),
        _para("课体提醒", keti_line),
        _para("怎么用",
              (notes[0].rstrip("。") if notes else
               "四位看的是「当下这一件事」的力道分布，不是命。"
               "把它当一面镜子：哪一头旺，就往哪头使力；哪一头死，就先别硬来")),
    ]
    return _wrap("金口诀", paras)


def _for_xuankong(text: str) -> str:
    if "**玄空飞星**" not in (text or ""):
        return ""
    head = _grab(text, r"\*\*玄空飞星\*\* · (\S+?运) (\S+?)山(\S+?)向")
    yun_name = _grab(text, r"\*\*玄空飞星\*\* · (\S+?运)")
    zuo = _grab(text, r"坐 (\S)（")
    xiang = _grab(text, r"向 (\S)（")
    geju = _grab(text, r"\*\*格局\*\*：(\S+?)\n")
    zuo_gua = _grab(text, r"坐 \S（(\S+?)卦·")
    xiang_gua = _grab(text, r"向 \S（(\S+?)卦·")
    year_span = _grab(text, r"(\d{4}–\d{4})年")

    cells = re.findall(r"· (\S+?)运(\d)　山(\d)（(\S)）　向(\d)（(\S)）", text)
    d = []
    for name, yun, shan, sq, xw, xq in cells:
        d.append({"name": name, "shan": int(shan), "xiang": int(xw),
                  "sq": sq, "xq": xq})

    good = [c for c in d if c["name"] != "中宫" and (
        c["sq"] in ("旺", "生") or c["xq"] in ("旺", "生"))]
    bad = [c for c in d if c["name"] != "中宫" and (
        c["sq"] in ("死", "煞") and c["xq"] in ("死", "煞"))]
    zuo_cell = next((c for c in d if c["name"].startswith(zuo_gua + "宫")), None)
    xiang_cell = next((c for c in d if c["name"].startswith(xiang_gua + "宫")), None)

    geju_note = {
        "旺山旺向": "当运星既到坐山又到向首，丁财两旺，是最省心的格局，宜坐实朝空",
        "上山下水": "当运星全跑反了，山星落向首、向星落坐山，属颠倒之局，要靠布局反用",
        "双星会向": "山向两星同聚向首，财气旺、人丁稍弱，重纳气口与前方明堂",
        "双星会坐": "山向两星同聚坐山，人丁旺、财气稍缓，重靠山与后方厚实",
    }
    gkey = next((k for k in geju_note if geju.startswith(k)), "")
    base = geju_note.get(gkey, "当运星未成对落到山向，吉凶要看各宫双星组合")

    zuo_txt = ""
    if zuo_cell:
        zuo_txt = (f"坐山{zuo}所在的{zuo_gua}宫，山星{zuo_cell['shan']}（{zuo_cell['sq']}）、"
                   f"向星{zuo_cell['xiang']}（{zuo_cell['xq']}）")
    xiang_txt = ""
    if xiang_cell:
        xiang_txt = (f"向首{xiang}所在的{xiang_gua}宫，山星{xiang_cell['shan']}（{xiang_cell['sq']}）、"
                     f"向星{xiang_cell['xiang']}（{xiang_cell['xq']}）")

    good_line = ("、".join(f"{c['name']}" for c in good)
                 if good else "没有特别得气的宫位")
    bad_line = ("、".join(f"{c['name']}" for c in bad)
                if bad else "没有山向双死煞的宫位")

    paras = [
        _para("一句话",
              f"{yun_name}（{year_span}）的{zuo}山{xiang}向，格局是「{geju}」——"
              f"{base}。"),
        _para("三层星怎么读",
              f"每宫三个数字：左上山星管人丁与健康，右上向星管财气与人事，"
              f"中间的运星是这二十年的底气。"
              + ("；".join([t for t in (zuo_txt, xiang_txt) if t]) + "。" if zuo_txt or xiang_txt else "")
              + "这两处是这套房子的主气，开门、安床、摆桌先看这里。"),
        _para("哪边能用，哪边要压",
              f"得气的宫位在{good_line}，适合做主要活动区、办公位、床位；"
              f"山向双死煞的宫位在{bad_line}，宜静宜压，别拿来做卧室或大门。"
              "煞气不等于凶，只是这二十年里它使不上劲，硬用会白耗。"),
        _para("形理要配合",
              "飞星只是理气，还得看形。旺山旺向要坐方有实（楼、山、高柜），"
              "向首有虚（窗、路、水）；上山下水反过来用才救得回来。"
              "如果坐方是空地、向首被高楼堵死，再好的盘也落不了地。"),
        _para("用前提醒",
              "玄空看的是「这栋房子在这二十年里的气」，换运会换盘，"
              "装修、换门向都可能要重新起盘。同一栋楼，单元不同、门向不同，"
              "盘就不一样——报坐向时最好用罗盘量一下度数，别凭感觉。"),
    ]
    return _wrap("玄空飞星", paras)


def _for_taiyi(text: str) -> str:
    year_gz = _grab(text, r"## 太乙神数 · (\S+?)年岁计")
    ju = _grab(text, r"入局\*\* (\S+?第 \d+ 局)")
    taiyi_gong = _grab(text, r"太乙临 (\d+)宫")
    taiyi_gua = _grab(text, r"太乙临 \d+宫（(\S+?)·")
    taiyi_fang = _grab(text, r"太乙临 \d+宫（\S+?·(\S+?)）")
    zhu = _grab(text, r"主算 (\d+)")
    ke = _grab(text, r"客算 (\d+)")
    zhu_shu = _grab(text, r"主算 \d+\*\* · (\S+?) ·")
    ke_shu = _grab(text, r"客算 \d+\*\* · (\S+?) ·")
    zhu_san = _grab(text, r"主算 \d+\*\* · \S+? · (\S+?) ·")
    ke_san = _grab(text, r"客算 \d+\*\* · \S+? · (\S+?) ·")
    zhi_shi = _grab(text, r"值使门 \*\*(\S+?)门\*\*")
    wenchang = _grab(text, r"文昌\(天目\)：(\S+?)·(\S+?)[，\n]")
    wenchang_pos = _grab(text, r"文昌\(天目\)：\S+?·(\S+?)[，\n]")
    shiji = _grab(text, r"始击\(客目\)：(\S+?)·")
    zhu_jiang = _grab(text, r"主大将 (\d+)宫")
    ke_jiang = _grab(text, r"客大将 (\d+)宫")
    geju = re.findall(r"^· (掩|囚|对|格|击|迫|提挟|杜塞|无掩迫囚击)[^\n]*$",
                      text, re.M)
    if not year_gz and not ju:
        return ""

    def _int(v):
        try:
            return int(v)
        except Exception:
            return 0

    zs, ks = _int(zhu), _int(ke)
    zj, kj = _int(zhu_jiang), _int(ke_jiang)

    # 主客之势
    if zs and ks:
        if zs > ks:
            trend = ("主算大于客算：这一局「主」的一侧更厚——先动的一方、本土的一方、"
                     "自己手里的资源占优，事情适合在自己熟悉的地盘上推进。")
        elif ks > zs:
            trend = ("客算大于主算：这一局「客」的一侧更厚——外部力量、后到的一方、"
                     "对方手里的牌更硬，硬顶不如先看清对方要什么。")
        else:
            trend = ("主客两算相当：双方势均力敌，谁先动谁先露底，"
                     "把节奏拖慢一点反而更有利。")
    else:
        trend = "主客两算已出，按先后与内外两方对照着看。"

    long_short = []
    if zs and zs < 11:
        long_short.append("主算短，内里的准备还不够厚")
    if ks and ks < 11:
        long_short.append("客算短，外部给的力量有限")
    ls = ("；".join(long_short) + "。") if long_short else "主客两算皆长，气数铺得开。"

    # 格局
    ge_txt = {
        "掩": "掩：客目与太乙同宫，事情被遮住一层，真实意图不容易看清，先别急着表态",
        "囚": "囚：大将同太乙，力量被拘住了，越用力越憋，宜守不宜攻",
        "对": "对：天目冲太乙，正面顶上了，容易硬碰硬",
        "格": "格：主大将与太乙相对，君臣背离之象，合作方可能与你目标不一致",
        "击": "击：始击在太乙左右，压力从侧边来，提防突然发难",
        "迫": "迫：诸将临太乙前后，人被事情推着走，主动权不在自己手上",
        "提挟": "提挟：太乙与天目挟客，格局紧，进退都受限",
        "杜塞": "杜塞：五算出而门将俱无，事情卡死，先放一放",
    }
    key_ge = list(dict.fromkeys(geju))
    if key_ge:
        ge_line = "；".join(ge_txt.get(g, g) for g in key_ge[:3]) + "。"
    else:
        ge_line = "无掩迫囚击，三才算和，是相对平顺的一局。"

    paras = [
        _para("一句话",
              f"{year_gz}年岁计，{ju}，太乙临{taiyi_gong}宫"
              f"（{taiyi_gua}·{taiyi_fang}）。"
              f"主算{zs}、客算{ks}，{zhu_shu or '—'}/{ke_shu or '—'}。{trend}"),
        _para("主客两方怎么看",
              f"主算{zs}是内、是我、是先动的一方；客算{ks}是外、是对方、是后到的一方。"
              f"{ls}太乙神数原本用来占国运兵事，落到个人身上，"
              "「主」就是你自己的底子和主场，「客」是外部环境与对手的牌面。"
              "看两算的大小与阴阳，判断该主动还是该等。"),
        _para("格局提醒",
              ge_line +
              "格局不是判死刑，它标的是「哪一处卡着」。卡在掩，就多问几句把话问清；"
              "卡在囚，就先松手别硬推进；卡在格，就把双方目标重新对一遍。"),
        _para("二目与抓手",
              f"文昌（天目）在{wenchang or '—'}{('·' + wenchang_pos) if wenchang_pos else ''}，"
              f"始击（客目）在{shiji or '—'}，主大将{zhu_jiang or '—'}宫、"
              f"客大将{ke_jiang or '—'}宫。天目看「事从哪儿起」，"
              "始击看「对面怎么动」，两个大将宫则是双方真正使力的落点。"
              + ("两边大将同宫，说明双方盯的是同一件事，容易正面撞上。"
                 if zj and zj == kj else "")),
        _para("值使与用法",
              f"值使{zhi_shi or '—'}门主当年当值之事，可以理解为「这一年主要处理的门类」。"
              "太乙属三式之首，原始用法是观大局、定进退，不是给个人算命；"
              "拿它看一年的大势与主客强弱最合适，具体的事还得落到现实里去办。"
              "（本盘按《太乙金镜式经》岁计口径，各派历元不同，结论会有差异。）"),
    ]
    return _wrap("太乙神数", paras)


_QZ_WX_CHAR = {
    "木": ("仁厚、看重成长", "惯于看长线、爱规画，遇事先问「这件事值不值得做久」"),
    "火": ("热烈、要体面", "起手快、讲气势，能把场子点起来，但也容易一口气烧完"),
    "土": ("沉稳、讲兑现", "重根基与承诺，慢而稳，最怕被催着表态"),
    "金": ("刚断、有分寸", "是非清楚、决断快，但容易硬碰硬"),
    "水": ("聪敏、多曲折", "会绕、会等，能屈能伸，怕的是想太多而不动"),
}

_QZ_WEI_MEAN = {
    "命宫": "自身与整体气数", "财帛": "钱财的来源与用法",
    "兄弟": "同辈、手足与协作", "田宅": "居所、家业与根基",
    "男女": "子女、创作与欢愉", "奴仆": "下属、劳作与身体消耗",
    "夫妻": "婚配、合作与对手", "疾厄": "病痛、隐患与欠账",
    "迁移": "外出、变动与机遇", "官禄": "事业、名位与公开身份",
    "福德": "精神享受、兴趣与福分", "相貌": "父母、遗传与外在形象",
}


_QZ_ZHI = "子丑寅卯辰巳午未申酉戌亥"


def _qz_parse_planets(text: str):
    """从文本中取出十一曜行。"""
    out = []
    for line in (text or "").split("\n"):
        if not line.startswith("· ") or "（" not in line:
            continue
        m = re.match(
            r"^· (\S+?)（(\S)）：(\S+?)宫·(\S+) ([\d.]+)° · (\S+?)宿([\d度分]+)"
            r"(.*)$", line)
        if not m:
            continue
        rest = m.group(8)
        d = "顺" if "· 顺" in rest else ("逆" if "· 逆" in rest else "留")
        dig = ""
        for k in ("庙", "旺", "落", "弱"):
            if "· %s" % k in rest:
                dig = k
                break
        rel = ""
        rm = re.search(r"· \S（(\S)）", rest)
        if rm:
            rel = rm.group(1)
        wm = re.search(r"居(\S+?)$", line)
        zhi = m.group(3)
        gi = (10 - _QZ_ZHI.index(zhi)) % 12 if zhi in _QZ_ZHI else 0
        out.append({
            "full": m.group(1), "name": m.group(2), "zhi": zhi,
            "xingzuo": m.group(4), "lon": 30.0 * gi + float(m.group(5)),
            "su": m.group(6), "su_du": m.group(7), "dir": d,
            "dig": dig, "rel": rel, "wei": wm.group(1) if wm else "",
        })
    return out


def _for_qizheng(text: str) -> str:
    if "## 七政四余" not in (text or ""):
        return ""
    ming_zhi = _grab(text, r"\*\*命宫\*\* (\S+?)宫·")
    ming_xz = _grab(text, r"\*\*命宫\*\* \S+?宫·(\S+?)（")
    ming_ci = _grab(text, r"\*\*命宫\*\* \S+?宫·\S+?（(\S+?)）")
    du_su = _grab(text, r"命度 (\S+?)宿(\S+?)　")
    du_du = _grab(text, r"命度 \S+?宿([\d度分]+)")
    ming_ruler = _grab(text, r"命宫主 (\S)")
    du_zhu = _grab(text, r"命度主 (\S)")
    shen_zhi = _grab(text, r"\*\*身宫\*\* (\S+?)宫")
    shen_xz = _grab(text, r"\*\*身宫\*\* \S+?宫·(\S+)")

    ps = _qz_parse_planets(text)
    if not ps and not ming_zhi:
        return ""
    by = {p["name"]: p for p in ps}
    sun, moon = by.get("日"), by.get("月")

    # 命宫所坐星曜
    sit = _grab(text, r"· 命宫（[^）]*）：(\S+?)\n")
    sit_list = [] if sit in ("", "空") else [s for s in sit.split("、") if s]

    wx_name = {"木": "木", "火": "火", "土": "土", "金": "金", "水": "水"}
    d_wx = wx_name.get(ming_ruler, "")
    d_char = _QZ_WX_CHAR.get(d_wx, ("", ""))[0]
    d_how = _QZ_WX_CHAR.get(d_wx, ("", ""))[1]
    du_wx = wx_name.get(du_zhu, "")
    du_char = _QZ_WX_CHAR.get(du_wx, ("", ""))[1]

    # 命宫主所在状态
    mr = by.get(ming_ruler)
    mr_txt = ""
    if mr:
        st = mr["dig"] or "平"
        tone = {"庙": "入庙，力足且正", "旺": "得旺，力足而显",
                "落": "落陷，力弱需借势", "弱": "处弱，力薄宜守",
                "平": "不入庙旺，看同宫星曜补"}.get(st, "平和")
        mr_txt = (f"命宫主{mr['full']}居{mr['zhi']}宫·{mr['xingzuo']}"
                  f"（{st}，{tone}）")
    # 命度主
    dz = by.get(du_zhu)
    dz_txt = ""
    if dz:
        dz_txt = (f"命度躔{du_su}宿{du_du}，度主{du_zhu}"
                  f"在{dz['zhi']}宫·{dz['xingzuo']}"
                  f"（{dz['dig'] or '平'}）")
    elif du_zhu:
        dz_txt = f"命度躔{du_su}宿{du_du}，度主{du_zhu}"

    # 日月
    day_line = ""
    if sun and moon:
        sep = abs((sun["lon"] - moon["lon"] + 180.0) % 360.0 - 180.0)
        if sep < 12:
            ph = "日月同度，合朔之象，事多内敛、起于暗处"
        elif sep > 168:
            ph = "日月对望，望月之象，性情外显、易被看见"
        elif 80 <= sep <= 100:
            ph = "日月成弦，半明半暗，做事讲配合与节奏"
        else:
            ph = "日月不同宫，自我与情绪两路并行"
        day_line = (f"太阳在{sun['zhi']}宫·{sun['xingzuo']}、"
                    f"太阴在{moon['zhi']}宫·{moon['xingzuo']}，{ph}")

    # 恩用仇难
    groups = {"恩": [], "用": [], "难": [], "仇": []}
    for p in ps:
        if p["rel"] in groups:
            groups[p["rel"]].append(p["full"])
    rel_parts = []
    for k, label in (("恩", "恩（生我，助我）"), ("用", "用（我生，可使之）"),
                     ("难", "难（克我，耗我）"), ("仇", "仇（我克，须制之）")):
        if groups[k]:
            rel_parts.append(f"{label}：" + "、".join(groups[k]))
    rel_line = "；".join(rel_parts) if rel_parts else ""

    # 星最聚的宫
    cell = {}
    for p in ps:
        cell.setdefault(p["wei"], []).append(p["full"])
    heavy = sorted(((len(v), k) for k, v in cell.items() if k), reverse=True)
    heavy_line = ""
    if heavy and heavy[0][0] >= 2:
        cnt, wei = heavy[0]
        heavy_line = (f"{wei}宫聚了 {cnt} 星（"
                      + "、".join(cell[wei])
                      + f"），{_QZ_WEI_MEAN.get(wei, '这一块')}是你一生着力最多的地方")

    # 四余
    siyu = [p for p in ps if p["name"] in ("罗", "计", "孛", "气")]
    siyu_line = ""
    if siyu:
        siyu_line = "；".join(
            f"{p['full']}在{p['zhi']}宫（{p['wei']}）" for p in siyu)
        siyu_line += ("。四余无光象，主的是「说不清却一直在」的那股劲："
                      "罗计管截断与转折，月孛管情绪最深处的执，紫气管贵人式的顺风")

    paras = [
        _para("一句话",
              f"命立{ming_zhi}宫·{ming_xz}（{ming_ci}），命宫主{ming_ruler}"
              + (f"（{d_char}）" if d_char else "")
              + (f"；身宫落在{shen_zhi}宫·{shen_xz}" if shen_zhi else "")
              + "。七政四余看的是「日月的光、五政的力、四余的影」怎么落在十二宫上，"
                "不是单看一个星座。"),
        _para("命与命度",
              ("命宫坐" + "、".join(sit_list) + "，气性直接显在本人身上；"
               if sit_list else
               "命宫无曜，气性由宫主与命度主带出，做事多一层转折；")
              + "；".join([t for t in (mr_txt, dz_txt) if t])
              + ("。命宫主管你怎么活，命度主管理气从哪儿来——"
                 + (f"度主{du_zhu}：{du_char}" if du_char else "")
                 if (du_char or mr_txt or dz_txt) else "")),
        _para("日月两盏灯", day_line),
        _para("谁助你，谁耗你", rel_line or "盘中恩用仇难分布较均"),
        _para("星聚之处", heavy_line or "十一曜分布较散，人生没有一处被过度堆叠"),
        _para("四余的暗线", siyu_line or "四余无特别堆叠"),
        _para("怎么用",
              "七政四余的长处是「宿度」——同一颗星落在哪一宿哪一度，"
              "决定了它的性质偏哪边。看盘时先看命宫与命度，再看日月，"
              "最后才看哪颗星旺、哪颗星陷。它给的是倾向与着力点，不是判词。"),
    ]
    return _wrap("七政四余", paras)


# ---------------------------------------------------------------- 牌库批
def _card_parse(text: str, prefix: str):
    """解析「· [牌位] 牌名（…）— 牌义」格式的抽牌行。"""
    out = []
    for line in (text or "").split("\n"):
        if not line.startswith("· ["):
            continue
        m = re.match(
            r"^· \[(\S+?)\] (.+?)（([^（）]*)）\s*—\s*(.+?)$",
            line.strip())
        if m:
            name, num = m.group(2), None
            nm = re.match(r"^第(\d+)张 (.+)$", name)
            if nm:
                num, name = nm.group(1), nm.group(2)
            out.append({"pos": m.group(1), "name": name, "num": num,
                        "meta": m.group(3), "kw": m.group(4)})
    return out if not prefix or (text or "").startswith(prefix) else out


_TAROT_POS_HINT = {
    "过去": "已经发生、正在暗中垫底的部分",
    "现在": "当前最真实的处境",
    "未来": "顺着现在的惯性走下去最可能落到的位置",
    "障碍": "卡住这件事的那块石头",
    "建议": "牌面给到你的动作提示",
    "结果": "把建议做到位之后的终点",
    "核心": "这件事的题眼",
    "今日": "今天的主色调",
}


def _for_tarot(text: str) -> str:
    cards = _card_parse(text, "## 塔罗占卜")
    if not cards:
        return ""
    spread = _grab(text, r"## 塔罗占卜 · (\S+)")
    n_rev = sum(1 for c in cards if "逆位" in c["meta"])
    n_major = sum(1 for c in cards if "大阿尔卡纳" in c["meta"]
                  or c["name"] in ("愚者", "魔术师", "女祭司", "女皇", "皇帝",
                                   "教皇", "恋人", "战车", "力量", "隐士",
                                   "命运之轮", "正义", "倒吊人", "死神", "节制",
                                   "恶魔", "高塔", "星星", "月亮", "太阳",
                                   "审判", "世界"))
    paras = []

    if n_major >= len(cards) / 2 and len(cards) > 1:
        paras.append(_para(
            "牌面基调",
            "大牌占了多数——这件事背后推着它的多是「时势」而不是「细节」，"
            "你能调整的余地有限，顺势比硬拗省力。"))
    elif n_major == 0 and len(cards) > 1:
        paras.append(_para(
            "牌面基调",
            "全是小牌——事情落在日常柴米油盐的层面，"
            "谈不上什么大运，把手头每件小事做扎实就是全部答案。"))

    revs = [c for c in cards if "逆位" in c["meta"]]
    if len(cards) > 1:
        if n_rev == 0:
            paras.append(_para(
                "能量状态", "全员正位，牌面通畅没有内耗，"
                "现在说的话做的事都比平时更容易被听见、被接住。"))
        elif n_rev == len(cards):
            paras.append(_para(
                "能量状态", "全员逆位——不是「坏」，而是整个局面都处在"
                "反刍和内耗里，适合先收摊复盘，不适合开新局。"))
        elif n_rev > len(cards) / 2:
            paras.append(_para(
                "能量状态",
                f"逆位 {n_rev}/{len(cards)}，阻力多于顺力："
                "逆位的牌多是「该做没做」或「做过头」，对照牌义自查即可。"))

    for c in cards:
        hint = _TAROT_POS_HINT.get(c["pos"], "")
        if not hint:
            continue
        paras.append(_para(
            f"{c['pos']} · {c['name']}",
            f"这里看的是{hint}。牌面给出「{c['kw']}」——"
            + ("逆位提醒你别把这个能量用过头或用反了。"
               if "逆位" in c["meta"] else "照着这股劲走就好。")))

    if spread:
        paras.insert(0, _para("牌阵", f"{spread}，共 {len(cards)} 张。"))
    return _wrap("塔罗占卜", paras)


def _for_lenormand(text: str) -> str:
    cards = _card_parse(text, "## 雷诺曼")
    if not cards:
        return ""
    spread = _grab(text, r"## 雷诺曼 · (\S+)")
    paras = []
    if spread:
        paras.append(_para("读法",
                           f"{spread}，雷诺曼按卡线从左到右像造句一样连读，"
                           "相邻两张是修饰关系。"))
    # 两两连读
    for a, b in zip(cards, cards[1:]):
        paras.append(_para(
            f"{a['name']} → {b['name']}",
            f"「{a['kw'].split(' · ')[0]}」带动「{b['kw'].split(' · ')[0]}」："
            f"{a['name']}落在{a['pos']}，{b['name']}落在{b['pos']}，"
            "两者连起来读，前一张是因、后一张是果。"))
    # 关键卡提示
    heavy = {"棺材": "有件事到这里就翻篇了，别再刨",
             "山": "中间有堵墙，硬撞不如绕",
             "蛇": "过程有弯绕，留意身边言不由衷的人",
             "狐狸": "涉及饭碗与算计，合同条款看清再签",
             "老鼠": "正在悄悄漏——漏钱、漏精力或漏消息",
             "太阳": "结果比预期亮",
             "钥匙": "答案会自己浮出来，卡点会开",
             "十字": "该背的担子躲不掉，背稳了反而快"}
    for c in cards:
        if c["name"] in heavy:
            paras.append(_para(f"留意 · {c['name']}",
                               f"第{c['num']}张出现在「{c['pos']}」——"
                               + heavy[c["name"]] + "。"))
    return _wrap("雷诺曼", paras)


def _for_thaitarot(text: str) -> str:
    cards = _card_parse(text, "## 泰式塔罗")
    if not cards:
        return ""
    paras = []
    domains = []
    for c in cards:
        meta = c["meta"]
        paras.append(_para(
            f"{c['pos']} · {c['name']}",
            f"牌义「{c['kw']}」。"
            + ("逆位说明这股能量现在用反了或用猛了，先收着。"
               if "逆位" in meta else "这股能量此刻是顺的，可以借力。")))
    # 领域提示
    for line in (text or "").split("\n"):
        if line.strip().startswith("现实领域："):
            domains.append(line.split("：", 1)[1].strip())
    if domains:
        seen = []
        for d in domains:
            for part in d.split(" · "):
                if part and part not in seen:
                    seen.append(part)
        if seen:
            paras.append(_para(
                "现实落点", "这组牌主要照进你的「"
                + "、".join(seen[:4]) + "」，近期的注意力放这些地方最划算。"))
    return _wrap("泰式塔罗", paras)


_TEXT_HANDLERS = {
    "xiaoliuren": _for_xlr,
    "meihua": _for_meihua,
    "almanac": _for_almanac,
    "huangji": _for_huangji,
    "bazhai": _for_bazhai,
    "qimen": _for_qimen,
    "liuren": _for_liuren,
    "jinjue": _for_jinjue,
    "xuankong": _for_xuankong,
    "taiyi": _for_taiyi,
    "qizheng": _for_qizheng,
    "tarot": _for_tarot,
    "lenormand": _for_lenormand,
    "thaitarot": _for_thaitarot,
}


def for_text(mode: str, text: str) -> str:
    fn = _TEXT_HANDLERS.get(mode)
    if not fn:
        return ""
    try:
        return fn(text)
    except Exception:
        return ""


def attach(mode: str, text: str, ctx=None) -> str:
    """在工具输出后面追加本地解读；不支持的 mode 原样返回。"""
    try:
        if mode == "bazi" and isinstance(ctx, dict):
            body = for_bazi(ctx)
        elif mode == "ziwei" and isinstance(ctx, dict):
            body = for_ziwei(ctx)
        elif mode == "liuyao" and isinstance(ctx, dict):
            body = for_liuyao(ctx, (ctx.get("question") or ""))
        else:
            body = for_text(mode, text)
    except Exception:
        body = ""
    if not body:
        return text
    return f"{text}\n\n{body}"


# ---- 单文件别名(与 from ai_reading import ... 保持一致) ----
ai_attach = attach
ai_for_bazi = for_bazi
ai_for_ziwei = for_ziwei
