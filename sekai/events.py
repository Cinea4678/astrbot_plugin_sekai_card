"""活动概览格式化与通用 ID 查找工具。纯函数。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

_JST = timezone(timedelta(hours=9))


def find_by_id(items: Iterable[dict], target_id) -> dict | None:
    if target_id is None:
        return None
    return next((item for item in items if item.get("id") == target_id), None)


def character_display_name(character: dict | None) -> str:
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


def format_event_summary(
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
        char = find_by_id(characters, c.get("characterId"))
        name = character_display_name(char)
        lines.append(
            f"  • [{c.get('id')}] {name}　{c.get('prefix') or '-'}"
        )
    lines.append(
        "\n使用 `/skcd event <活动ID> <角色昵称>` 可进一步拉取该角色的卡面与剧情。"
    )
    return "\n".join(lines)
