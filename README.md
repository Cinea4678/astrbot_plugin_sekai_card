# astrbot_plugin_sekai_card

一个 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 插件：输入 Project Sekai 卡牌 ID 或活动 ID，拉取该卡/活动的基础信息，以及对应的角色剧情（前篇 / 后篇）纯文本脚本，并作为 txt 文件发送。

## 指令

所有指令都在指令组 `/skcd` 下（旧名 `/sekai_card` 作为别名继续可用）。

### `/skcd card`

```
/skcd card <卡牌ID> [translate]
```

例如：

```
/skcd card 1275             # 仅输出日文原文
/skcd card 1275 true        # 额外调用 LLM 输出中文译名与译文 txt

/sekai_card card 1275       # 等价写法（别名）
```

会先返回一条卡面信息的文本消息（卡名、角色、组合、附属组合、属性、稀有度、技能名、开放时间、Gacha 语录），随后分别发送 **前篇** 和 **后篇** 剧情。每一篇剧情会同时附上：

- 渲染后的纯文本 `.txt`（与 sekai.best 前端 "纯文本" 页面一致）；
- 原始 `.asset` 文件（实际是 JSON），即从 `storage.sekai.best` 直接下载的字节，未经任何修改，便于本地二次解析。

### `/skcd event`

```
/skcd event <活动ID> [角色昵称] [translate]
```

例如：

```
/skcd event 202             # 输出活动概览与活动卡牌列表
/skcd event 202 miku        # 输出 miku 在该活动中的卡面 & 剧情
/skcd event 202 冬弥 true    # 带翻译的例子
```

- 不带角色时：返回活动名称、类型、开始/结束时间、以及该活动的所有活动卡牌列表（ID / 角色 / 卡名）。
- 带角色时：从活动卡牌中筛出该角色的卡，依次发送卡面信息与前/后篇剧情。

活动卡牌关系源自 `eventCards.json`，与 <https://sekai.best/event/202> 等前端页面保持一致。

### 角色昵称识别

支持常见英文/罗马音昵称，也兼容汉字。部分示例：

| 昵称 | 角色 | 昵称 | 角色 |
|---|---|---|---|
| miku / 初音 / ミク | 初音未来 | kanade / 奏 | 宵崎奏 |
| ichika / icchan / 一歌 | 星乃一歌 | mafuyu / まふゆ / 真冬 | 朝比奈真冬 |
| saki / 咲希 | 天马咲希 | ena / 絵名 / 绘名 | 东云绘名 |
| honami / honacha / 穂波 | 望月穂波 | mizuki / 瑞希 | 晓山瑞希 |
| shiho / 志歩 | 日野森志歩 | rin / リン | 镜音 Rin |
| minori / minorin | 花里みのり | len / レン | 镜音 Len |
| haruka / 遥 | 桐谷遥 | luka / ルカ / 巡音 | 巡音 Luka |
| airi / 愛莉 | 桃井愛莉 | meiko | MEIKO |
| shizuku / 雫 | 日野森雫 | kaito | KAITO |
| kohane / こはね | 小豆沢こはね | an / 杏 | 白石杏 |
| akito / 彰人 | 东云彰人 | toya / touya / 冬弥 | 青柳冬弥 |
| tsukasa / 司 | 天马司 | emu / えむ | 凤えむ |
| nene / 寧々 | 草薙寧々 | rui / 類 | 神代類 |

`translate` 参数接受 `true` / `false` / `yes` / `no` / `1` / `0`，省略时等同于 `false`。

## 剧情文本格式

与 sekai.best 前端 "纯文本" 页面的呈现一致：

```
誰もいないセカイ

湖

ミク：…………あ
KAITO：…………
...
```

- 场景标题（`SpecialEffectData.EffectType == 8` 的 `StringVal`）作为单独一行输出；相邻的标题之间空一行分隔。
- 对话为 `WindowDisplayName：Body`，保留原文换行和游戏内的 `\N` 软换行符。
- 标题块与首句台词之间空一行分段。

### 附带的 `.asset` 原始文件

每篇剧情除了发送渲染后的 `.txt`，还会额外附上对应的 `.asset`。该文件就是插件从 `storage.sekai.best/sekai-jp-assets/character/member/{assetbundleName}/{scenarioId}.asset` 拿到的原始字节（实际上是 JSON），**未经过 `json.loads` / `json.dumps` 往返**，字段顺序、空白与缩进与 CDN 下发的内容 bit-for-bit 一致，方便需要自定义解析或二次处理时直接使用。

文件名规则：

```
card_<cardId>_<scenarioId>_<title>_ja.txt        # 渲染后的纯文本
card_<cardId>_<scenarioId>_<title>.asset         # 原始 JSON
card_<cardId>_<scenarioId>_<title>_zh.txt        # translate=true 时的中文译本
```

## 数据来源

插件**不依赖** sekai.best 前端页面，而是直接读取：

- `https://sekai-world.github.io/sekai-master-db-diff/cards.json`
- `https://sekai-world.github.io/sekai-master-db-diff/cardEpisodes.json`
- `https://sekai-world.github.io/sekai-master-db-diff/gameCharacters.json`
- `https://sekai-world.github.io/sekai-master-db-diff/events.json`
- `https://sekai-world.github.io/sekai-master-db-diff/eventCards.json`
- `https://storage.sekai.best/sekai-jp-assets/character/member/{assetbundleName}/{scenarioId}.asset`

仅使用日服（sekai-jp-assets）数据。

## 配置项

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `translate_provider_id` | string | `""` | 指定用于翻译的 LLM 提供商 ID，留空则使用当前会话默认提供商。仅在指令带 `translate` 参数时生效。 |
| `cache_ttl_seconds` | int | 3600 | 主数据（cards / cardEpisodes / gameCharacters / events / eventCards）的内存缓存时长。 |
| `http_timeout_seconds` | int | 30 | 单次 HTTP 请求超时时间。 |

## 翻译说明

- 是否翻译由指令参数 `translate` 控制，开启时会额外调用 LLM 把卡名和两篇剧情翻译成中文，卡面译名附在卡面信息消息末尾，前/后篇剧情译文作为独立的 `_zh.txt` 文件发送。
- 翻译通过 AstrBot 配置的大语言模型完成，打开翻译会显著增加 token 消耗。
- 剧情文本较长时会分块（默认每块 ≤ 2000 字符）提交给 LLM，按行拼回。
- Prompt 已要求：保留行结构、保留 `\N` 与空行、角色名同时翻译、只输出译文本体。但 LLM 本身无法保证 100% 严格遵守，如需更稳定的效果，建议使用能力较强的模型。

## 许可

MIT
