"""astrbot_plugin_sekai_card - Project Sekai 卡牌信息 & 剧情导出插件。

指令：
    /skcd card <card_id> [translate]
    /skcd event <event_id> [character] [translate]

    旧的 /sekai_card 作为 alias 保留，也可写作
    /sekai_card card 1275 或 /sekai_card event 202 miku。

功能：
    1. 拉取指定卡牌的基础信息并作为文本消息发送。
    2. 拉取该卡牌的前篇/后篇剧情脚本，渲染为纯文本并作为 txt 文件发送。
    3. 对于活动 (event) 指令，列出活动信息并可选择某位角色的活动卡牌，
       输出其卡面信息与剧情。
    4. （可选）当 translate 参数为真（true/yes/1）时，调用 AstrBot 当前
       LLM 提供商翻译卡名和剧情，额外输出中文版本。
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

from .sekai.characters import resolve_character_id
from .sekai.client import SekaiClient
from .sekai.formatter import format_card_info, format_scenario

# 翻译相关常量
_TRANSLATE_CHUNK_MAX_CHARS = 2000
_TRANSLATE_CHUNK_SLEEP = 0.2  # 分块之间的短暂 sleep，避免压垮提供商

_SYS_PROMPT_CARD_TITLE = (
    "你是一名专业的日译中译者，擅长 Project Sekai（世界计划/プロセカ）"
    "相关文本翻译。请将用户给的卡面日文标题翻译成中文，保留原意与风格，"
    "用简体中文输出，只输出译文本体，不要添加解释、括号或引号。"
)

_SYS_PROMPT_SCENARIO = (
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

# 文件名安全字符：字母数字下划线、CJK 统一表意、平假名、片假名
_FILENAME_SAFE_RE = re.compile(r"[^\w\-\u3040-\u30ff\u4e00-\u9fff]+", re.UNICODE)

_JST = timezone(timedelta(hours=9))


@register(
    "astrbot_plugin_sekai_card",
    "Cinea4678",
    "从 sekai.best 拉取 Project Sekai 卡牌 / 活动信息与角色剧情并输出文本。",
    "0.3.0",
    "https://github.com/Cinea4678/astrbot_plugin_sekai_card",
)
class SekaiCardPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.config = config
        self._client = SekaiClient(
            cache_ttl=int(self.config.get("cache_ttl_seconds", 3600) or 3600),
            timeout=int(self.config.get("http_timeout_seconds", 30) or 30),
        )
        self._data_dir: Path = StarTools.get_data_dir("astrbot_plugin_sekai_card")
        self._data_dir.mkdir(parents=True, exist_ok=True)

    # -----------------------------
    # 指令组：/skcd（别名 /sekai_card）
    # -----------------------------
    @filter.command_group("skcd", alias={"sekai_card"})
    def skcd(self):
        """Sekai 卡牌 / 活动指令组。

        子指令：
          card  <卡牌ID> [translate]
          event <活动ID> [角色昵称] [translate]
        """

    # -----------------------------
    # 子指令：/skcd card
    # -----------------------------
    @skcd.command("card")
    async def cmd_card(
        self,
        event: AstrMessageEvent,
        card_id: int | None = None,
        translate: bool = False,
    ):
        """/skcd card <卡牌ID> [translate]

        拉取卡牌信息与前/后篇剧情。translate 传 true/yes/1 时，会额外输出中文译名与译文。
        """
        if card_id is None:
            yield event.plain_result(
                "用法：/skcd card <卡牌ID> [translate]，例如 /skcd card 1275 true"
            )
            return

        async for msg in self._handle_card(event, card_id, translate):
            yield msg

    # -----------------------------
    # 子指令：/skcd event
    # -----------------------------
    @skcd.command("event")
    async def cmd_event(
        self,
        event: AstrMessageEvent,
        event_id: int | None = None,
        character: str | None = None,
        translate: bool = False,
    ):
        """/skcd event <活动ID> [角色昵称] [translate]

        不带角色时输出活动信息与卡牌列表；带角色时输出该活动中该角色的卡面 & 剧情。
        支持昵称如 miku / saki / toya / 冬弥 等，详见 README。
        """
        if event_id is None:
            yield event.plain_result(
                "用法：/skcd event <活动ID> [角色昵称] [translate]，例如 /skcd event 202 miku"
            )
            return

        yield event.plain_result(f"正在拉取活动 {event_id} 的信息……")

        try:
            events, event_cards = await self._client.fetch_event_data()
            cards, episodes, characters = await self._client.fetch_master_data()
        except Exception as e:  # noqa: BLE001
            logger.exception("[sekai_card] 拉取主数据失败")
            yield event.plain_result(f"拉取 sekai 主数据失败：{e}")
            return

        ev = _find_by_id(events, event_id)
        if not ev:
            yield event.plain_result(f"没有找到 ID 为 {event_id} 的活动。")
            return

        related = [ec for ec in event_cards if ec.get("eventId") == event_id]
        event_card_ids = [ec.get("cardId") for ec in related]
        ev_cards = [c for c in cards if c.get("id") in event_card_ids]

        # 没指定角色：输出活动概览 + 卡牌列表
        if not character:
            yield event.plain_result(
                _format_event_summary(ev, ev_cards, characters)
            )
            return

        # 指定了角色：解析昵称（character 可能因纯数字被自动转成 int）
        char_id = resolve_character_id(str(character))
        if char_id is None:
            yield event.plain_result(
                f"没认出角色『{character}』。"
                "请用昵称如 miku / saki / toya / kanade 或角色名（中日均可）。"
            )
            return

        matched = [c for c in ev_cards if c.get("characterId") == char_id]
        if not matched:
            char = _find_by_id(characters, char_id)
            name = _character_display_name(char) if char else f"ID {char_id}"
            yield event.plain_result(f"活动 {event_id} 里没有『{name}』的卡牌。")
            return

        for card in matched:
            c_id = int(card["id"])
            async for msg in self._handle_card_with_prefetched(
                event, c_id, translate, cards, episodes, characters
            ):
                yield msg

    async def terminate(self) -> None:
        """插件卸载时无需特殊清理。"""

    # -----------------------------
    # 单张卡牌处理
    # -----------------------------
    async def _handle_card(
        self,
        event: AstrMessageEvent,
        card_id: int,
        translate: bool,
    ):
        try:
            card_id = int(card_id)
        except (TypeError, ValueError):
            yield event.plain_result("卡牌ID必须是整数。例如 /skcd card 1275")
            return

        yield event.plain_result(f"正在拉取卡牌 {card_id} 的信息与剧情……")

        try:
            cards, episodes, characters = await self._client.fetch_master_data()
        except Exception as e:  # noqa: BLE001
            logger.exception("[sekai_card] 拉取主数据失败")
            yield event.plain_result(f"拉取 sekai 主数据失败：{e}")
            return

        async for msg in self._handle_card_with_prefetched(
            event, card_id, translate, cards, episodes, characters
        ):
            yield msg

    async def _handle_card_with_prefetched(
        self,
        event: AstrMessageEvent,
        card_id: int,
        translate: bool,
        cards: list[dict],
        episodes: list[dict],
        characters: list[dict],
    ):
        card = _find_by_id(cards, card_id)
        if not card:
            yield event.plain_result(f"没有找到 ID 为 {card_id} 的卡牌。")
            return

        character = _find_by_id(characters, card.get("characterId"))

        async for msg in self._emit_card_info(event, card, character, translate):
            yield msg

        card_episodes = sorted(
            (ep for ep in episodes if ep.get("cardId") == card_id),
            key=lambda ep: ep.get("seq", 0),
        )
        if not card_episodes:
            yield event.plain_result("该卡牌没有找到对应的角色剧情条目。")
            return

        assetbundle_name = card.get("assetbundleName", "")
        for ep in card_episodes:
            async for msg in self._emit_episode(
                event, card_id, assetbundle_name, ep, translate
            ):
                yield msg

    # -----------------------------
    # 输出流水：卡面信息
    # -----------------------------
    async def _emit_card_info(
        self,
        event: AstrMessageEvent,
        card: dict,
        character: dict | None,
        translate: bool,
    ):
        info_text = format_card_info(card, character)

        prefix = card.get("prefix") or ""
        if translate and prefix:
            try:
                prefix_zh = await self._llm_translate(
                    event, prefix, _SYS_PROMPT_CARD_TITLE
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[sekai_card] 翻译卡名失败: {e}")
                prefix_zh = None
            if prefix_zh:
                info_text = f"{info_text}\n🎴 中文译名：{prefix_zh}"

        yield event.plain_result(info_text)

    # -----------------------------
    # 输出流水：单个剧情条目
    # -----------------------------
    async def _emit_episode(
        self,
        event: AstrMessageEvent,
        card_id: int,
        assetbundle_name: str,
        ep: dict,
        translate: bool,
    ):
        scenario_id = ep.get("scenarioId")
        title = ep.get("title") or scenario_id or "剧情"
        if not scenario_id:
            return

        try:
            scenario = await self._client.fetch_scenario(
                assetbundle_name, scenario_id
            )
        except Exception as e:  # noqa: BLE001
            logger.exception(
                f"[sekai_card] 拉取剧情失败: card={card_id} scenario={scenario_id}"
            )
            yield event.plain_result(f"拉取剧情「{title}」失败：{e}")
            return

        text = format_scenario(scenario)

        # 原文 txt
        path = self._write_txt(card_id, scenario_id, title, "ja", text)
        yield event.chain_result(
            [
                Comp.Plain(f"剧情「{title}」已导出："),
                Comp.File(file=str(path), name=path.name),
            ]
        )

        if not translate:
            return

        try:
            text_zh = await self._translate_scenario(event, text)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[sekai_card] 翻译剧情失败: {e}", exc_info=True)
            return

        if not text_zh:
            return

        path_zh = self._write_txt(card_id, scenario_id, title, "zh", text_zh)
        yield event.chain_result(
            [
                Comp.Plain(f"剧情「{title}」中文译本："),
                Comp.File(file=str(path_zh), name=path_zh.name),
            ]
        )

    def _write_txt(
        self, card_id: int, scenario_id: str, title: str, lang: str, text: str
    ) -> Path:
        filename = _make_filename(card_id, scenario_id, title, lang)
        path = self._data_dir / filename
        path.write_text(text, encoding="utf-8")
        return path

    # -----------------------------
    # LLM 翻译
    # -----------------------------
    def _get_provider(self, event: AstrMessageEvent):
        provider_id = (self.config.get("translate_provider_id") or "").strip()
        if provider_id:
            prov = self.context.get_provider_by_id(provider_id=provider_id)
            if prov:
                return prov
            logger.warning(
                f"[sekai_card] translate_provider_id={provider_id!r} 未找到，回退到会话默认提供商"
            )
        return self.context.get_using_provider(umo=event.unified_msg_origin)

    async def _llm_translate(
        self,
        event: AstrMessageEvent,
        text: str,
        system_prompt: str,
    ) -> str | None:
        """调用 LLM 进行一次翻译调用，返回译文；没有可用提供商时返回 None。"""
        prov = self._get_provider(event)
        if not prov:
            logger.warning("[sekai_card] 当前没有可用的 LLM 提供商，跳过翻译")
            return None
        resp = await prov.text_chat(
            prompt=text,
            context=[],
            system_prompt=system_prompt,
        )
        return (resp.completion_text or "").strip() or None

    async def _translate_scenario(
        self, event: AstrMessageEvent, text: str
    ) -> str | None:
        """翻译整段剧情文本。太长则按行分块翻译再拼接。"""
        chunks = list(_split_by_lines(text, _TRANSLATE_CHUNK_MAX_CHARS))
        translated: list[str] = []
        for idx, chunk in enumerate(chunks, 1):
            logger.info(
                f"[sekai_card] 翻译剧情分块 {idx}/{len(chunks)} ({len(chunk)} 字符)"
            )
            piece = await self._llm_translate(event, chunk, _SYS_PROMPT_SCENARIO)
            if piece is None:
                return None
            translated.append(piece)
            if idx < len(chunks):
                await asyncio.sleep(_TRANSLATE_CHUNK_SLEEP)
        return "\n".join(translated).rstrip() + "\n"


# -----------------------------
# 模块级工具
# -----------------------------
def _find_by_id(items: Iterable[dict], target_id) -> dict | None:
    if target_id is None:
        return None
    return next((item for item in items if item.get("id") == target_id), None)


def _character_display_name(character: dict | None) -> str:
    if not character:
        return "?"
    parts = [character.get("firstName", ""), character.get("givenName", "")]
    return " ".join(p for p in parts if p) or "?"


def _fmt_event_time(ts_ms: int | None) -> str:
    if not ts_ms:
        return "未知"
    try:
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).astimezone(_JST)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError):
        return "未知"


def _format_event_summary(
    ev: dict, ev_cards: list[dict], characters: list[dict]
) -> str:
    lines = [
        f"🎉 活动 #{ev.get('id')}　{ev.get('name') or '-'}",
        f"类型：{ev.get('eventType') or '-'}",
        f"开始：{_fmt_event_time(ev.get('startAt'))} (JST)",
        f"结束：{_fmt_event_time(ev.get('closedAt'))} (JST)",
    ]
    if not ev_cards:
        lines.append("\n（该活动暂无活动卡牌数据）")
        return "\n".join(lines)

    lines.append(f"\n活动卡牌（{len(ev_cards)} 张）：")
    for c in sorted(ev_cards, key=lambda x: x.get("id", 0)):
        char = _find_by_id(characters, c.get("characterId"))
        name = _character_display_name(char)
        lines.append(
            f"  • [{c.get('id')}] {name}　{c.get('prefix') or '-'}"
        )
    lines.append(
        "\n使用 `/skcd event <活动ID> <角色昵称>` 可进一步拉取该角色的卡面与剧情。"
    )
    return "\n".join(lines)


def _split_by_lines(text: str, max_chars: int) -> Iterable[str]:
    """按行把文本切成若干 ≤ max_chars 的块。"""
    current: list[str] = []
    current_len = 0
    for line in text.splitlines():
        line_len = len(line) + 1  # +1 为换行符
        if current and current_len + line_len > max_chars:
            yield "\n".join(current)
            current = []
            current_len = 0
        current.append(line)
        current_len += line_len
    if current:
        yield "\n".join(current)


def _sanitize(name: str) -> str:
    cleaned = _FILENAME_SAFE_RE.sub("_", name).strip("_")
    return cleaned or "untitled"


def _make_filename(
    card_id: int, scenario_id: str, title: str, lang: str
) -> str:
    title_safe = _sanitize(title)[:40]
    return f"card_{card_id}_{scenario_id}_{title_safe}_{lang}.txt"
