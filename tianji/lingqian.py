"""灵签（观音/月老/关帝/财神/黄大仙/车公/吕祖等十五签库）。"""

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


def _lq_hash(*parts) -> int:
    import hashlib
    h = hashlib.md5("|".join(str(p) for p in parts).encode()).hexdigest()
    return int(h[:8], 16)


def _lq_today() -> str:
    from datetime import date as _lq_date
    return _lq_date.today().isoformat()


# ---------------------------------------------------------------- 签种
# 键: (名称, 签数, 神祇一句话)
_LQ_KINDS = {
    "guanyin": ("观音灵签", 100, "大悲观世音菩萨，慈悲第一"),
    "guandi": ("关帝灵签", 100, "关圣帝君，忠义千秋"),
    "lvzu": ("吕祖灵签", 100, "纯阳吕祖，点化迷津"),
    "huangdaxian": ("黄大仙灵签", 100, "赤松黄大仙，有求必应"),
    "yuelao": ("月老灵签", 100, "月下老人，专司姻缘"),
    "mazu": ("妈祖灵签", 60, "天上圣母，护航济世"),
    "chegong": ("车公灵签", 96, "车大元帅，转危为安"),
    "tudigong": ("土地公灵签", 60, "福德正神，守望一方"),
    "baosheng": ("保生大帝灵签", 60, "保生大帝，妙手济人"),
    "fozu": ("佛祖灵签", 100, "释迦文佛，觉海慈航"),
    "jiazi": ("六十甲子签", 60, "六十甲子太岁，岁君值年"),
    "zhuge": ("诸葛神数", 215, "武侯诸葛亮，神机妙算"),
    "lingqi": ("灵棋经", 125, "灵棋十二棋，古卜遗法"),
    "zaojun": ("灶君灵签", 50, "东厨司命，察一家善恶"),
    "wanggong": ("王公灵签", 60, "王公大使，灵验闽南"),
}

# 触发词（长词在前，main.py 按序匹配）；值对应 _LQ_KINDS 键
LQ_KEYWORDS = (
    ("观音灵签", "guanyin"), ("观音签", "guanyin"), ("观音签诗", "guanyin"),
    ("关帝灵签", "guandi"), ("关公灵签", "guandi"), ("关帝签", "guandi"),
    ("吕祖灵签", "lvzu"), ("吕祖签", "lvzu"),
    ("黄大仙灵签", "huangdaxian"), ("黄大仙签", "huangdaxian"),
    ("月老灵签", "yuelao"), ("月老签", "yuelao"),
    ("妈祖灵签", "mazu"), ("天后灵签", "mazu"), ("妈祖签", "mazu"),
    ("车公灵签", "chegong"), ("车公签", "chegong"),
    ("土地公灵签", "tudigong"), ("土地公签", "tudigong"),
    ("保生大帝灵签", "baosheng"), ("保生灵签", "baosheng"),
    ("佛祖灵签", "fozu"), ("佛祖签", "fozu"),
    ("六十甲子签", "jiazi"), ("甲子签", "jiazi"),
    ("诸葛神数", "zhuge"), ("诸葛签", "zhuge"),
    ("灵棋经", "lingqi"), ("灵棋", "lingqi"),
    ("灶君灵签", "zaojun"), ("灶君签", "zaojun"),
    ("王公灵签", "wanggong"), ("王公签", "wanggong"),
    ("灵签", None), ("求签", None), ("抽签", None),
)

# ---------------------------------------------------------------- 签诗池
# 上吉池（上上/上签取用）
_LQ_POEM_GOOD = (
    ("天开地辟结良缘", "日吉时良万物全", "若得此签非小可", "人行忠正帝王宣"),
    ("春来花发映枝红", "万里舟行快便风", "若问前程归宿地", "安然自在乐融融"),
    ("宝剑新磨出匣鸣", "寒光凛凛鬼神惊", "从今斩断前程路", "直上青云万里程"),
    ("旭日东升照九州", "祥云拥护凤麟洲", "求谋遂意皆成就", "福禄双全到白头"),
    ("云开月出正分明", "恰似诗人得句成", "谋望从今皆遂意", "喜事重重福自生"),
    ("金榜题名姓字扬", "春风得意马蹄香", "婚姻财帛皆如意", "更喜田蚕六畜旺"),
    ("枯木逢春发新枝", "久旱甘霖润故池", "塞上翁来非是祸", "否去泰来正当时"),
    ("朝来喜鹊噪檐前", "报到佳音在目前", "求名求利皆如意", "更有灾消福自绵"),
    ("鲲鹏展翅九万里", "长风破浪会有时", "直挂云帆济沧海", "功成名就两相宜"),
    ("月到中秋分外明", "清光皎皎照人情", "一年好事今圆就", "从此家门百事兴"),
    ("瓜熟蒂落自圆成", "水到渠成不用惊", "自古好心天照管", "善缘结处福随行"),
    ("雪尽梅开春意浓", "冰消冻解暖融融", "从前苦处今甜处", "苦尽甘来处处通"),
)
# 中平池
_LQ_POEM_MID = (
    ("行藏出入礼义恭", "言必忠信志必从", "欲问前程归远处", "且守本分莫匆匆"),
    ("舟行风静浪微惊", "两岸桃花夹水明", "莫嫌路远程途缓", "缓到终须事竟成"),
    ("花开花谢自有时", "莫怨东风惜别离", "守己安心贫亦乐", "贪求无益反招非"),
    ("雾锁山头山锁雾", "天连水尾水连天", "眼前迷处心休急", "拨雾终能见日边"),
    ("二人同行未怀疑", "一腔心事两谁知", "目前得失休萦怀", "岁月悠悠自有期"),
    ("耕耘半载未见功", "禾黍低头渐有风", "休叹时乖名利薄", "秋来还有一分丰"),
    ("云中白鹤困樊笼", "羽翼虽丰未遇风", "且待春风消息动", "一声鸣处九霄冲"),
    ("月过十五光明少", "人到中年万事和", "安分守常灾自远", "强求反致起风波"),
    ("静里乾坤大似天", "闲中日月乐无边", "求名求利须迟缓", "缓处安身福自绵"),
    ("路入中途景更新", "一山放过一山迎", "初心不改终须达", "莫为浮云蔽眼睛"),
    ("潮平两岸阔无风", "稳驾轻舟缓缓行", "急处未必先到岸", "从容反得渡前程"),
    ("园中花木渐凋零", "根固枝存来岁春", "守得旧时基业在", "再修功德待时新"),
)
# 下签池
_LQ_POEM_BAD = (
    ("风急浪高舟莫行", "前途暗处有礁横", "不如守旧安家坐", "免教劳心损此生"),
    ("云遮月暗夜沉沉", "跋涉崎岖路难寻", "君子此时当守静", "小人妄动祸相侵"),
    ("莫听闲言是与非", "是非到底只因吹", "守口如瓶风波息", "一步错时万事灰"),
    ("满树花开结实稀", "虚名虚利两难齐", "劝君莫作痴心梦", "脚踏实地免伤悲"),
    ("井底观天所见偏", "坐井言天岂得全", "识见未开心勿躁", "更须修省待明年"),
    ("秋后寒蝉声渐低", "名利无意漫相思", "不如且把心头事", "付与东流一带溪"),
    ("行船失了水浮洲", "进退两难心自忧", "凡事从今休妄想", "只宜守旧渡春秋"),
    ("霜降花残叶又凋", "严冬未过雪还飘", "穷通自有天支配", "忍过寒冬春便朝"),
    ("镜里恩情梦里身", "镜花水月总非真", "劝君莫向虚中觅", "守取真诚自安贫"),
    ("狂风骤雨打芭蕉", "屋漏偏逢连夜潮", "此时诸事宜安忍", "躁进徒然惹祸苗"),
    ("破网临江鱼不来", "空劳心力费疑猜", "且须守分安贫过", "好运来时门自开"),
    ("枯池水浅草枯黄", "鱼不能游鸟不翔", "静守寒潭清到底", "莫贪浮利惹灾殃"),
)

# ---------------------------------------------------------------- 典故
_LQ_STORIES = (
    "太公钓渭", "苏秦刺股", "三顾茅庐", "韩信登坛", "子牙弃官",
    "孟尝君还珠", "李太白醉写", "精卫填海", "张骞乘槎", "岳飞精忠",
    "渭水访贤", "断桥相会", "桃园结义", "李白捞月", "玄德闻雷",
    "班超投笔", "朱买臣负薪", "司马题桥", "匡衡凿壁", "吕蒙正守困",
    "姜维伐魏", "周公解梦", "石崇巨富", "萧何月下追韩信",
)

# ---------------------------------------------------------------- 解曰
# 六维断语：吉 / 平 / 谨慎 三档
_LQ_ADVICE = {
    "求财": {
        "吉": ("财源广进，正财偏财皆有份", "利在东方，秋冬更旺"),
        "平": ("财有小得，不宜贪多", "守财为主，投机莫问"),
        "谨慎": ("破耗之象，谨防借贷担保", "财不入急门，安分度日"),
    },
    "功名": {
        "吉": ("科甲有望，名列前茅", "贵人提携，升迁在即"),
        "平": ("功名尚需时日，厚积薄发", "勤修学业，缓图进取"),
        "谨慎": ("名途阻滞，另辟蹊径为宜", "时不我与，且蓄实力"),
    },
    "姻缘": {
        "吉": ("天赐良缘，花好月圆", "有情人终成眷属，宜速定"),
        "平": ("缘分未至，不可强求", "现缘平淡，用心经营则稳"),
        "谨慎": ("情多波折，慎防口舌是非", "缘浅莫贪，聚散随缘"),
    },
    "健康": {
        "吉": ("安康如意，小恙自愈", "精神爽利，宜多动养身"),
        "平": ("旧疾宜复查，劳逸结合", "谨防季节小病，注意饮食"),
        "谨慎": ("病符当值，有病早医莫讳疾", "心宽是药，忌怒忌忧"),
    },
    "出行": {
        "吉": ("出行大吉，远行得利", "一路平安，贵人相助"),
        "平": ("可行，但早去早回", "行程有变数，宜订稳妥"),
        "谨慎": ("远行不利，能免则免", "路上谨慎，防盗防失"),
    },
    "家宅": {
        "吉": ("宅运昌隆，添丁进财", "家和万事兴，喜气盈门"),
        "平": ("宅运平稳，小修小补为宜", "门庭安泰，凡事商量"),
        "谨慎": ("宅有晦气，宜净宅安神", "慎防火烛口角，邻里相让"),
    },
}

_LQ_LEVELS = ("上上", "上吉", "中平", "下签", "下下")
# 档位→签诗池/断语档
_LQ_LEVEL_MAP = {"上上": ("g", "吉"), "上吉": ("g", "吉"), "中平": ("m", "平"),
                 "下签": ("b", "谨慎"), "下下": ("b", "谨慎")}
# 签号 hash → 等级（吉签占比约半，贴近真实灵签分布）
_LQ_LEVEL_BUCKETS = ((45, ("上上", "上吉")), (75, ("中平",)), (90, ("下签",)), (100, ("下下",)))

_LQ_YI = {
    "吉": ("行善布施", "签约谈事", "远行求财", "嫁娶开张", "搬迁动土"),
    "平": ("守旧安常", "多行善事", "量入为出", "静心读书"),
    "谨慎": ("安分守己", "修心积德", "检查身体", "关照家人"),
}
_LQ_JI = {
    "吉": "口舌争执、忘恩负义",
    "平": "贪心冒进、轻信人言",
    "谨慎": "远行冒险、官司担保、投机赌博",
}


def _lq_level(no: int) -> str:
    """签号→吉凶档。v∈1..100 落桶：≤45 上吉档 / ≤75 中平 / ≤90 下签 / 其余下下。"""
    v = _lq_hash("lv", no) % 100 + 1
    for top, levels in _LQ_LEVEL_BUCKETS:
        if v <= top:
            return levels[_lq_hash("lv2", no) % len(levels)]
    return "下下"


def _lq_pick(pool, no: int, salt: str):
    return pool[_lq_hash(salt, no) % len(pool)]


def _lq_draw(kind: str, no=None) -> str:
    """kind: _LQ_KINDS 键；no: 指定签号复核或 None=当日一签。"""
    name, total, desc = _LQ_KINDS[kind]
    today = _lq_today()
    if no is None:
        no = _lq_hash(kind, today) % total + 1
        drawn = True
    else:
        no = int(no) if str(no).strip().isdigit() else 0
        if not 1 <= no <= total:
            raise ValueError(f"{name}共 {total} 签，请填 1~{total} 的签号")
        drawn = False

    level = _lq_level(_lq_hash(kind, "base", no) % 10000 + no * 7)
    pool_key, grade = _LQ_LEVEL_MAP[level]
    pool = {"g": _LQ_POEM_GOOD, "m": _LQ_POEM_MID, "b": _LQ_POEM_BAD}[pool_key]
    poem = _lq_pick(pool, _lq_hash(kind, "base", no), "poem")
    story = _lq_pick(_LQ_STORIES, _lq_hash(kind, "base", no), "story")

    lines = [f"【{name} · 第{no}签 · {level}】"]
    if drawn:
        lines.append(f"（{_lq_today()} 当日一签 · 同日再求得同签）")
    lines.append("签诗：")
    lines += [f"　{ln}" for ln in poem]
    lines.append(f"典故：{story}")
    lines.append(f"神祇：{desc}")
    lines.append("解曰：" + {
        "上上": "大吉大利，谋望皆成，正是乘势而上时。",
        "上吉": "吉多凶少，求谋遂意，惟防得意忘形。",
        "中平": "不吉不凶，安分守常，耐心自有转机。",
        "下签": "凶多吉少，诸事谨慎，静守为宜。",
        "下下": "运势低迷，切忌妄动，修身积德待时来。",
    }[level])
    for dim, per in _LQ_ADVICE.items():
        opts = per[grade]
        lines.append(f"{dim}：{opts[_lq_hash(kind, no, dim) % len(opts)]}")
    yi_pool = _LQ_YI[grade]
    i1 = _lq_hash(kind, no, "yi") % len(yi_pool)
    i2 = (i1 + 1 + _lq_hash(kind, no, "yi2") % (len(yi_pool) - 1)) % len(yi_pool)
    lines.append(f"宜：{yi_pool[i1]}、{yi_pool[i2]}　忌：{_LQ_JI[grade]}")
    if drawn:
        lines.append("（复核：灵签 签号，如「观音灵签 23」）")
    return "\n".join(lines)


def _lq_list() -> str:
    lines = ["【灵签 · 十五签库】", "抽签：@机器人 观音灵签（当日一签）",
             "复核：@机器人 观音灵签 23（固定签文）", "—— 签库 ——"]
    for i, (name, total, _) in enumerate(_LQ_KINDS.values(), 1):
        lines.append(f"{i:>2}. {name}（{total}签）")
    lines.append("例：关帝灵签 / 月老灵签 7 / 黄大仙灵签 88")
    return "\n".join(lines)


def _lq_main(arg: str = "") -> str:
    """灵签入口。arg 可为空（列签库）、签种、签种+签号。"""
    t = (arg or "").strip()
    if not t:
        return _lq_list()
    # 分离尾部签号
    parts = t.split()
    no = None
    if len(parts) >= 2 and parts[-1].isdigit():
        no = int(parts[-1])
        t = " ".join(parts[:-1])
    t = t.replace("灵签签", "灵签").strip()
    for kw, kind in LQ_KEYWORDS:
        if t == kw or t.startswith(kw):
            rest = t[len(kw):].strip()
            if rest.isdigit():
                no = int(rest)
            return _lq_draw(kind or "guanyin", no)
    # 没匹配到签种但有数字 → 默认观音
    if no is not None:
        return _lq_draw("guanyin", no)
    raise ValueError("没认出签种～用法：观音灵签 / 关帝灵签 23 / 月老灵签 7（发「灵签」看十五签库）")


lingqian = _lq_main
