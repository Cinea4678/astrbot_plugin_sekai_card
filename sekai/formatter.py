"""卡面信息、剧情脚本的格式化工具。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

# sekai 内部稀有度 -> 展示文本
RARITY_TYPE_DISPLAY = {
    "rarity_1": "★1",
    "rarity_2": "★2",
    "rarity_3": "★3",
    "rarity_4": "★4",
    "rarity_birthday": "★BD (生日卡)",
}

# 组合 ID 展示
UNIT_DISPLAY = {
    "piapro": "Virtual Singer (piapro)",
    "light_sound": "Leo/need",
    "idol": "MORE MORE JUMP!",
    "street": "Vivid BAD SQUAD",
    "theme_park": "Wonderlands×Showtime",
    "school_refusal": "25時、ナイトコードで。",
    "none": "无",
}

# 属性 ID 展示
ATTR_DISPLAY = {
    "cute": "Cute (粉)",
    "cool": "Cool (蓝)",
    "pure": "Pure (绿)",
    "happy": "Happy (黄)",
    "mysterious": "Mysterious (紫)",
}

JST = timezone(timedelta(hours=9))

# 剧情脚本 Snippets 的 Action 取值
_ACTION_TALK = 1
_ACTION_SPECIAL_EFFECT = 6
# 场景标题对应的特效类型
_EFFECT_SCENE_TITLE = 8


def _fmt_release_at(ts_ms: int | None) -> str:
    """sekai 的 releaseAt 是毫秒级 UTC 时间戳，按 JST 渲染。"""
    if not ts_ms:
        return "未知"
    try:
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        return dt.astimezone(JST).strftime("%Y-%m-%d %H:%M (JST)")
    except (ValueError, OSError):
        return "未知"


def _character_display_name(character: dict[str, Any] | None, fallback_id: Any) -> str:
    if not character:
        return f"角色ID {fallback_id}"
    parts = [character.get("firstName", ""), character.get("givenName", "")]
    return " ".join(p for p in parts if p) or f"角色ID {fallback_id}"


def _unit_display(unit_id: str | None) -> str:
    if not unit_id or unit_id == "none":
        return "-"
    return UNIT_DISPLAY.get(unit_id, unit_id)


def format_card_info(
    card: dict[str, Any],
    character: dict[str, Any] | None,
) -> str:
    """把 cards.json 中的一条卡牌数据渲染成人类友好的摘要文本。"""

    main_unit_id = character.get("unit") if character else None

    lines = [
        f"🎴 {card.get('prefix') or '-'}",
        f"角色：{_character_display_name(character, card.get('characterId', '?'))}",
        f"组合：{_unit_display(main_unit_id)}",
        f"附属组合：{_unit_display(card.get('supportUnit'))}",
        f"属性：{ATTR_DISPLAY.get(card.get('attr', ''), card.get('attr') or '-')}",
        f"稀有度：{RARITY_TYPE_DISPLAY.get(card.get('cardRarityType', ''), card.get('cardRarityType') or '-')}",
        f"技能名：{card.get('cardSkillName') or '-'}",
        f"开放时间：{_fmt_release_at(card.get('releaseAt'))}",
        f"Gacha 语录：{card.get('gachaPhrase') or '-'}",
    ]
    return "\n".join(lines)


def format_scenario(scenario: dict[str, Any]) -> str:
    """把一份 .asset 剧情脚本渲染为纯文本。

    格式约定：
    - 对话：`WindowDisplayName：Body`，Body 中的原始换行与 `\\N` 都保留原样。
    - 场景切换（SpecialEffectData.EffectType == 8）的 `StringVal` 作为场景标题输出；
      连续的场景标题紧挨着输出，首句台词前空一行。
    """

    talks = scenario.get("TalkData") or []
    effects = scenario.get("SpecialEffectData") or []
    snippets = scenario.get("Snippets") or []

    out: list[str] = []
    prev_was_title = False
    prev_was_talk = False

    for snippet in snippets:
        action = snippet.get("Action")
        ref = snippet.get("ReferenceIndex", 0)

        if action == _ACTION_TALK and 0 <= ref < len(talks):
            talk = talks[ref]
            name = (talk.get("WindowDisplayName") or "").strip()
            body = talk.get("Body") or ""
            if prev_was_title:
                out.append("")  # 标题与首句台词之间空一行
            out.append(f"{name}：{body}" if name else body)  # 无名字则为旁白
            prev_was_title = False
            prev_was_talk = True
            continue

        if action == _ACTION_SPECIAL_EFFECT and 0 <= ref < len(effects):
            effect = effects[ref]
            if effect.get("EffectType") != _EFFECT_SCENE_TITLE:
                continue
            title = effect.get("StringVal")
            if not title:
                continue
            if prev_was_talk:
                out.append("")  # 从台词切到新标题，空一行分段
            out.append(title)
            prev_was_title = True
            prev_was_talk = False

    return "\n".join(out).rstrip() + "\n"
