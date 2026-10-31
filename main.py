#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TianjiQbot —— 东方命理 · 术数 · 西方牌占 QQ 机器人

用法:
    python main.py

启动前配置环境变量（不要把密钥写进代码）:
    TIANJI_APPID / TIANJI_SECRET   QQ 开放平台机器人凭据（必填）
    TIANJI_SANDBOX=1               沙箱环境
    TIANJI_MARKDOWN=0              关闭 Markdown 回复
    TIANJI_COOLDOWN=5              群聊指令冷却秒数

指令示例（群里 @ 机器人）:
    八字 1990-05-20 14:30 男 北京
    紫微 1990-05-20 14:30 男 北京
    奇门 / 大六壬 / 金口诀 / 太乙 / 七政 / 玄空飞星
    六爻 3 3 3 3 3 3 / 梅花 3 5 午 / 八宅 1990 男 坐北朝南
    皇极经世 / 小六壬 / 黄历 / 宜忌 / 吉时 / 择日 2026-11
    观音灵签 / 称骨 1990-05-20 / 五行 1990-05-20 14:30 男 / 生肖 龙鸡
    塔罗 / 雷诺曼 / 泰式塔罗
"""
import asyncio
import base64
import re
import traceback

import botpy
from botpy.http import Route
from botpy.message import C2CMessage, GroupMessage, Message as ChannelMessage

from tianji.config import (APPID, SECRET, COOLDOWN_SECONDS, IS_SANDBOX,
                           MARKDOWN_TEMPLATE_ID, USE_MARKDOWN)

from tianji.bazi import BaziError, cast_chart, format_text, parse_birth_info
from tianji.ziwei import cast_ziwei, format_ziwei
from tianji.qimen import cast_qimen, format_qimen
from tianji.liuren import cast_liuren, format_liuren
from tianji.jinjue import cast_jinjue, format_jinjue
from tianji.xuankong import cast_xuankong, format_xuankong
from tianji.taiyi import cast_taiyi, format_taiyi
from tianji.qizheng import cast_qizheng, format_qizheng
from tianji.liuyao import liuyao, liuyao_from_arg
from tianji.meihua import meihua
from tianji.bazhai import bazhai
from tianji.huangji import huangji
from tianji.xiaoliuren import xiaoliuren
from tianji.huangli import almanac_today, jinri, jishi
from tianji.zeri import _jr_main as jiri, pofuchan
from tianji.lingqian import LQ_KEYWORDS, _lq_main as lingqian
from tianji.chenggu import chenggu
from tianji.wuxing import wuxingque
from tianji.shengxiao import shengxiao
from tianji.cards import cast_lenormand, cast_tarot, cast_thaitarot
from tianji.cards import format_lenormand, format_tarot, format_thaitarot

from tianji.ai_interpret import ai_for_bazi, attach
from tianji.render.charts import (render_chart_image, render_jinjue_card,
                                  render_liuren_card, render_qimen_card,
                                  render_qizheng_card, render_taiyi_card,
                                  render_xuankong_card, render_ziwei_card)
from tianji.render.decks import (render_lenormand_card, render_tarot_card,
                                 render_thaitarot_card)

VERSION = "1.0.0"

USAGE = (
    "【天玑 Qbot · 用法】@我 + 指令（指令前加 / 也可以）喵～\n"
    "八字 1990-05-20 14:30 男 北京\n"
    "紫微 1990-05-20 14:30 男 北京\n"
    "奇门 / 大六壬 / 金口诀 / 太乙神数 / 七政四余 / 玄空飞星 子山午向 8运\n"
    "六爻 3 3 3 3 3 3 / 梅花 3 5 午 / 八宅 1990 男 坐北朝南\n"
    "皇极经世 / 小六壬 / 黄历 / 今日宜忌 / 今日吉时 / 择日 2026-11 / 剖腹产 2026-11\n"
    "观音灵签 / 月老灵签 / 关帝灵签 … / 称骨 1990-05-20\n"
    "五行 1990-05-20 14:30 男 / 生肖配对 龙鸡\n"
    "塔罗 / 雷诺曼 / 泰式塔罗\n"
    "帮助 — 显示本菜单"
)

# ---------------------------------------------------------------------------
# 指令表: (关键词元组, 模式)。匹配时按关键词长度降序，避免短词吞长词。
# ---------------------------------------------------------------------------
COMMAND_TABLE = [
    (("奇门遁甲", "奇门"), "qimen"),
    (("大六壬", "六壬"), "liuren"),
    (("金口诀", "金口"), "jinjue"),
    (("玄空飞星", "玄空", "飞星"), "xuankong"),
    (("太乙神数", "太乙"), "taiyi"),
    (("七政四余", "七政", "果老", "星盘"), "qizheng"),
    (("紫微斗数", "紫微", "斗数"), "ziwei"),
    (("梅花易数", "梅花"), "meihua"),
    (("八宅风水", "八宅"), "bazhai"),
    (("六爻", "纳甲", "装卦"), "liuyao"),
    (("皇极经世", "值年卦", "皇极"), "huangji"),
    (("小六壬",), "xiaoliuren"),
    (("今日黄历", "黄历"), "almanac"),
    (("今日宜忌", "黄历宜忌", "老黄历", "宜忌"), "jinri"),
    (("时辰吉凶", "今日吉时", "吉时"), "jishi"),
    (("择日", "吉日"), "jiri"),
    (("剖腹产择日", "剖腹产"), "pofuchan"),
    (("称骨算命", "称骨"), "chenggu"),
    (("五行缺口", "五行"), "wuxing"),
    (("生肖配对", "生肖"), "shengxiao"),
    (("塔罗牌", "塔罗"), "tarot"),
    (("雷诺曼",), "lenormand"),
    (("泰式塔罗", "泰塔"), "thaitarot"),
    (("八字",), "bazi"),
    (("help", "帮助", "菜单", "指令"), "help"),
]

# 灵签关键词（长词在前）
_LQ_PAIRS = sorted(LQ_KEYWORDS, key=lambda kv: -len(kv[0]))

# XX吉日 → 事项归一化
_JIRI_EVENT = (("提车吉日", "提车"), ("搬家吉日", "搬家"), ("结婚吉日", "嫁娶"),
               ("婚嫁吉日", "嫁娶"), ("开业吉日", "开业"), ("开张吉日", "开业"),
               ("出行吉日", "出行"), ("装修吉日", "装修"), ("动土吉日", "装修"),
               ("领证吉日", "嫁娶"), ("黄道吉日", None))


def _clean_text(raw: str) -> str:
    text = re.sub(r"<@!?[0-9A-Za-z]+>|^@\S+\s*", "", raw or "")
    text = text.replace("\u200b", "").replace("\u200c", "").replace("\u200d", "")
    text = text.replace("\u3000", " ").strip()
    if text[:1] in ("/", "／", "＼"):
        text = text[1:].strip()
    return text


def match_command(raw: str):
    """返回 (mode, arg)；无法识别返回 None。"""
    text = _clean_text(raw).strip()
    if not text:
        return "help", ""
    # 灵签关键词优先（15 种签库名字较长）
    for kw, kind in _LQ_PAIRS:
        if text.startswith(kw):
            return "lingqian", text[len(kw):].strip()
    # XX吉日 归一化
    for kw, event in _JIRI_EVENT:
        if text.startswith(kw):
            rest = text[len(kw):].strip()
            return "jiri", (f"{event} {rest}".strip() if event else rest)
    best = None
    for kws, mode in COMMAND_TABLE:
        for kw in kws:
            if text == kw or text.startswith(kw):
                cand = (len(kw), mode, text[len(kw):].strip())
                if best is None or cand[0] > best[0]:
                    best = cand
    if best:
        return best[1], best[2]
    return None


# ---------------------------------------------------------------------------
# 各指令执行器: (文本, 图片字节或 None)
# ---------------------------------------------------------------------------
USAGE_TEXTS = {
    "bazi": "用法：八字 1990-05-20 14:30 男 北京（时间支持 14:30 / 下午3点半 / 申时）",
    "ziwei": "用法：紫微 1990-05-20 14:30 男 北京（农历亦可：紫微 农历1990年四月初三 未时 男）",
    "liuyao": "用法：六爻 3 3 3 3 3 3（六个 3-9 数字）或 六爻 3老阴5 3 3 3 3",
    "bazhai": "用法：八宅 1990 男 坐北朝南",
    "xuankong": "用法：玄空飞星 子山午向 8运",
    "jiri": "用法：择日 2026-11，或 提车吉日 2026-11 / 结婚吉日 2026-11",
    "pofuchan": "用法：剖腹产 2026-11",
    "chenggu": "用法：称骨 1990-05-20 14:30 男（或 农历1990年四月初三 申时）",
    "wuxing": "用法：五行 1990-05-20 14:30 男 北京",
    "shengxiao": "用法：生肖配对 龙鸡（或 属龙 属鸡）",
}


def _safe_image(fn, *args):
    """渲染失败不影响文字回复。"""
    try:
        return fn(*args).getvalue()
    except Exception:
        traceback.print_exc()
        return None


def run_mode(mode: str, arg: str):
    """执行指令，返回 (text, image_bytes | None)。arg 为空时用 "" 。"""
    if mode == "help":
        return USAGE, None
    if mode == "bazi":
        birth = parse_birth_info(arg)
        chart = cast_chart(birth)
        return attach("bazi", format_text(chart), chart), \
            _safe_image(render_chart_image, chart)
    if mode == "ziwei":
        chart = cast_ziwei(arg)
        return attach("ziwei", format_ziwei(chart), chart), \
            _safe_image(render_ziwei_card, chart)
    if mode == "qimen":
        chart = cast_qimen(arg)
        return attach("qimen", format_qimen(chart)), \
            _safe_image(render_qimen_card, chart)
    if mode == "liuren":
        chart = cast_liuren(arg)
        return attach("liuren", format_liuren(chart)), \
            _safe_image(render_liuren_card, chart)
    if mode == "jinjue":
        chart = cast_jinjue(arg)
        return attach("jinjue", format_jinjue(chart)), \
            _safe_image(render_jinjue_card, chart)
    if mode == "xuankong":
        chart = cast_xuankong(arg)
        return attach("xuankong", format_xuankong(chart)), \
            _safe_image(render_xuankong_card, chart)
    if mode == "taiyi":
        chart = cast_taiyi(arg)
        return attach("taiyi", format_taiyi(chart)), \
            _safe_image(render_taiyi_card, chart)
    if mode == "qizheng":
        chart = cast_qizheng(arg)
        return attach("qizheng", format_qizheng(chart)), \
            _safe_image(render_qizheng_card, chart)
    if mode == "liuyao":
        d = liuyao_from_arg(arg)
        d["question"] = ""
        return attach("liuyao", liuyao(arg, strict=True), d), None
    if mode == "meihua":
        return attach("meihua", meihua(arg)), None
    if mode == "bazhai":
        return attach("bazhai", bazhai(arg)), None
    if mode == "huangji":
        return attach("huangji", huangji(arg)), None
    if mode == "xiaoliuren":
        return attach("xiaoliuren", xiaoliuren(arg)), None
    if mode == "almanac":
        return attach("almanac", almanac_today(arg)), None
    if mode == "jinri":
        return jinri(arg), None
    if mode == "jishi":
        return jishi(arg), None
    if mode == "jiri":
        return jiri(arg), None
    if mode == "pofuchan":
        return pofuchan(arg), None
    if mode == "lingqian":
        return lingqian(arg), None
    if mode == "chenggu":
        return chenggu(arg), None
    if mode == "wuxing":
        return wuxingque(arg), None
    if mode == "shengxiao":
        return shengxiao(arg), None
    if mode == "tarot":
        c = cast_tarot(arg)
        return attach("tarot", format_tarot(c)), _safe_image(render_tarot_card, c)
    if mode == "lenormand":
        c = cast_lenormand(arg)
        return attach("lenormand", format_lenormand(c)), \
            _safe_image(render_lenormand_card, c)
    if mode == "thaitarot":
        c = cast_thaitarot(arg)
        return attach("thaitarot", format_thaitarot(c)), \
            _safe_image(render_thaitarot_card, c)
    return None, None


# ---------------------------------------------------------------------------
# QQ 消息回复工具
# ---------------------------------------------------------------------------
_PATTERN_TRAIL = re.compile(r"[\s!！?？。.,，、~～]+$")


def _to_markdown(text: str, title: str = "") -> str:
    lines = (text or "").split("\n")
    if not lines:
        return f"## {title}" if title else ""
    first = lines[0].strip()
    m = re.match(r"^【(.+?)】(.*)$", first)
    if m:
        head = m.group(1)
        rest = m.group(2).strip()
        lines[0] = f"## {head}" + (f" · {rest}" if rest else "")
    elif not first.startswith("#") and title:
        lines.insert(0, f"## {title}")
    for i, line in enumerate(lines):
        if line.startswith("※ "):
            lines[i] = "> " + line
    return "\n".join(lines)


async def send_markdown(message, title: str, content: str) -> bool:
    if not USE_MARKDOWN:
        return False
    try:
        md = {"content": _to_markdown(content, title)}
        if isinstance(message, ChannelMessage):
            await message.reply(markdown=md)
        else:
            await message.reply(msg_type=2, markdown=md)
        return True
    except Exception:
        return False


async def reply_text(message, text: str, title: str = "天玑 Qbot") -> None:
    if await send_markdown(message, title, text):
        return
    try:
        await message.reply(content=text)
    except Exception:
        traceback.print_exc()


async def upload_group_image(api, group_openid: str, img_bytes: bytes,
                             filename: str = "chart.png") -> str:
    route = Route("POST", "/v2/groups/{group_openid}/files", group_openid=group_openid)
    resp = await api._http.request(
        route,
        json={
            "file_type": 1,
            "file_name": filename,
            "file_data": base64.b64encode(img_bytes).decode("ascii"),
            "srv_send_msg": False,
        },
    )
    file_info = resp.get("file_info") if isinstance(resp, dict) \
        else getattr(resp, "file_info", None)
    if not file_info:
        raise RuntimeError(f"上传图片未返回 file_info, 响应: {resp}")
    return file_info


async def upload_c2c_image(api, user_openid: str, img_bytes: bytes,
                           filename: str = "chart.png") -> str:
    route = Route("POST", "/v2/users/{openid}/files", openid=user_openid)
    resp = await api._http.request(
        route,
        json={
            "file_type": 1,
            "file_name": filename,
            "file_data": base64.b64encode(img_bytes).decode("ascii"),
            "srv_send_msg": False,
        },
    )
    file_info = resp.get("file_info") if isinstance(resp, dict) \
        else getattr(resp, "file_info", None)
    if not file_info:
        raise RuntimeError(f"私聊上传图片未返回 file_info, 响应: {resp}")
    return file_info


# ---------------------------------------------------------------------------
# 机器人主体
# ---------------------------------------------------------------------------
class TianjiClient(botpy.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cooldown = {}

    def _cooldown_hit(self, key: str) -> bool:
        import time
        now = time.time()
        last = self._cooldown.get(key, 0)
        if now - last < COOLDOWN_SECONDS:
            return True
        self._cooldown[key] = now
        return False

    async def _handle(self, message, text_getter):
        raw = text_getter(message)
        hit = match_command(raw)
        if not hit:
            return
        mode, arg = hit
        if mode != "help":
            key = getattr(message, "group_openid", None) or \
                getattr(message.author, "user_openid", None) or \
                getattr(message.author, "id", "anon")
            if self._cooldown_hit(key):
                return
        try:
            text, img = run_mode(mode, arg)
        except BaziError as exc:
            await reply_text(message, f"输入有点问题喵：\n{exc}\n\n{USAGE_TEXTS.get(mode, USAGE)}",
                             "参数提示")
            return
        except ValueError as exc:
            await reply_text(message, f"输入有点问题喵：{exc}\n\n{USAGE_TEXTS.get(mode, USAGE)}",
                             "参数提示")
            return
        except Exception as exc:
            traceback.print_exc()
            await reply_text(message,
                             f"排盘出错了喵（{type(exc).__name__}）：{exc}",
                             "运行错误")
            return
        if img:
            try:
                if isinstance(message, GroupMessage):
                    file_info = await upload_group_image(
                        self.api, message.group_openid, img, f"{mode}.png")
                elif isinstance(message, C2CMessage):
                    file_info = await upload_c2c_image(
                        self.api, message.author.user_openid, img, f"{mode}.png")
                else:
                    file_info = None
                if file_info:
                    await message.reply(msg_type=7,
                                        media={"file_info": file_info}, msg_seq=1)
                    await reply_text(message, text, "解读")
                    return
                if isinstance(message, ChannelMessage):
                    await message.reply(file_image=img)
                    await reply_text(message, text, "解读")
                    return
            except Exception:
                traceback.print_exc()
        await reply_text(message, text, "解读")

    async def on_group_at_message_create(self, message: GroupMessage):
        await self._handle(message, lambda m: m.content)

    async def on_c2c_message_create(self, message: C2CMessage):
        await self._handle(message, lambda m: m.content)

    async def on_at_message_create(self, message: ChannelMessage):
        await self._handle(message, lambda m: m.content)


if __name__ == "__main__":
    if not APPID or not SECRET:
        raise SystemExit(
            "缺少机器人凭据：请先设置环境变量 TIANJI_APPID 与 TIANJI_SECRET 喵～")
    print("=" * 52)
    print(f"天玑 Qbot v{VERSION} 启动中 ...")
    print("群里 @ 机器人：直接 @ 可看菜单，或发『八字 ...』排盘")
    print("=" * 52)
    try:
        client = TianjiClient(
            intents=botpy.Intents(public_guild_messages=True, public_messages=True),
            is_sandbox=IS_SANDBOX,
        )
        client.run(appid=APPID, secret=SECRET)
    except KeyboardInterrupt:
        print("\n已手动停止。")
    except Exception:
        traceback.print_exc()
