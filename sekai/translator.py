"""LLM 翻译封装：挑选 provider、单次翻译、长文分块翻译。

依赖 AstrBot 的 Context 与事件对象，但不涉及消息组件或落盘；
异常一律 warning 后返回 None，调用方按需 fallback。
"""

from __future__ import annotations

import asyncio
from typing import Iterable

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context

from .constants import (
    SYS_PROMPT_CARD_TITLE,
    SYS_PROMPT_SCENARIO,
    TRANSLATE_CHUNK_MAX_CHARS,
    TRANSLATE_CHUNK_SLEEP,
)


def split_by_lines(text: str, max_chars: int) -> Iterable[str]:
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


class Translator:
    """封装 provider 选择与翻译调用的轻量工具类。"""

    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        self._context = context
        self._config = config

    def _get_provider(self, event: AstrMessageEvent):
        provider_id = (self._config.get("translate_provider_id") or "").strip()
        if provider_id:
            prov = self._context.get_provider_by_id(provider_id=provider_id)
            if prov:
                return prov
            logger.warning(
                f"[sekai_card] translate_provider_id={provider_id!r} 未找到，回退到会话默认提供商"
            )
        return self._context.get_using_provider(umo=event.unified_msg_origin)

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

    async def translate_card_title(
        self, event: AstrMessageEvent, text: str
    ) -> str | None:
        return await self._llm_translate(event, text, SYS_PROMPT_CARD_TITLE)

    async def translate_scenario(
        self, event: AstrMessageEvent, text: str
    ) -> str | None:
        """翻译整段剧情文本。太长则按行分块翻译再拼接。"""
        chunks = list(split_by_lines(text, TRANSLATE_CHUNK_MAX_CHARS))
        translated: list[str] = []
        for idx, chunk in enumerate(chunks, 1):
            logger.info(
                f"[sekai_card] 翻译剧情分块 {idx}/{len(chunks)} ({len(chunk)} 字符)"
            )
            piece = await self._llm_translate(event, chunk, SYS_PROMPT_SCENARIO)
            if piece is None:
                return None
            translated.append(piece)
            if idx < len(chunks):
                await asyncio.sleep(TRANSLATE_CHUNK_SLEEP)
        return "\n".join(translated).rstrip() + "\n"

    async def safe_call(self, coro, label: str, exc_info: bool = False):
        """await 一个翻译协程；异常记 warning 并返回 None。"""
        try:
            return await coro
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[sekai_card] 翻译{label}失败: {e}", exc_info=exc_info)
            return None
