"""西方牌占：塔罗 78 张、雷诺曼 36 张、泰式塔罗的牌库与抽牌。"""

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


_RNG = random.SystemRandom()

# ---------------------------------------------------------------- 大阿尔卡纳
# (编号, 英文名, 中文名, 泰文名, 正位牌义, 逆位牌义, 现实领域)
TAROT_MAJOR = (
    (0, "The Fool", "愚者", "เดอะ ฟูล",
     "新的开始 · 自由 · 冒险 · 纯真", "鲁莽 · 幼稚 · 计划不周",
     "人生选择 · 新阶段"),
    (1, "The Magician", "魔术师", "เดอะ แมจิเชียน",
     "显化 · 资源在手 · 行动力 · 口才", "欺瞒 · 才华误用 · 空谈",
     "事业 · 谈判"),
    (2, "The High Priestess", "女祭司", "เดอะ ไฮพรีสเตส",
     "直觉 · 潜意识 · 秘密 · 静观", "忽视直觉 · 秘密浮出 · 迷茫",
     "内心 · 感情"),
    (3, "The Empress", "女皇", "เดอะ เอ็มเพรส",
     "丰饶 · 创造力 · 滋养 · 享受生活", "过度依赖 · 停滞 · 忽视自我",
     "感情 · 家庭 · 创作量产"),
    (4, "The Emperor", "皇帝", "เดอะ เอ็มเพอเรอร์",
     "权威 · 秩序 · 稳定 · 掌控局面", "专断 · 固执 · 体制僵化",
     "事业 · 管理层"),
    (5, "The Hierophant", "教皇", "เดอะ ไฮเออโรแฟนต์",
     "传统 · 导师指引 · 学习 · 正规渠道", "教条 · 破格 · 与体制冲突",
     "学业 · 婚礼 · 名分"),
    (6, "The Lovers", "恋人", "เดอะ เลิฟเวอร์ส",
     "结合 · 吸引 · 价值观契合 · 重要选择", "分歧 · 诱惑 · 关系失衡",
     "感情 · 合作"),
    (7, "The Chariot", "战车", "เดอะ แชริโอท",
     "胜利 · 意志 · 全速前进 · 掌握方向", "失控 · 受阻 · 强行推进",
     "竞争 · 出行"),
    (8, "Strength", "力量", "เดอะ สเตรงท์",
     "温柔的勇气 · 耐心 · 驯服冲动", "自我怀疑 · 力竭 · 情绪失控",
     "健康 · 心态"),
    (9, "The Hermit", "隐士", "เดอะ เฮอร์มิท",
     "内省 · 独处 · 寻求真理 · 长者智慧", "孤僻 · 逃避 · 自我封闭",
     "思考 · 深造"),
    (10, "Wheel of Fortune", "命运之轮", "วีล ออฟ ฟอร์จูน",
     "转机 · 周期轮转 · 时来运转", "逆势 · 时运不济 · 抗拒变化",
     "时运 · 机会"),
    (11, "Justice", "正义", "เดอะ จัสติส",
     "公平 · 因果分明 · 契约法律 · 权衡", "偏私 · 失衡 · 逃避责任",
     "诉讼 · 决断"),
    (12, "The Hanged Man", "倒吊人", "เดอะ แฮงด์แมน",
     "换位思考 · 暂停蓄势 · 有价值的牺牲", "徒劳拖延 · 白白牺牲 · 停滞",
     "等待 · 观念转变"),
    (13, "Death", "死神", "เดอะ เดธ",
     "结束与重生 · 转化 · 放手", "抗拒改变 · 拖延结束 · 旧事缠身",
     "转折 · 断舍离"),
    (14, "Temperance", "节制", "เดอะ เท็มเพอแรนซ์",
     "平衡 · 调和 · 耐心 · 中道", "失衡 · 走极端 · 缺乏耐心",
     "健康 · 关系磨合"),
    (15, "The Devil", "恶魔", "เดอะ เดวิล",
     "束缚 · 欲望 · 诱惑 · 沉迷上瘾", "挣脱束缚 · 觉察 · 断舍离",
     "坏习惯 · 消耗型关系"),
    (16, "The Tower", "高塔", "เดอะ ทาวเวอร์",
     "突变 · 结构崩塌 · 迫使觉醒", "勉强支撑 · 余震未平 · 惊魂未定",
     "突发 · 变故"),
    (17, "The Star", "星星", "เดอะ สตาร์",
     "希望 · 疗愈 · 灵感 · 长线信念", "失望 · 信心不足 · 理想褪色",
     "愿景 · 疗伤"),
    (18, "The Moon", "月亮", "เดอะ มูน",
     "潜意识 · 不安 · 幻象 · 直觉敏锐", "拨云见日 · 真相浮现 · 走出迷雾",
     "感情猜疑 · 局势不明"),
    (19, "The Sun", "太阳", "เดอะ ซัน",
     "喜悦 · 成功 · 活力 · 光明正大", "暂时阴霾 · 过度乐观 · 虚耗",
     "考试 · 名声 · 好消息"),
    (20, "Judgement", "审判", "เดอะ จัดจ์เมนต์",
     "觉醒 · 召唤 · 旧事清算 · 重生", "自我怀疑 · 逃避审判 · 错失召唤",
     "抉择 · 复合 · 复盘"),
    (21, "The World", "世界", "เดอะ เวิลด์",
     "完成 · 圆满 · 达成 · 整合收官", "未竟 · 差临门一脚 · 虎头蛇尾",
     "毕业 · 收尾 · 出国"),
)

_TAROT_MAJOR_BY_NUM = {c[0]: c for c in TAROT_MAJOR}

# ---------------------------------------------------------------- 小阿尔卡纳
# 每张按「元素 × 数字」独立写正逆位（黄金黎明口径，非查表拼接）。
# TAROT_MINOR[suit] = (元素, 领域, [(中文名, 英文名, 正位, 逆位), ... x14])
TAROT_MINOR = {
    "权杖": ("火 · 行动", "事业 · 行动 · 热情", (
        ("权杖王牌", "Ace of Wands", "新事业萌发 · 行动力满格 · 灵感点火",
         "计划搁浅 · 冲劲泄气 · 时机未到"),
        ("权杖二", "Two of Wands", "谋划大局 · 两案择一 · 立足看远",
         "畏首畏尾 · 错失扩张 · 守在原地"),
        ("权杖三", "Three of Wands", "事业展开 · 远见布局 · 跨域合作",
         "视野受限 · 合作生变 · 延误出航"),
        ("权杖四", "Four of Wands", "庆功安顿 · 根基已立 · 阶段圆满",
         "过渡不稳 · 庆典延后 · 内部松动"),
        ("权杖五", "Five of Wands", "竞争角力 · 意见相左 · 磨合练兵",
         "避免争端 · 和解契机 · 退出竞争"),
        ("权杖六", "Six of Wands", "得胜凯旋 · 众望所归 · 捷报传来",
         "胜而不稳 · 光环褪色 · 名声存疑"),
        ("权杖七", "Seven of Wands", "据守阵地 · 以寡敌众 · 捍卫成果",
         "力不从心 · 弃守退让 · 顾此失彼"),
        ("权杖八", "Eight of Wands", "事情提速 · 消息频传 · 一路绿灯",
         "延误阻塞 · 节奏乱掉 · 航班变动"),
        ("权杖九", "Nine of Wands", "坚持到底 · 警惕最后一里 · 带伤上阵",
         "心防崩溃 · 疲惫放弃 · 过度设防"),
        ("权杖十", "Ten of Wands", "负重前行 · 责任压身 · 临门苦撑",
         "卸下重担 · 学会放手 · 分工减负"),
        ("权杖侍从", "Page of Wands", "行动起手 · 热情探索 · 消息带来变化",
         "三分钟热度 · 消息反复 · 方向未定"),
        ("权杖骑士", "Knight of Wands", "勇往直前 · 热血远征 · 雷厉执行",
         "鲁莽冒进 · 半途而废 · 来去匆匆"),
        ("权杖王后", "Queen of Wands", "温暖坚定 · 行动有度 · 自信有魅力",
         "刚愎自用 · 顾此失彼 · 虚张声势"),
        ("权杖国王", "King of Wands", "高瞻远瞩 · 事业掌局 · 领袖魅力",
         "独断专行 · 滥用权柄 · 咄咄逼人"),
    )),
    "圣杯": ("水 · 情感", "感情 · 人际 · 内心", (
        ("圣杯王牌", "Ace of Cups", "心动开始 · 情感充盈 · 爱意萌生",
         "情感封闭 · 心动错付 · 空杯难满"),
        ("圣杯二", "Two of Cups", "两情相悦 · 彼此吸引 · 对等结合",
         "失衡冷战 · 貌合神离 · 缘分波动"),
        ("圣杯三", "Three of Cups", "欢聚庆祝 · 友谊升温 · 互助小团体",
         "三人成虎 · 乐极生悲 · 圈子是非"),
        ("圣杯四", "Four of Cups", "兴致缺缺 · 错受邀约 · 冷眼旁观",
         "重新出发 · 走出低潮 · 接受好意"),
        ("圣杯五", "Five of Cups", "哀悼失落 · 眼见所失 · 悔意难消",
         "释怀接纳 · 翻篇重来 · 珍视余下"),
        ("圣杯六", "Six of Cups", "旧忆重温 · 纯真善意 · 故人往事",
         "困于过去 · 旧情复燃 · 拒绝长大"),
        ("圣杯七", "Seven of Cups", "幻想纷杂 · 选项迷离 · 海市蜃楼",
         "拨云见日 · 认清所求 · 少即是多"),
        ("圣杯八", "Eight of Cups", "告别出走 · 寻觅意义 · 月下转身",
         "进退两难 · 欲走还留 · 逃避现实"),
        ("圣杯九", "Nine of Cups", "心想事成 · 愿望成真 · 惬意满足",
         "口蜜腹剑 · 满足表象 · 内里空虚"),
        ("圣杯十", "Ten of Cups", "阖家美满 · 情感圆满 · 终成眷属",
         "家庭失和 · 美满破灭 · 期望落空"),
        ("圣杯侍从", "Page of Cups", "心动讯息 · 浪漫萌芽 · 童心创意",
         "情绪幼稚 · 甜言失真 · 钝感伤人"),
        ("圣杯骑士", "Knight of Cups", "浪漫追求 · 乘兴而来 · 情书攻势",
         "花言巧语 · 不切实际 · 光说不练"),
        ("圣杯王后", "Queen of Cups", "温柔共情 · 善解人意 · 直觉灵敏",
         "情绪淹没 · 过度付出 · 边界失守"),
        ("圣杯国王", "King of Cups", "情绪稳定 · 包容成熟 · 以情服人",
         "情绪操控 · 外冷内乱 · 压抑爆发"),
    )),
    "宝剑": ("风 · 思维", "思维 · 沟通 · 冲突", (
        ("宝剑王牌", "Ace of Swords", "思路清明 · 真相破晓 · 一针见血",
         "思绪混乱 · 言辞伤人 · 计划流产"),
        ("宝剑二", "Two of Swords", "僵持不下 · 回避抉择 · 蒙眼平衡",
         "蒙眼决策 · 故作镇定 · 拖到爆雷"),
        ("宝剑三", "Three of Swords", "心碎之痛 · 言语扎心 · 揭穿真相",
         "疗愈开始 · 走出伤心 · 冰释前嫌"),
        ("宝剑四", "Four of Swords", "歇息静养 · 充电蓄力 · 暂停备战",
         "倦怠难眠 · 被迫停摆 · 静极思动"),
        ("宝剑五", "Five of Swords", "争胜伤和 · 得不偿失 · 惨胜如败",
         "化敌为友 · 放下胜负 · 旧账重提"),
        ("宝剑六", "Six of Swords", "渡过难关 · 渐行渐稳 · 移船靠岸",
         "旧事拖拽 · 行程波折 · 半途折返"),
        ("宝剑七", "Seven of Swords", "计谋暗行 · 有所隐瞒 · 声东击西",
         "东窗事发 · 自首坦白 · 弃暗投明"),
        ("宝剑八", "Eight of Swords", "自缚手脚 · 画地为牢 · 心障大于墙",
         "松绑破局 · 重获自由 · 出路就在眼前"),
        ("宝剑九", "Nine of Swords", "忧思难寐 · 噩梦缠身 · 想太多",
         "噩梦将醒 · 说出来就好 · 恐惧夸大"),
        ("宝剑十", "Ten of Swords", "谷底触底 · 尘埃落定 · 一了百了",
         "缓慢复苏 · 最糟已过 · 侥幸翻盘"),
        ("宝剑侍从", "Page of Swords", "消息灵通 · 观察学习 · 试探风向",
         "言语轻率 · 打探是非 · 键盘冒进"),
        ("宝剑骑士", "Knight of Swords", "雷厉风行 · 直冲要害 · 快刀斩麻",
         "言语激进 · 横冲直撞 · 欲速不达"),
        ("宝剑王后", "Queen of Swords", "清醒独立 · 洞若观火 · 界限分明",
         "冷言冷语 · 刻薄挑剔 · 防御过重"),
        ("宝剑国王", "King of Swords", "理性裁决 · 专业权威 · 令出如山",
         "独断冷酷 · 滥权苛断 · 强词夺理"),
    )),
    "星币": ("土 · 物质", "金钱 · 事业 · 现实", (
        ("星币王牌", "Ace of Pentacles", "财运开张 · 机会落地 · 种子钱",
         "错失良机 · 财务漏洞 · 画饼充饥"),
        ("星币二", "Two of Pentacles", "多线平衡 · 灵活调度 · 骑墙周转",
         "手忙脚乱 · 顾此失彼 · 拆东补西"),
        ("星币三", "Three of Pentacles", "技艺立身 · 协作成事 · 图纸落地",
         "各怀心思 · 配合失灵 · 半吊子活"),
        ("星币四", "Four of Pentacles", "守财稳健 · 安全感足 · 握紧不放",
         "过度守成 · 患得患失 · 被迫放血"),
        ("星币五", "Five of Pentacles", "拮据困顿 · 寒窗求援 · 身心俱疲",
         "渡过难关 · 援手将至 · 柳暗花明"),
        ("星币六", "Six of Pentacles", "慷慨给予 · 资源流动 · 有借有还",
         "施舍失衡 · 条件交换 · 恩成负担"),
        ("星币七", "Seven of Pentacles", "长线耕耘 · 静待收成 · 评估仓位",
         "急于求成 · 打水漂 · 前功尽弃"),
        ("星币八", "Eight of Pentacles", "匠心精进 · 埋头苦练 · 量产交付",
         "敷衍了事 · 半途而废 · 粗制滥造"),
        ("星币九", "Nine of Pentacles", "硕果自立 · 财务自由 · 优雅独处",
         "依赖成性 · 享受无度 · 面子工程"),
        ("星币十", "Ten of Pentacles", "家业丰隆 · 世代绵延 · 落袋为安",
         "家底动摇 · 遗产纠葛 · 长线断裂"),
        ("星币侍从", "Page of Pentacles", "学以致用 · 新机会萌芽 · 踏实起步",
         "学业分心 · 机会不实 · 眼高手低"),
        ("星币骑士", "Knight of Pentacles", "稳扎稳打 · 务实勤恳 · 慢即是快",
         "墨守成规 · 无聊乏味 · 原地打转"),
        ("星币王后", "Queen of Pentacles", "持家有道 · 务实温暖 · 事业家庭两顾",
         "操劳过度 · 物质焦虑 · 自我忽略"),
        ("星币国王", "King of Pentacles", "富而有成 · 稳坐江山 · 财脉通达",
         "贪得无厌 · 守财苛刻 · 物质至上"),
    )),
}

_TAROT_ALL = []  # (中文名, 英文名, 正位, 逆位, 元素领域, is_major, major_num)
for _c in TAROT_MAJOR:
    _TAROT_ALL.append({
        "name": _c[2], "en": _c[1], "up": _c[4], "rev": _c[5],
        "domain": _c[6], "major": True, "num": _c[0],
    })
for _suit, (_elem, _dom, _cards) in TAROT_MINOR.items():
    for _name, _en, _up, _rev in _cards:
        _TAROT_ALL.append({
            "name": _name, "en": _en, "up": _up, "rev": _rev,
            "domain": _dom, "major": False, "num": None,
        })

TAROT_SPREADS = {
    1: ("单张日运", ["今日"]),
    3: ("三牌阵", ["过去", "现在", "未来"]),
    5: ("五牌阵", ["过去", "现在", "障碍", "建议", "结果"]),
}


def cast_tarot(arg: str = "") -> dict:
    """抽塔罗牌。arg 可含牌数（单/3/5）与问题文本。"""
    arg = (arg or "").strip()
    n = 3
    question = ""
    low = arg.lower()
    if low.startswith("单") or low.startswith("日运") or low == "1":
        n = 1
        rest = arg[2:] if arg.startswith("日运") else arg[1:]
        question = rest.strip()
    elif low.startswith("3"):
        n = 3
        question = arg[1:].strip()
    elif low.startswith("5"):
        n = 5
        question = arg[1:].strip()
    else:
        question = arg

    cards = _RNG.sample(_TAROT_ALL, n)
    picked = []
    for pos, card in zip(TAROT_SPREADS[n][1], cards):
        rev = _RNG.random() < 0.5
        picked.append({
            "pos": pos, "name": card["name"], "en": card["en"],
            "major": card["major"], "num": card["num"],
            "reversed": rev, "kw": card["rev"] if rev else card["up"],
            "domain": card["domain"],
        })
    from datetime import datetime
    return {
        "spread": TAROT_SPREADS[n][0],
        "positions": TAROT_SPREADS[n][1],
        "question": question,
        "cards": picked,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def format_tarot(c: dict) -> str:
    lines = [f"## 塔罗占卜 · {c['spread']}", ""]
    if c["question"]:
        lines.append(f"**问题** {c['question']}")
        lines.append("")
    lines.append("牌位：" + " · ".join(c["positions"]))
    lines.append("")
    lines.append("**抽牌**")
    for p in c["cards"]:
        num = f"（{p['num']}）" if p["major"] else ""
        lines.append(
            f"· [{p['pos']}] {p['name']}{num}（{'逆位' if p['reversed'] else '正位'}）"
            f" — {p['kw']}"
        )
    n_rev = sum(1 for p in c["cards"] if p["reversed"])
    n_major = sum(1 for p in c["cards"] if p["major"])
    lines.append("")
    lines.append(f"正位 {len(c['cards']) - n_rev} · 逆位 {n_rev} · 大阿尔卡纳 {n_major} 张")
    lines.append(f"抽牌时间 {c['time']}")
    lines.append("")
    lines.append("（结果仅供文化娱乐参考）")
    return "\n".join(lines)


def tarot(arg: str = "") -> str:
    return format_tarot(cast_tarot(arg))


# ---------------------------------------------------------------- 雷诺曼 36
# (编号, 中文名, 英文名, 关键词)
LENORMAND_CARDS = (
    (1, "骑士", "Rider", "消息 · 来访 · 新动态"),
    (2, "三叶草", "Clover", "小幸运 · 短暂机会 · 赌一把"),
    (3, "船", "Ship", "旅程 · 远方 · 外贸生意"),
    (4, "房子", "House", "家庭 · 安稳 · 根基"),
    (5, "树", "Tree", "健康 · 缓慢成长 · 根性"),
    (6, "云", "Clouds", "困惑 · 不确定 · 阴霾"),
    (7, "蛇", "Snake", "复杂 · 背叛 · 迂回的女人"),
    (8, "棺材", "Coffin", "结束 · 疾病 · 告一段落"),
    (9, "花束", "Bouquet", "礼物 · 赞美 · 美好邀请"),
    (10, "镰刀", "Scythe", "突然 · 切割 · 果断决断"),
    (11, "鞭子", "Whip", "争执 · 反复 · 竞争博弈"),
    (12, "鸟", "Birds", "对话 · 紧张 · 七嘴八舌"),
    (13, "孩子", "Child", "新开始 · 天真 · 小事"),
    (14, "狐狸", "Fox", "狡猾 · 警惕 · 打工饭碗"),
    (15, "熊", "Bear", "力量 · 权威 · 大财 · 长辈"),
    (16, "星星", "Stars", "目标 · 指引 · 好运网络"),
    (17, "鹳", "Stork", "变迁 · 搬家 · 越变越好"),
    (18, "狗", "Dog", "朋友 · 忠诚 · 信任"),
    (19, "高塔", "Tower", "机构 · 官方 · 孤高"),
    (20, "花园", "Garden", "公共 · 社交 · 活动"),
    (21, "山", "Mountain", "阻碍 · 停滞 · 硬骨头"),
    (22, "十字路口", "Crossroads", "选择 · 岔路 · 多线并行"),
    (23, "老鼠", "Mice", "消耗 · 流失 · 焦虑啃噬"),
    (24, "心", "Heart", "爱情 · 善意 · 热忱"),
    (25, "戒指", "Ring", "承诺 · 契约 · 婚约"),
    (26, "书", "Book", "知识 · 秘密 · 考试深造"),
    (27, "信", "Letter", "文件 · 消息 · 白纸黑字"),
    (28, "男士", "Man", "男方 · 提问者本人（男）"),
    (29, "女士", "Woman", "女方 · 提问者本人（女）"),
    (30, "百合", "Lily", "安宁 · 成熟 · 长辈德行"),
    (31, "太阳", "Sun", "成功 · 能量 · 大胜"),
    (32, "月亮", "Moon", "名声 · 认可 · 情绪起伏"),
    (33, "钥匙", "Key", "突破 · 确定 · 答案揭晓"),
    (34, "鱼", "Fish", "财富 · 流动 · 生意兴隆"),
    (35, "锚", "Anchor", "稳定 · 坚持 · 长期饭票"),
    (36, "十字", "Cross", "命运 · 考验 · 不得不背"),
)

LENORMAND_LINES = {
    1: ("单张", ["今日"]),
    3: ("三卡线", ["过去", "现在", "未来"]),
    5: ("五卡线", ["过去", "现在", "核心", "建议", "结果"]),
}


def cast_lenormand(arg: str = "") -> dict:
    """抽雷诺曼卡。arg 可含卡数（单/3/5）与问题文本。"""
    arg = (arg or "").strip()
    n = 3
    question = ""
    low = arg.lower()
    if low.startswith("单") or low == "1":
        n = 1
        question = arg[1:].strip()
    elif low.startswith("3"):
        n = 3
        question = arg[1:].strip()
    elif low.startswith("5"):
        n = 5
        question = arg[1:].strip()
    else:
        question = arg

    idxs = _RNG.sample(range(36), n)
    picked = []
    for pos, i in zip(LENORMAND_LINES[n][1], idxs):
        num, name, en, kw = LENORMAND_CARDS[i]
        picked.append({"pos": pos, "num": num, "name": name, "en": en, "kw": kw})
    from datetime import datetime
    return {
        "spread": LENORMAND_LINES[n][0],
        "positions": LENORMAND_LINES[n][1],
        "question": question,
        "cards": picked,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def format_lenormand(c: dict) -> str:
    lines = [f"## 雷诺曼 · {c['spread']}", ""]
    if c["question"]:
        lines.append(f"**问题** {c['question']}")
        lines.append("")
    for p in c["cards"]:
        lines.append(f"· [{p['pos']}] 第{p['num']}张 {p['name']}（{p['en']}）— {p['kw']}")
    lines.append("")
    lines.append("雷诺曼不设逆位，按卡线从左到右连读。")
    lines.append(f"抽卡时间 {c['time']}")
    lines.append("")
    lines.append("（结果仅供文化娱乐参考）")
    return "\n".join(lines)


def lenormand(arg: str = "") -> str:
    return format_lenormand(cast_lenormand(arg))


# ---------------------------------------------------------------- 泰式塔罗
# 复用大阿尔卡纳 22 张，突出泰文牌名与现实领域。
_THAI_DOMAIN = {c[0]: c[6] for c in TAROT_MAJOR}


def cast_thaitarot(arg: str = "") -> dict:
    """抽泰式塔罗（默认单张，可 3 张）。"""
    arg = (arg or "").strip()
    n = 1
    question = ""
    low = arg.lower()
    if low.startswith("3"):
        n = 3
        question = arg[1:].strip()
    elif low:
        question = arg

    cards = _RNG.sample(TAROT_MAJOR, n)
    picked = []
    for pos, card in zip(["今日"] if n == 1 else ["过去", "现在", "未来"], cards):
        rev = _RNG.random() < 0.5
        picked.append({
            "pos": pos, "num": card[0], "en": card[1], "name": card[2],
            "thai": card[3], "reversed": rev,
            "kw": card[5] if rev else card[4], "domain": card[6],
        })
    from datetime import datetime
    return {
        "n": n, "question": question, "cards": picked,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def format_thaitarot(c: dict) -> str:
    lines = ["## 泰式塔罗", ""]
    if c["question"]:
        lines.append(f"**问题** {c['question']}")
        lines.append("")
    for p in c["cards"]:
        lines.append(
            f"· [{p['pos']}] {p['thai']} · {p['name']}"
            f"（{p['en']}，第{p['num']}张，{'逆位' if p['reversed'] else '正位'}）"
            f" — {p['kw']}"
        )
        lines.append(f"  现实领域：{p['domain']}")
    lines.append("")
    lines.append(f"抽牌时间 {c['time']}")
    lines.append("")
    lines.append("（结果仅供文化娱乐参考）")
    return "\n".join(lines)


def thaitarot(arg: str = "") -> str:
    return format_thaitarot(cast_thaitarot(arg))
