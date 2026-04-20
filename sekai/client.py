"""Sekai 数据源客户端。

直接从 sekai-world 公共仓库与 sekai.best 的 CDN 拉取数据，绕开前端页面。

原始数据源：
- 卡牌主表:     https://sekai-world.github.io/sekai-master-db-diff/cards.json
- 卡牌剧情表:   https://sekai-world.github.io/sekai-master-db-diff/cardEpisodes.json
- 角色表:       https://sekai-world.github.io/sekai-master-db-diff/gameCharacters.json
- 活动主表:     https://sekai-world.github.io/sekai-master-db-diff/events.json
- 活动卡牌关系: https://sekai-world.github.io/sekai-master-db-diff/eventCards.json
- 剧情脚本:     https://storage.sekai.best/sekai-jp-assets/character/member/
                    {assetbundleName}/{scenarioId}.asset

为提升在中国大陆的访问稳定性，实际请求走下面由本仓库维护者提供的镜像
域名（见 ``MASTER_DB_BASE`` / ``STORAGE_BASE``），路径结构与上游完全一致，
可直接替换 host 使用。如需切回官方源，把这两个常量改回上面的 URL 即可。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

# 使用本仓库维护者提供的镜像（cinea.ln.cn），而非官方的
# sekai-world.github.io / storage.sekai.best。镜像只是改了 host，
# 路径 / 文件内容与官方源保持一致；切回官方源时把下面两行换成：
#     MASTER_DB_BASE = "https://sekai-world.github.io/sekai-master-db-diff"
#     STORAGE_BASE   = "https://storage.sekai.best/sekai-jp-assets"
MASTER_DB_BASE = "https://master-db.sekai.cinea.ln.cn/sekai-master-db-diff"
STORAGE_BASE = "https://storage.sekai.cinea.ln.cn/sekai-jp-assets"

CARDS_URL = f"{MASTER_DB_BASE}/cards.json"
CARD_EPISODES_URL = f"{MASTER_DB_BASE}/cardEpisodes.json"
GAME_CHARACTERS_URL = f"{MASTER_DB_BASE}/gameCharacters.json"
EVENTS_URL = f"{MASTER_DB_BASE}/events.json"
EVENT_CARDS_URL = f"{MASTER_DB_BASE}/eventCards.json"


class SekaiClient:
    """异步、带内存缓存的 sekai 数据源客户端。"""

    def __init__(self, cache_ttl: int = 3600, timeout: int = 30) -> None:
        self._cache_ttl = cache_ttl
        self._timeout = timeout
        # 每个 URL 一份缓存: {url: (expire_ts, data)}
        self._cache: dict[str, tuple[float, Any]] = {}

    async def _get_json(
        self, client: httpx.AsyncClient, url: str, use_cache: bool
    ) -> Any:
        if use_cache:
            cached = self._cache.get(url)
            if cached and cached[0] > time.time():
                return cached[1]

        resp = await client.get(url, timeout=self._timeout)
        resp.raise_for_status()
        data = resp.json()

        if use_cache:
            self._cache[url] = (time.time() + self._cache_ttl, data)
        return data

    async def fetch_master_data(self) -> tuple[list[dict], list[dict], list[dict]]:
        """并发拉取卡牌 / 卡牌剧情 / 角色 三张主表（结果被缓存）。"""
        async with httpx.AsyncClient() as client:
            return await asyncio.gather(
                self._get_json(client, CARDS_URL, use_cache=True),
                self._get_json(client, CARD_EPISODES_URL, use_cache=True),
                self._get_json(client, GAME_CHARACTERS_URL, use_cache=True),
            )

    async def fetch_event_data(self) -> tuple[list[dict], list[dict]]:
        """并发拉取活动主表 / 活动卡牌关系表（结果被缓存）。"""
        async with httpx.AsyncClient() as client:
            return await asyncio.gather(
                self._get_json(client, EVENTS_URL, use_cache=True),
                self._get_json(client, EVENT_CARDS_URL, use_cache=True),
            )

    async def fetch_scenario(
        self, assetbundle_name: str, scenario_id: str
    ) -> tuple[dict, bytes]:
        """拉取指定剧情脚本（character/member 目录下的 .asset，实际是 JSON）。

        返回 `(parsed_dict, raw_bytes)` —— `raw_bytes` 即 CDN 返回的原始
        字节，便于把原始 .asset 文件原封不动地附加到消息里。

        剧情脚本体积较大且单次使用，故不走缓存。
        """
        url = (
            f"{STORAGE_BASE}/character/member/"
            f"{assetbundle_name}/{scenario_id}.asset"
        )
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=self._timeout)
            resp.raise_for_status()
            return resp.json(), resp.content
