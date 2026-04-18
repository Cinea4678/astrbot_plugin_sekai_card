# AGENTS.md

本文件为后续在本仓库工作的 Agent / 开发者提供项目上下文、约定与扩展指南。

## 项目定位

`astrbot_plugin_sekai_card` 是一个 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 插件。它接收 Project Sekai（世界计划 / プロセカ）的卡牌 ID，输出：

1. 一条卡面信息文本消息（卡名 / 角色 / 组合 / 附属组合 / 属性 / 稀有度 / 技能名 / 开放时间 / Gacha 语录）。
2. 该卡牌前篇、后篇角色剧情的纯文本 `.txt` 附件。
3. 可选：指令携带 `translate` 参数（值为 true/yes/1）时，调用 AstrBot 当前 LLM 提供商翻译卡名和剧情，额外输出中文版本。

**入口指令**（指令组 `/skcd`，旧名 `/sekai_card` 作为 alias）：

- `/skcd card <卡牌ID> [translate]`（例：`/skcd card 1275`、`/skcd card 1275 true`）。
- `/skcd event <活动ID> [角色昵称] [translate]`（例：`/skcd event 202`、`/skcd event 202 miku`）。
- `/sekai_card card ...` / `/sekai_card event ...`：完全等价的别名写法。

`translate` 参数接受 `true/false/yes/no/1/0`，省略则为 `false`。

## 数据来源（非常重要）

本插件 **不** 解析 sekai.best 前端页面，而是直接读取其底层公共数据源：

| 用途 | URL |
|---|---|
| 卡牌主表 | `https://sekai-world.github.io/sekai-master-db-diff/cards.json` |
| 卡牌剧情关系表 | `https://sekai-world.github.io/sekai-master-db-diff/cardEpisodes.json` |
| 角色表 | `https://sekai-world.github.io/sekai-master-db-diff/gameCharacters.json` |
| 剧情脚本（日服） | `https://storage.sekai.best/sekai-jp-assets/character/member/{assetbundleName}/{scenarioId}.asset` |

剧情脚本文件扩展名虽然是 `.asset`，但实际就是 JSON；结构中我们关心的三个字段：

- `TalkData[]`：每条对话 `{WindowDisplayName, Body, ...}`
- `SpecialEffectData[]`：含场景切换 `{EffectType: 8, StringVal: "场景标题"}`
- `Snippets[]`：驱动主时间线，`Action=1` 引用 `TalkData[ReferenceIndex]`，`Action=6` 引用 `SpecialEffectData[ReferenceIndex]`

**剧情输出格式** 与 sekai.best 前端"纯文本"页面一致：
- `SpecialEffectData.EffectType == 8` 的 `StringVal` 作为单独一行（场景标题 / 地点）。
- 相邻的标题紧挨着输出；标题块 → 首句台词之间空一行；台词 → 下一个新标题之间空一行。
- 对话行格式固定为 `WindowDisplayName：Body`，Body 中的原文换行与 `\N` 软换行符**必须原样保留**。

如果需要改动剧情渲染规则，核心在 `sekai/formatter.py#format_scenario`。

## 代码结构

```
astrbot_plugin_sekai_card/
├── main.py                 # 插件入口：SekaiCardPlugin，注册 /card /event /sekai_card 指令
├── metadata.yaml           # 插件元数据，AstrBot 识别插件的依据
├── _conf_schema.json       # WebUI 配置项 Schema
├── requirements.txt        # httpx
├── README.md               # 面向用户
├── AGENTS.md               # 本文件，面向开发者/Agent
└── sekai/
    ├── __init__.py
    ├── characters.py        # 昵称 -> characterId 映射表，纯函数
    ├── client.py            # SekaiClient：异步 + 内存 TTL 缓存的数据源客户端
    └── formatter.py        # format_card_info / format_scenario：纯函数，无副作用
```

### 模块职责

- **`sekai/client.py`**
  - `SekaiClient.fetch_master_data()`：并发拉 3 张主表，**走缓存**（默认 1 小时）。
  - `SekaiClient.fetch_scenario(assetbundle_name, scenario_id)`：单次拉剧情脚本，**不走缓存**（体积大、单次使用）。
  - 内部共用 `_get_json(client, url, use_cache)`，不要再加第三条 HTTP 分支；加新数据源时复用这个方法。

- **`sekai/formatter.py`**
  - **只能是纯函数**：输入 dict，输出 str。不要做任何 I/O、logging。
  - 稀有度 / 组合 / 属性的展示文本在文件顶部常量表中；新服更新导致枚举变化时改这里。
  - 剧情渲染的魔法数字（`_ACTION_TALK=1`、`_ACTION_SPECIAL_EFFECT=6`、`_EFFECT_SCENE_TITLE=8`）已命名；新增分支请同样常量化。

- **`main.py`**
  - `SekaiCardPlugin.cmd_sekai_card`：指令主入口，只做参数校验 + 主数据拉取 + 路由。第二个参数 `translate: bool = False` 由 AstrBot 指令解析器自动把 `true/yes/1` / `false/no/0` 转为 bool。
  - `_handle_card_with_prefetched`：卡面处理核心。把「卡面信息」和「各篇剧情 (原文)」**收集为 sections**，一次性通过 `_emit_message` 发出（支持合并转发的平台合并为一条 `Nodes`，否则 fallback 为单条拼接链）。
  - `_emit_message` / `_build_forward_or_chain`：消息打包器。判定 `event.get_platform_name() in _SUPPORTS_FORWARD_PLATFORMS`（当前是 `{aiocqhttp, satori}`）来决定是否用合并转发；新平台原生支持 Node/Nodes 时记得把平台名加到集合里。
  - `_send_translation_async`：`translate=True` 时开的后台 task，把翻译好的卡名 + 各篇中文剧情再打包成一条合并转发通过 `self.context.send_message(umo, MessageChain(...))` 主动推送。task 由 `self._bg_tasks` 持有，`terminate()` 时统一取消。
  - `_llm_translate(event, text, system_prompt)`：所有 LLM 调用的唯一入口。新增翻译场景请新增一条 `_SYS_PROMPT_*` 常量并复用本方法，不要直接调 `prov.text_chat`。
  - `_split_by_lines`、`_find_by_id`、`_sanitize`、`_make_filename`：模块级纯工具，不依赖 `self`。

## AstrBot 关键 API（本插件用到的）

- 注册：`@register(name, author, desc, version, repo)` + 继承 `Star`，主文件必须是 `main.py`。
- 指令：`@filter.command("sekai_card")`，处理函数 `async def handler(self, event, <args>)`。
- 输出：
  - 文本：`event.plain_result(text)`
  - 消息链：`event.chain_result([Comp.Plain(...), Comp.File(file=path, name=name)])`
- 配置：`__init__(self, context, config: AstrBotConfig)`，与 `_conf_schema.json` 字段对应。
- 数据目录：`StarTools.get_data_dir("astrbot_plugin_sekai_card")` → `data/plugin_data/astrbot_plugin_sekai_card/`。**不要** 把数据写到插件自身目录。
- LLM：`self.context.get_using_provider(umo=event.unified_msg_origin)`，若插件配置了 `translate_provider_id` 再 `get_provider_by_id`。
- 日志：`from astrbot.api import logger`，**不要** 用标准库 `logging`。

## 开发约束（务必遵守）

1. **网络请求只能用异步库**（`httpx.AsyncClient`），**禁止** `requests`。
2. **持久化写入目录**：只能写到 `StarTools.get_data_dir(...)`，**不要** 写到插件自身目录（更新/重装插件会被清掉）。
3. **文件名 sanitize**：用户/游戏侧的标题可能含日文、全角括号、特殊符号，调 `_make_filename` 统一处理；新增路径生成逻辑时沿用 `_FILENAME_SAFE_RE`。
4. **剧情正文不做任何编辑**：`\N`、空格、全角符号、原文换行都要 bit-for-bit 保留；这些是游戏内的排版指令，删掉会丢信息。
5. **LLM 调用必须 try/except**：翻译失败不能让主流程挂掉，必须 `logger.warning` 后跳过翻译、继续发原文。
6. **缓存语义**：主数据走 TTL 缓存（默认 1h），剧情脚本不缓存。不要擅自给 `fetch_scenario` 加缓存（体积大、覆盖面广、容易撑爆内存）。
7. **格式化器是纯函数**：`sekai/formatter.py` 里不能出现 `print` / `logger` / `open` / `httpx`。便于脱机单测。

## 验证 & 调试

### 离线单测（不依赖 AstrBot）

`sekai/formatter.py` 与 `sekai/client.py` 可独立验证：

```bash
# 拉一份 miku01 剧情样本到本地
curl -s 'https://storage.sekai.best/sekai-jp-assets/character/member/res021_no061/021061_miku01.asset' \
    -o /tmp/miku01.asset

python3 -c "
import json, sys
sys.path.insert(0, '.')
from sekai.formatter import format_scenario
print(format_scenario(json.load(open('/tmp/miku01.asset')))[:500])
"
```

### 在 AstrBot 中调试

1. 把本目录软链/克隆到 `AstrBot/data/plugins/astrbot_plugin_sekai_card`
2. 启动 AstrBot，WebUI → 插件管理 → 重载插件
3. 发送 `/sekai_card 1275` 验证
4. 代码修改后点"重载插件"即可，不需要重启 AstrBot

### 测试用例（手动）

| Case | 期望 |
|---|---|
| `/sekai_card` | 返回用法提示 |
| `/sekai_card abc` | 返回"卡牌ID必须是整数" |
| `/sekai_card 99999999` | 返回"没有找到 ID 为 ... 的卡牌" |
| `/sekai_card 1275` | 卡面信息 + 前篇 txt + 后篇 txt |
| `/sekai_card 1275 true` | 额外 1 条中文译名 + 2 个 `_zh.txt` |
| 指令带 `translate` 但未配置 LLM | 原文正常，LLM 部分静默跳过并 warning |

## 常见扩展场景

### 加一个新指令（例如按活动 ID 列出卡牌）

1. 在 `SekaiCardPlugin` 上加 `@filter.command("...")` 方法。
2. 如需新数据源（比如 `events.json`），在 `sekai/client.py` 顶部加 URL 常量 + 对应 `fetch_*` 方法，复用 `_get_json`。
3. 新的格式化逻辑放 `sekai/formatter.py`，保持纯函数。

### 支持其他服务器（国际服 / 繁中服）

`STORAGE_BASE` 是硬编码的日服路径。要支持多服需要：
1. 在 `_conf_schema.json` 加 `server: enum["jp","en","tw","kr"]` 字段。
2. 把 `STORAGE_BASE` 改成函数 `storage_base(server)`，main DB 可能也要换（参考 sekai.best 前端的 server switch）。
3. 注意 `assetbundleName` 在不同服可能不一致，cards.json 也要换源。

### 输出图片（卡图）

卡图 URL 的命名规律：

```
# 特训前 / 特训后 大图
https://storage.sekai.best/sekai-jp-assets/character/member_cutout_trm/{assetbundleName}/card_normal.webp
https://storage.sekai.best/sekai-jp-assets/character/member_cutout_trm/{assetbundleName}/card_after_training.webp

# 小图
https://storage.sekai.best/sekai-jp-assets/thumbnail/chara/{assetbundleName}_normal.webp
https://storage.sekai.best/sekai-jp-assets/thumbnail/chara/{assetbundleName}_after_training.webp
```

想发图就在 `_build_card_info_components` 里追加 `Comp.Image.fromURL(url)` 即可，不要保存本地。

## 版本 / 发布

- 修改功能性代码后更新 `metadata.yaml` 的 `version`，遵循 semver。
- 依赖新增务必写入 `requirements.txt`。
- 提交前使用 [ruff](https://docs.astral.sh/ruff/) 格式化。
- Commit message 用中文 Conventional Commits（例：`feat: 支持输出卡图`、`fix(formatter): 修复连续场景标题丢失空行`）。

## 已知限制

- 仅支持日服（sekai-jp-assets）。
- 剧情脚本中的选项分支（choice）目前按主时间线顺序输出，没有处理玩家选项切换。
- LLM 翻译基于 prompt 约束，无法 100% 保证 "保留行数 / 保留 `\N` / 保留空行" 的硬性要求；能力弱的模型可能产出格式漂移的译文。
- `gameCharacters.json` 中只有主 10 + 5 位 VS 成员；客串 / 活动 mob 角色不在内，当 `characterId` 不在主角色表时，插件会降级显示 "角色ID xxx"。
