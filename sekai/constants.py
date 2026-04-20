"""常量、提示词、帮助文本——纯声明，无副作用。"""

from __future__ import annotations

# 卡图：sekai.best CDN 上的大图（特训前 / 特训后）。
# 仅 rarity_3 / rarity_4 同时存在特训后图，其它稀有度只发特训前。
RARITIES_WITH_AFTER_TRAINING = frozenset({"rarity_3", "rarity_4"})

# 翻译相关常量
TRANSLATE_CHUNK_MAX_CHARS = 2000
TRANSLATE_CHUNK_SLEEP = 0.2  # 分块之间的短暂 sleep，避免压垮提供商

# 合并转发相关：目前 AstrBot 原生支持 Node/Nodes 的平台（见源码 sources/）
SUPPORTS_FORWARD_PLATFORMS = frozenset({"aiocqhttp", "satori"})
FORWARD_NODE_NAME = "Sekai"
FORWARD_NODE_UIN = "2854196310"

SYS_PROMPT_CARD_TITLE = (
    "你是一名专业的日译中译者，擅长 Project Sekai（世界计划/プロセカ）"
    "相关文本翻译。请将用户给的卡面日文标题翻译成中文，保留原意与风格，"
    "用简体中文输出，只输出译文本体，不要添加解释、括号或引号。"
)

SYS_PROMPT_SCENARIO = (
    "你是一名专业的日译中译者，熟悉 Project Sekai（世界计划 / プロセカ）的世界观"
    "与角色口癖。请把用户给的日文剧情脚本翻译成自然、流畅的简体中文。"
    "严格遵守以下规则：\n"
    "1. 保留原脚本的行结构。每一行都要原样对应一行输出，不要合并或拆分行。\n"
    "2. 对话行的格式为 `角色名：对白`，请把角色名也翻译成中文（如 ミク→初音未来、"
    "KAITO→KAITO、絵名→绘名、まふゆ→真冬、奏→奏 等），冒号使用全角 `：`。\n"
    "3. 没有冒号的行是场景标题或旁白，直接翻译即可，保持独立成行。\n"
    "4. 原文中的换行符 `\\N` 必须原样保留，不要替换为真实换行。\n"
    "5. 空行必须保留为空行。\n"
    "6. 只输出翻译结果本体，不要添加任何解释、前后缀或标注。"
)

HELP_TEXT = (
    "🎴 Sekai 卡牌剧情插件　使用说明\n"
    "指令组：/skcd（别名 /sekai_card）\n"
    "\n"
    "子指令：\n"
    "  • /skcd card <卡牌ID> [translate]\n"
    "      拉取指定卡牌的卡面信息，以及前篇 / 后篇角色剧情（.txt 附件）。\n"
    "      例：/skcd card 1275\n"
    "          /skcd card 1275 true   # 额外输出中文译名与译文\n"
    "\n"
    "  • /skcd event <活动ID> [角色昵称] [translate]\n"
    "      不带角色昵称：输出活动概览与活动卡牌列表。\n"
    "      带角色昵称：输出该活动中该角色的卡面信息与剧情。\n"
    "      例：/skcd event 202\n"
    "          /skcd event 202 miku\n"
    "          /skcd event 202 miku true\n"
    "\n"
    "  • /skcd help\n"
    "      输出本帮助信息。\n"
    "\n"
    "参数说明：\n"
    "  translate 接受 true/false/yes/no/1/0，省略则为 false。\n"
    "  角色昵称支持常见罗马音 / 中日文名（如 miku、saki、冬弥、绘名 等）。\n"
    "\n"
    "Made by Cinea"
)
