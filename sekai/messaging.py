"""消息装配：把 section 列表打包成合并转发或单条消息链；卡图 section 构造。

纯函数，依赖 astrbot 的消息组件，不访问 self / 全局状态。
"""

from __future__ import annotations

import astrbot.api.message_components as Comp

from .client import STORAGE_BASE
from .constants import (
    FORWARD_NODE_NAME,
    FORWARD_NODE_UIN,
    RARITIES_WITH_AFTER_TRAINING,
    SUPPORTS_FORWARD_PLATFORMS,
)


def build_forward_or_chain(
    sections: list[list],
    platform_name: str,
    header_note: str | None = None,
) -> list:
    """根据平台决定返回 Nodes 合并转发链，或 fallback 拼接链。"""
    header = [Comp.Plain(header_note + "\n")] if header_note else []
    use_forward = (
        platform_name in SUPPORTS_FORWARD_PLATFORMS and len(sections) > 1
    )
    if use_forward:
        nodes = [
            Comp.Node(
                uin=FORWARD_NODE_UIN,
                name=FORWARD_NODE_NAME,
                content=list(comps),
            )
            for comps in sections
        ]
        return [*header, Comp.Nodes(nodes=nodes)]

    # fallback：拼接为单条链，section 之间插入分隔线
    body: list = []
    for idx, comps in enumerate(sections):
        if idx > 0:
            body.append(Comp.Plain("\n\n────────\n\n"))
        body.extend(comps)
    return [*header, *body]


def build_card_image_sections(card: dict) -> list[list]:
    """根据卡牌 assetbundleName / 稀有度，构造卡图 section 列表。

    每张图独占一个 section（合并转发节点）：与 File 同样，多张 Image 放在
    同一节点会被部分 OneBot 协议端折叠，单图独占节点最稳。
    """
    ab = (card.get("assetbundleName") or "").strip()
    if not ab:
        return []
    base = f"{STORAGE_BASE}/character/member/{ab}"
    sections: list[list] = [
        [
            Comp.Plain("🖼️ 卡面（特训前）"),
            Comp.Image.fromURL(f"{base}/card_normal.webp"),
        ]
    ]
    if card.get("cardRarityType") in RARITIES_WITH_AFTER_TRAINING:
        sections.append(
            [
                Comp.Plain("🖼️ 卡面（特训后）"),
                Comp.Image.fromURL(f"{base}/card_after_training.webp"),
            ]
        )
    return sections
