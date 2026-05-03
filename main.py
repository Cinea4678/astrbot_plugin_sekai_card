"""astrbot_plugin_sekai_card - Project Sekai 卡牌信息 & 剧情导出插件。

指令：
    /skcd card <card_id> [translate]
    /skcd event <event_id> [character] [translate]
    /skcd help

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
from pathlib import Path

import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.core import astrbot_config

from .sekai.characters import resolve_character_id
from .sekai.client import SekaiClient
from .sekai.constants import HELP_TEXT
from .sekai.events import (
    character_display_name,
    find_by_id,
    format_event_summary,
)
from .sekai.formatter import format_card_info, format_scenario
from .sekai.messaging import build_card_image_sections, build_forward_or_chain
from .sekai.storage import write_asset, write_txt
from .sekai.translator import Translator


@register(
    "astrbot_plugin_sekai_card",
    "Cinea4678",
    "从 sekai.best 拉取 Project Sekai 卡牌 / 活动信息与角色剧情并输出文本。",
    "0.6.1",
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
        self._translator = Translator(context, config)
        self._bg_tasks: set[asyncio.Task] = set()

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

    @skcd.command("help")
    async def cmd_help(self, event: AstrMessageEvent):
        """/skcd help —— 输出指令使用说明与作者信息。"""
        yield event.plain_result(HELP_TEXT)

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

        ev = find_by_id(events, event_id)
        if not ev:
            yield event.plain_result(f"没有找到 ID 为 {event_id} 的活动。")
            return

        related = [ec for ec in event_cards if ec.get("eventId") == event_id]
        event_card_ids = [ec.get("cardId") for ec in related]
        ev_cards = [c for c in cards if c.get("id") in event_card_ids]

        # 没指定角色：输出活动概览 + 卡牌列表
        if not character:
            yield event.plain_result(format_event_summary(ev, ev_cards, characters))
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
            char = find_by_id(characters, char_id)
            name = character_display_name(char) if char else f"ID {char_id}"
            yield event.plain_result(f"活动 {event_id} 里没有『{name}』的卡牌。")
            return

        for card in matched:
            c_id = int(card["id"])
            async for msg in self._handle_card_with_prefetched(
                event, c_id, translate, cards, episodes, characters
            ):
                yield msg

    async def terminate(self) -> None:
        """插件卸载时取消未完成的后台翻译任务。"""
        for task in list(self._bg_tasks):
            task.cancel()
        if self._bg_tasks:
            await asyncio.gather(*self._bg_tasks, return_exceptions=True)

    async def _make_file_component(self, path: Path):
        """按 AstrBot 全局 callback_api_base 决定用 HTTP 回调链接或 file:// URI。"""
        callback_api_base = str(
            astrbot_config.get("callback_api_base", "") or ""
        ).strip()
        logger.info(
            "[sekai_card] 构造文件链接: callback_api_base=%r, path=%s",
            callback_api_base,
            path,
        )
        if callback_api_base:
            local_file = Comp.File(file=str(path), name=path.name)
            try:
                url = await local_file.register_to_file_service()
            except Exception:  # noqa: BLE001
                logger.warning(
                    "[sekai_card] 注册文件到 AstrBot callback 文件服务失败，退回 file://：%s",
                    path,
                    exc_info=True,
                )
            else:
                logger.info(
                    "[sekai_card] 文件链接生成成功: callback_api_base=%r, link=%s",
                    callback_api_base,
                    url,
                )
                return Comp.File(name=path.name, url=url)

        file_uri = path.resolve().as_uri()
        logger.info(
            "[sekai_card] 文件链接使用 file:// 回退: callback_api_base=%r, link=%s",
            callback_api_base,
            file_uri,
        )
        return Comp.File(name=path.name, url=file_uri)

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
        card = find_by_id(cards, card_id)
        if not card:
            yield event.plain_result(f"没有找到 ID 为 {card_id} 的卡牌。")
            return

        character = find_by_id(characters, card.get("characterId"))
        card_info_comps = [Comp.Plain(format_card_info(card, character))]

        card_episodes = sorted(
            (ep for ep in episodes if ep.get("cardId") == card_id),
            key=lambda ep: ep.get("seq", 0),
        )

        image_sections = build_card_image_sections(card)

        if not card_episodes:
            chain = build_forward_or_chain(
                sections=[card_info_comps, *image_sections],
                platform_name=event.get_platform_name(),
            )
            yield event.chain_result(chain)
            yield event.plain_result("该卡牌没有找到对应的角色剧情条目。")
            return

        # 拉取所有剧情原文、写出 txt，为之后的发送与翻译准备数据
        assetbundle_name = card.get("assetbundleName", "")
        episode_sections: list[dict] = []
        for ep in card_episodes:
            scenario_id = ep.get("scenarioId")
            title = ep.get("title") or scenario_id or "剧情"
            if not scenario_id:
                continue
            try:
                scenario, raw_bytes = await self._client.fetch_scenario(
                    assetbundle_name, scenario_id
                )
            except Exception as e:  # noqa: BLE001
                logger.exception(
                    f"[sekai_card] 拉取剧情失败: card={card_id} scenario={scenario_id}"
                )
                yield event.plain_result(f"拉取剧情「{title}」失败：{e}")
                continue

            text = format_scenario(scenario)
            path = write_txt(self._data_dir, card_id, scenario_id, title, "ja", text)
            asset_path = write_asset(
                self._data_dir, card_id, scenario_id, title, raw_bytes
            )
            episode_sections.append(
                {
                    "scenario_id": scenario_id,
                    "title": title,
                    "text": text,
                    "path": path,
                    "asset_path": asset_path,
                }
            )

        # 原文合并发送（或 fallback）
        # 注意：OneBot 协议端（NapCat/Lagrange 等）在合并转发节点里，
        # content 出现 file 段后会把整个 Node 视为"文件节点"，吞掉同 Node
        # 内的其他 Plain 和后续 File。所以每个 File 必须独占一个 section。
        episode_comps: list[list] = []
        for sec in episode_sections:
            txt_file = await self._make_file_component(sec["path"])
            asset_file = await self._make_file_component(sec["asset_path"])
            episode_comps.append(
                [
                    Comp.Plain(f"剧情「{sec['title']}」已导出（纯文本）："),
                    txt_file,
                ]
            )
            episode_comps.append(
                [
                    Comp.Plain(f"剧情「{sec['title']}」原始 .asset："),
                    asset_file,
                ]
            )
        chain = build_forward_or_chain(
            sections=[card_info_comps, *episode_comps, *image_sections],
            platform_name=event.get_platform_name(),
        )
        yield event.chain_result(chain)

        if translate:
            task = asyncio.create_task(
                self._send_translation_async(
                    unified_msg_origin=event.unified_msg_origin,
                    platform_name=event.get_platform_name(),
                    event=event,
                    card=card,
                    episode_sections=episode_sections,
                )
            )
            self._bg_tasks.add(task)
            task.add_done_callback(self._bg_tasks.discard)

    # -----------------------------
    # 异步翻译：后台任务中翻译卡名 + 各篇剧情，结果打包成一条合并转发发出
    # -----------------------------
    async def _send_translation_async(
        self,
        unified_msg_origin: str,
        platform_name: str,
        event: AstrMessageEvent,
        card: dict,
        episode_sections: list[dict],
    ) -> None:
        """后台任务：翻译卡名 + 各篇剧情，结果打包成一条合并转发发出。"""
        try:
            card_id = int(card.get("id", 0))
            sections: list[list] = []
            failed_titles: list[str] = []

            # 1. 卡名翻译
            prefix = card.get("prefix") or ""
            if prefix:
                prefix_zh = await self._translator.safe_call(
                    self._translator.translate_card_title(event, prefix),
                    label="卡名",
                )
                if prefix_zh:
                    sections.append([Comp.Plain(f"🎴 中文译名：{prefix_zh}")])
                else:
                    failed_titles.append("卡名")

            # 2. 各篇剧情翻译
            for sec in episode_sections:
                title = sec["title"]
                text_zh = await self._translator.safe_call(
                    self._translator.translate_scenario(event, sec["text"]),
                    label=f"剧情「{title}」",
                    exc_info=True,
                )
                if not text_zh:
                    failed_titles.append(title)
                    continue
                path_zh = write_txt(
                    self._data_dir, card_id, sec["scenario_id"], title, "zh", text_zh
                )
                zh_file = await self._make_file_component(path_zh)
                sections.append(
                    [
                        Comp.Plain(f"剧情「{title}」中文译本："),
                        zh_file,
                    ]
                )

            # 3. 打包发送
            if not sections and not failed_titles:
                return

            if failed_titles:
                sections.append(
                    [
                        Comp.Plain(
                            "⚠️ 以下内容翻译失败，请稍后重试或检查 LLM 配置：\n  • "
                            + "\n  • ".join(failed_titles)
                        )
                    ]
                )

            chain = build_forward_or_chain(
                sections=sections,
                platform_name=platform_name,
                header_note="🌐 中文翻译结果",
            )
            await self.context.send_message(
                unified_msg_origin,
                MessageChain(chain=chain),
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("[sekai_card] 后台翻译任务异常")
