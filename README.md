# astrbot_plugin_sekai_card

一个 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 插件：输入 Project Sekai 卡牌 ID，拉取该卡的基础信息，以及该卡对应的角色剧情（前篇 / 后篇）纯文本脚本，并作为 txt 文件发送。

## 指令

```
/sekai_card <卡牌ID>
```

例如：

```
/sekai_card 1275
```

会先返回一条卡面信息的文本消息（卡名、角色、组合、附属组合、属性、稀有度、技能名、开放时间、Gacha 语录），随后分别发送 **前篇** 和 **后篇** 的剧情 txt 文件。

## 剧情文本格式

与 sekai.best 前端 "纯文本" 页面的呈现一致：

```
誰もいないセカイ
湖

ミク：…………あ
KAITO：…………
...
```

- 场景标题（`SpecialEffectData.EffectType == 8` 的 `StringVal`）作为单独一行输出；相邻的标题紧挨着。
- 对话为 `WindowDisplayName：Body`，保留原文换行和游戏内的 `\N` 软换行符。
- 标题块与首句台词之间空一行分段。

## 数据来源

插件**不依赖** sekai.best 前端页面，而是直接读取：

- `https://sekai-world.github.io/sekai-master-db-diff/cards.json`
- `https://sekai-world.github.io/sekai-master-db-diff/cardEpisodes.json`
- `https://sekai-world.github.io/sekai-master-db-diff/gameCharacters.json`
- `https://storage.sekai.best/sekai-jp-assets/character/member/{assetbundleName}/{scenarioId}.asset`

仅使用日服（sekai-jp-assets）数据。

## 配置项

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `translate_to_chinese` | bool | false | 开启后会额外调用 LLM 把卡名和两篇剧情翻译成中文，并作为附加消息/附加 txt 文件发送。 |
| `translate_provider_id` | string | `""` | 指定用于翻译的 LLM 提供商 ID，留空则使用当前会话默认提供商。 |
| `cache_ttl_seconds` | int | 3600 | 主数据（cards / cardEpisodes / gameCharacters）的内存缓存时长。 |
| `http_timeout_seconds` | int | 30 | 单次 HTTP 请求超时时间。 |

## 翻译说明

- 翻译通过 AstrBot 配置的大语言模型完成，开启 `translate_to_chinese` 会显著增加 token 消耗。
- 剧情文本较长时会分块（默认每块 ≤ 2000 字符）提交给 LLM，按行拼回。
- Prompt 已要求：保留行结构、保留 `\N` 与空行、角色名同时翻译、只输出译文本体。但 LLM 本身无法保证 100% 严格遵守，如需更稳定的效果，建议使用能力较强的模型。

## 许可

MIT
