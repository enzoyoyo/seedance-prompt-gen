用途：仅为明确目标是出海短剧的项目提供平台条件化，不替代通用叙事、生成与发布验收。
触发条件：用户明确写出「出海／海外／外语短剧」，或点名 ReelShort、DramaBox、FreeReels、NetShort、Melolo 等海外短剧 App，且作品是短剧；抖音与出海同时写出时，本文件与 [platform-douyin.md](platform-douyin.md) 同时生效，互不覆盖。
分界：[platform-packaging.md](platform-packaging.md) 管分平台交付物，[platform-risk-and-compliance.md](platform-risk-and-compliance.md) 管通用合规；本文件只管出海短剧增量。

# 出海短剧条件化模块

## 适用开关

同时满足「明确写出海／海外／外语短剧，或点名海外短剧 App」和「交付物是短剧」才启用。以下单独出现均不触发：

- 只写 TikTok、YouTube Shorts 或 Instagram Reels，走通用平台分轨；
- 只写竖屏；
- 只要「英文版」或「翻译字幕」，属后期分轨职责；
- 「短视频」或「社媒」。

海外短剧的落点分两类：一类是 TikTok、YouTube Shorts、Instagram Reels 等开放平台；一类是 ReelShort、DramaBox、FreeReels、NetShort、Melolo 等专属短剧 App。两类的提交路径不同，但都不改本 skill 的通用验收。目标仍含糊时保持通用路径，不把语言、画幅或平台名推断成出海项目。「出海 + 产品／品牌广告」走 Lane C，只读取 [platform-packaging.md](platform-packaging.md)，不启用本短剧模块。

## 默认与阻塞问题

- 目标地区与目标语言是阻塞项，写进 `### 接单问题`，占用既有的阻塞问题名额，不另加问题行；未答前不写正文，也不替用户选地区。
- 默认画幅 `9:16`，并立即标 `TODO_VERIFY_LIVE: aspect_ratio`；这是平台惯例而非法规，用户显式指定可覆盖。
- 各短剧 App 的上架规格按发布日的官方页面核对，标 `TODO_VERIFY_LIVE: dramaapp_<name>_spec`；本文件不写像素、码率或时长。
- 对白默认用目标语言原生生成，不先写中文再翻译；目标模型的语言覆盖标 `TODO_VERIFY_LIVE: language_coverage`，不写语种数量与语言清单。
- 交付时长按观看体验与 brief 决定，沿用通用路径的时长问法，不因出海另设节拍。

## 选题增量

地区题材偏好只作待核实假设，逐条标记，不设梯队也不列权重表：北美偏高冲突强刺激，标 `TODO_VERIFY_LIVE: regional_taste_north_america`；东南亚偏家庭伦理与乡土逆袭，标 `TODO_VERIFY_LIVE: regional_taste_southeast_asia`；中东偏情感与家庭关系，标 `TODO_VERIFY_LIVE: regional_taste_middle_east`；日韩偏细腻情感与漫改，标 `TODO_VERIFY_LIVE: regional_taste_japan_korea`。

同一核心冲突可按地区更换背景、主题与设定，但剧本张力门仍是唯一验收，地区偏好不能代替它。冲突／逆转 Lane 的完整规则读取 [story-short-drama.md](story-short-drama.md)，本文件只增加平台侧的选择顺序。不复制现有海外作品的 IP 人物、片名与标志性桥段：地区偏好是方向假设，不是抄袭许可。

## 本地化重做

- 直译中文成片不算出海交付。姓名、身份、职业、关系与冲突动机都要改成在目标地区成立的版本，不是给中文故事换一层字幕。
- 语域按角色身份、年龄、时代与目标语言习惯校对，读 [human-texture-and-script-gate.md](human-texture-and-script-gate.md)；不把中文台词逐句译过去。
- 角色与场景资产按目标地区外观、年代与服饰重锁，candidate 到 approved 重走一遍，不沿用中文版的 approved 资产，做法见 [keyframe-assets.md](keyframe-assets.md)。
- 声音资产按目标语言重建，读 [post-production.md](post-production.md) 的配音与声音一致性节；不用中文音色驱动外语台词。
- 已有成片改地区版走 Lane E：源视频只承担调度、机位、时序与节奏职责，身份、服装、地点与语言全部重锁并重新批准。

## 英语对白与口型压缩

只写动作不写台词，生成的是哑剧。宿主能生成带口型同步的说话画面和原生音轨，但必须在提示词里显式写出要说的英文句子，否则只会出口型乱动的无声表演。

三处声明缺一不可：开头总声明、节拍内嵌一次、结尾集中声明一次。

经 adapter 渲染 NBP v2 且写了 `beats` 时，节拍内嵌由 `beats[].say` 完成，结尾声明只写句数与「各说一次、逐字不改」，不重复原句（见 [prompt-contract.md](prompt-contract.md) 「剧本锁」）；这种写法与下方重复原句的写法哪种更稳待核实。

```text
15-second vertical 9:16 cinematic short drama with SPOKEN ENGLISH DIALOGUE.
Characters speak American English out loud with clear lip-sync.

BEAT 9-15s: ... Marcus slams a document on the table and shouts out loud
in English with clear lip-sync: 'Sign it! Or security will drag you into the rain!'

SPOKEN DIALOGUE, American English, clearly audible, lip-synced.
CLAIRE: '...'  MARCUS: '...'  HANNAH: '...'
```

剧本原句往往太长，短时长装不下且会出现口型对不上。**每句 8–15 个单词是实用参考范围**，具体按镜头实际秒数与表演停顿留白调整；压缩时保留最关键的一半信息。

- 原句：`"Marcus. Before you kick me out... have you ever bothered to check who actually funded your dying company? Or whose name is on the deed of this very building?"`
- 压缩：`'Marcus. Before you throw me out, check whose name is on the deed of this building.'`

写了对白后模型可能自动烧字幕，结尾必须加 `No on-screen text, no watermark, no subtitles.`；目标语言字幕仍按上文「提交前核对项」走确定性后期。

## 发行测试序列

- 先把开头几集与切片发到开放平台观察表现，只与同账号、同入口、相近发行阶段比较，并标 `TODO_VERIFY_LIVE: completion_signal`；不写完播率阈值或统一数字。
- 再向短剧 App 或 TikTok Drama Center 提交整剧；渠道条款与上架要求标 `TODO_VERIFY_LIVE: channel_<name>_terms`，发布日读官方当前页面，不凭记忆填写。
- 本文件不写收益、分账、补贴、激励结论；发布数据只回写创作变量，按主入口「用真实数据回写下一轮」执行。

## 提交前核对项

- AIGC 披露：TikTok 读 claim `tiktok.aigc.help.pointer.current`；YouTube 读 `youtube.aigc.realistic_disclosure.current` 与 `youtube.aigc.ai_use_ui.current`，来源见 [platform-evidence-ledger.jsonl](platform-evidence-ledger.jsonl)。Instagram 与各短剧 App 在 ledger 无条目，只标 `TODO_VERIFY_LIVE: aigc_disclosure_<platform>`，不凭推断写审核规则。
- 肖像、声音与音乐授权按 [platform-risk-and-compliance.md](platform-risk-and-compliance.md) 的三态运行；参考音色的来源与授权写进 manifest 的 `rights_or_attribution`。
- 目标语言字幕与画内文字由母语者或目标语言校对后定稿，走确定性后期，不交给生成阶段临场发挥。
- 地区版与中文版各自绑定自己的母版与资产版本；相关失效症状见 [failure-diagnosis.md](failure-diagnosis.md) 剧本层表。

## 平台证据门

查询模板、证据升级规则与三段式结果见 [platform-risk-and-compliance.md](platform-risk-and-compliance.md) 的「## 平台证据门」；本文件未升级项写 `TODO_VERIFY_LIVE: overseas_<platform>_<topic>`（arb B-41）。

