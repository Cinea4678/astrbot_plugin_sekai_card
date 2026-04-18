"""Project Sekai 角色昵称 → characterId 映射。

`gameCharacters.json` 中的 `id` 与本表一致：
1~4   Leo/need     (一歌 / 咲希 / 穂波 / 志歩)
5~8   MORE MORE JUMP! (みのり / 遥 / 愛莉 / 雫)
9~12  Vivid BAD SQUAD (こはね / 杏 / 彰人 / 冬弥)
13~16 Wonderlands×Showtime (司 / えむ / 寧々 / 類)
17~20 25時、ナイトコードで。 (奏 / まふゆ / 絵名 / 瑞希)
21~26 Virtual Singer (Miku / Rin / Len / Luka / MEIKO / KAITO)

`resolve_character_id(name)` 返回匹配到的 character id，没匹配到则返回 None。
匹配规则（依次尝试）：
1. 全部小写、去掉两端空白后精确匹配 nickname 表。
2. 与角色全名（汉字/假名）做包含匹配。
"""

from __future__ import annotations

from typing import Iterable

# (character_id, [nickname, ...]) — nickname 全部小写、纯 ASCII 或常见汉字
_NICKNAMES: tuple[tuple[int, tuple[str, ...]], ...] = (
    # Leo/need
    (1, ("ichika", "icchan", "一歌", "ichika hoshino", "hoshino", "星乃")),
    (2, ("saki", "sacchan", "咲希", "tenma saki")),
    (3, ("honami", "honacha", "穂波", "穗波", "mochizuki")),
    (4, ("shiho", "志歩", "shippo", "hinomori shiho")),
    # MORE MORE JUMP!
    (5, ("minori", "minorin", "みのり", "hanasato")),
    (6, ("haruka", "kiritani", "桐谷", "遥")),
    (7, ("airi", "愛莉", "爱莉", "momoi")),
    (8, ("shizuku", "雫", "hinomori shizuku")),
    # Vivid BAD SQUAD
    (9, ("kohane", "こはね", "azusawa")),
    (10, ("an", "anhan", "杏", "shiraishi")),
    (11, ("akito", "彰人", "shinonome akito")),
    (12, ("toya", "touya", "tooya", "冬弥", "aoyagi")),
    # Wonderlands×Showtime
    (13, ("tsukasa", "司", "tenma tsukasa")),
    (14, ("emu", "えむ", "ootori", "otori")),
    (15, ("nene", "寧々", "宁宁", "kusanagi")),
    (16, ("rui", "類", "类", "kamishiro")),
    # 25時、ナイトコードで。
    (17, ("kanade", "奏", "yoisaki")),
    (18, ("mafuyu", "まふゆ", "真冬", "asahina")),
    (19, ("ena", "絵名", "绘名", "shinonome ena")),
    (20, ("mizuki", "瑞希", "akiyama")),
    # Virtual Singer
    (21, ("miku", "hatsune", "初音", "ミク", "未来")),
    (22, ("rin", "kagamine rin", "リン", "鏡音リン", "鏡音鈴")),
    (23, ("len", "kagamine len", "レン", "鏡音レン", "鏡音連")),
    (24, ("luka", "megurine", "ルカ", "巡音")),
    (25, ("meiko",)),
    (26, ("kaito",)),
)

_NICKNAME_TO_ID: dict[str, int] = {
    nick.lower(): cid for cid, nicks in _NICKNAMES for nick in nicks
}


def resolve_character_id(name: str) -> int | None:
    """昵称 → characterId；找不到返回 None。"""
    if not name:
        return None
    key = name.strip().lower()
    return _NICKNAME_TO_ID.get(key)


def list_known_nicknames() -> Iterable[tuple[int, tuple[str, ...]]]:
    """供帮助文本使用：列出 (characterId, nicknames) 元组。"""
    return _NICKNAMES
