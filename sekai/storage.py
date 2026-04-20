"""剧情 / .asset 落盘工具。纯函数（只做路径构造 + 写文件）。"""

from __future__ import annotations

import re
from pathlib import Path

# 文件名安全字符：字母数字下划线、CJK 统一表意、平假名、片假名
_FILENAME_SAFE_RE = re.compile(r"[^\w\-\u3040-\u30ff\u4e00-\u9fff]+", re.UNICODE)


def sanitize(name: str) -> str:
    cleaned = _FILENAME_SAFE_RE.sub("_", name).strip("_")
    return cleaned or "untitled"


def make_txt_filename(card_id: int, scenario_id: str, title: str, lang: str) -> str:
    title_safe = sanitize(title)[:40]
    return f"card_{card_id}_{scenario_id}_{title_safe}_{lang}.txt"


def make_asset_filename(card_id: int, scenario_id: str, title: str) -> str:
    title_safe = sanitize(title)[:40]
    return f"card_{card_id}_{scenario_id}_{title_safe}.asset"


def write_txt(
    data_dir: Path,
    card_id: int,
    scenario_id: str,
    title: str,
    lang: str,
    text: str,
) -> Path:
    path = data_dir / make_txt_filename(card_id, scenario_id, title, lang)
    path.write_text(text, encoding="utf-8")
    return path


def write_asset(
    data_dir: Path,
    card_id: int,
    scenario_id: str,
    title: str,
    raw: bytes,
) -> Path:
    """将原始 .asset（JSON）字节原封不动地落盘。"""
    path = data_dir / make_asset_filename(card_id, scenario_id, title)
    path.write_bytes(raw)
    return path
