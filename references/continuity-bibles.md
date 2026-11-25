# Continuity Bibles

## 用途与真源

圣经只解决跨镜头会漂移的事实，不替代剧本、分镜或 Prompt。两条真源分开维护：故事/人物状态来自批准剧本与 state ledger；物理生产状态来自 approved assets、当前镜头台账与真实通过 QC 的末态。聊天记忆、旧文件名和失败生成不能覆盖真源。

物理生成偏差不得自动改写人物知情、信念或动机；批准剧本的设定也不得覆盖真实像素中的手位、道具、空间或动作末态。

先按复杂度选重量。只因“想做得高级”不得升级流程；存在多条条件时按最高真实风险处理。

| 档位 | 触发条件 | 必做 | 禁止 |
|---|---|---|---|
| 轻流程 | 没有需要跨镜继承的高风险事实，或单镜即可闭合 | Prompt Contract；明确当前参考职责与稳定末态 | 建三圣经、时间线或全套拓扑台账 |
| 轻圣经 | 有少量会跨镜复用的身份、道具、状态或空间事实，且歧义与返工成本可由稀疏台账控制 | 只建实际需要的角色卡、资产 variant 与 continuity in/out | 为未出现的群像、跨时空或战损预建重资产 |
| 完整圣经 | 多个身份/服化道/空间/时间状态相互依赖，漂移或返工成本高，轻台账不足以证明一致性 | 只建立覆盖已声明高风险维度的圣经、状态机、时间线与镜头台账 | 仅靠 prose 或聊天上下文维持已声明的高风险连续性 |

简单项目禁用重流程；复杂项目不得省略其真实风险所需的连续性管理。镜头数、角色数或场景数只能提示风险，不能单独决定档位。

## 四类圣经

### 角色圣经 Character Bible

每个需要建档的角色单独记录，不批量混写。`character_id / version / approval_status` 是该记录的必填真源；其余维度只按跨镜复用、漂移概率、叙事因果和下游验证风险选择，未参与执行的字段删除而不是为了表格完整而编造。候选维度包括：

- `character_id / version / approval_status`：稳定 ID、版本和批准状态；
- 叙事功能、欲望、可见压力与本场行为，不把背景小传直接塞进生成 Prompt；
- 静止态身份：脸部骨相、肤色、体型、身高比例、永久标记和不可漂移项；
- 适用的已批准 `identity / outfit / minimum_view_set / lineup` 资产 ID；
- 发型、妆容、服装、伤口、污渍和随身道具的 variant ID；
- 与其他角色的身高差、站位倾向、对抗/回避关系；
- `voice / movement / stillness` 引语级描述符；
- 完整态与战损态的切换条件；
- `Production Rules`：必须保持、绝不出现、何时必须重锁身份。
- 同剧主要角色面部须有清晰区分度；禁止跨剧复用高度相似 AI 脸（媒体多源转述红果差异化要求，2026-09-15；相似度百分比不写）。

引语级描述符必须是可直接粘贴、可观察的物理描述，语言服从用户与目标 provider；外层用引号，内部不写角色名字。下面英文仅为序列化示例，不是语言硬门：

```text
Voice: "Low mid register, dry breath texture, measured pace, quiet sentence endings; never shouts."
Movement: "Leads with the left shoulder, takes short weighted steps, touches the ring before committing."
Stillness: "Weight held over the back foot, right hand loose beside the seam, slow nasal breathing, gaze level."
```

`Voice` 写音区、音色、语速、默认音量和语言习惯；`Movement` 写步态、手势、发力与下意识动作；`Stillness` 写静止时的手位、重心、呼吸和视线。抽象词如“神秘、强大、很有气场”不合格。

`Voice` 同时是冻结条件块：在写对白前定稿，一人一块，之后逐字复用；若必须改变，升级版本并重验，不用同义词静默改写。触发式举止也按「条件 → 可见动作」冻结，不以情绪形容词代替。

#### Sparse character scene state

Stable biography stays in the Character Bible; changing scene state is recorded sparsely at scene/beat resolution:

- `knows`: facts the character has actually received, with a traceable source/event;
- `believes`: the character's current inference, including false beliefs that differ from objective truth;
- `wants`: the state this character currently hopes to bring about;
- `relation_power(target)`: directional leverage, dependency, permission or obligation toward a named target.

Keep objective truth, viewer knowledge and each character's subjective state separate. Unknown remains `unknown`; do not fill gaps with invented backstory. Crowds, a one-off back view, non-speaking extras and character-free work may omit the table.

State changes obey an event rule:

```text
state_in + visible/audible scene_event → changed fields only → state_out
```

If no event changes a field, inherit it. Every knowledge update names how the character learned it; every power shift names the gained/lost leverage, dependency, permission or obligation. `A → B` and `B → A` are separate records and need not be symmetric or reducible to one score.

`acting_task` may be derived for the current scene, but it is not merged into `wants`:

```text
wants = desired state
acting_task = current actable tactic toward a person/object/space
```

Only visible tactics, body/voice responses and physical consequences enter a generation Prompt. The state ledger prevents impossible behavior; it is not invisible exposition for the model.

模板：[character-bible.md](../templates/character-bible.md)。角色资产的批准、替换和 superseded 规则见 [continuity-storyboard.md](continuity-storyboard.md#角色定型)。

### 角色访谈法

访谈按轴采集、最后压成可直投单行；不把问题清单原样塞进交付：

1. 先问叙事功能与现在时心理，再问足以解释当下选择的一项具体成型细节；功能必须先于背景。
2. 视觉锁逐项只提交一个明确答案，并同步写「错误答案长什么样」的身份防火墙；永久辨识点必须能绑定到稳定位置。
3. 声音与动作分轴采集，最后分别组装成带引号单行；静止态独立成栏，高能量人物也要有可观察的静止变体。
4. 暗线只收用户能说清的既定线索，并改写为可拍动作时刻；说不清就不写。
5. 引语内部不用角色名，只写物理特征；视觉锁在最终卡中压成一行，采集过程不照搬为模板。
6. 一次做深一个角色；所谓先做少量角色只是个人工作法，不设固定人数门。

读参考图只描述看见的内容；参考与规格都没有的信息先问，不猜。状态变化用分叉版本重锁，旧版不覆盖；建服装或分镜前声明使用哪个状态。状态特征写明触发原因，永久特征和已知漂移项就地冻结。

### 场景圣经 Scene Bible

一个可复用地点一个 `location_id`，不同时间、天气或破坏状态用 variant，不静默改写原地点。只记录会影响当前镜头、跨镜继承或验收的字段，候选包括：

- 北向基准、坐标原点、主要尺寸、楼层/高差和可通行边界；
- 门窗、走廊、家具、固定道具、入口/出口和角色移动路径；
- 角色与摄影机可用区、遮挡物、反射面及危险歧义点；
- 每条对白/动作轴线、允许机位侧和合法过轴办法；
- 主光的实体来源、方向、高度、色温基准、阴影方向与时段；
- 环境声、混响与持续背景运动；
- 被打碎、移走、点燃或遗留物的物体恒存状态；
- 已批准地点板、俯视拓扑图和关键角度资产 ID。

模板：[scene-bible.md](../templates/scene-bible.md)。

场景多角度资产以一张批准基准图为真源，派生角度只改变相机。锚点必须覆盖可命名固定物、尺度、拓扑与坐标；同一空间确实承载反复对话或连续分镜时才投入多角度资产，少量镜头不强建。基准图可先自动生成再人工调整；可选槽位顺序：场景地点／主要元素／风格氛围／镜头视角，不设为门。

### 视觉风格圣经 Visual Style Bible

风格圣经只锁跨镜头可验证的视觉行为，不复述人物和剧情：

- `style_id / version` 与适用世界、时代、时间线；
- 主色、辅色、强调色、肤色保护区和颜色弧；
- 对比度、曝光基准、黑位、饱和度与高光滚降；
- 动机光源类型、软硬度、允许的雾/颗粒/受控瑕疵；
- 构图倾向、镜头高度、FOV/景深行为、手持或稳定器档位；
- 材质响应、年代道具和介质纹理；
- 排他规则：哪些现代物、光色、镜头行为和伪文字绝不进入；
- 跨时代项目为每条时间线建立互斥签名，避免同一 LUT 伪装差异。

风格参考只承担色板、媒介、纹理和光线职责，不能成为身份参考。

模板：[visual-style-bible.md](../templates/visual-style-bible.md)。

多时间线分别锁色调、光质、纹理、颗粒与机位语法；相邻场的光线按场序形成可追踪弧线，跨度过大时设计有叙事作用的过渡场，不靠统一 LUT 抹平差异。风格前缀可按 题材世界观／影像风格／材质／镜头光影／色彩／负面限制 的顺序组织，只是可选排序；母版画幅在风格阶段一并定下，分轨画幅另记。

### 世界观圣经 World Bible

世界观圣经只在跨时代、阵营、地点、世界规则或群像关系会被多次消费时建立。由外向内交付：一句话前提 → 主题问句 → 时间线 → 时代美术 → 阵营 → 地点 → 世界规则 → 角色 → 群像 → 结构引擎 → 生产规则 → 使用说明；不适用项直接删除。

- 每个时代用互斥且可观察的色彩、光质与介质签名；
- 群像写人物组合在场时的行为质感，不只写关系名词；
- 参考图承担身份、服装、发型与五官；圣经补它带不走的声音、动作、静止态、时代美术和生产禁令；
- 末尾写清下游如何引用、哪些事实不得推断；
- 完备性只问：陌生下游仅凭此圣经，能否写出一场不破坏设定的戏。不能就补真源，不靠后续聊天记忆。

## 建立与冻结顺序

1. 从剧本抽取镜头中能看见的稳定事实、会变化的状态和不可逆事件。
2. 为角色、地点、服装、道具、风格和关键帧分配稳定 ID；先标 `candidate`。
3. 单角色逐一冻结身份与引语级描述符，再建立场景空间和风格边界。
4. 只有镜头实际需要时才创建发型、服装、道具或损伤 variant。
5. 多角色同框且身份/比例容易混淆时批准阵容表；正反打或复杂走位存在空间歧义时批准轴线、视线及所需拓扑表示。
6. 资产通过下游用途 QC 后改为 `approved`；旧版本标 `superseded`，不能再输入生成。
7. 当下一镜声明继承当前实际结果时，以本镜真实通过 QC 的末态更新台账后再编译；独立 pickup、editorial cut 或无跨镜继承任务不机械吃尾态。
8. 场/beat 结束后只用真实 `scene_event` 更新改变的 `knows / believes / wants / relation_power`；其余继承或保留 unknown。

## 服装、发型与道具时间线

把状态写成 variant，不写“和上一镜一样”。每次变化记录触发镜头、变化前后、是否可逆、下一镜必须继承什么。

| 类别 | 必记字段 | 断裂判据 |
|---|---|---|
| 服装 | outfit ID、实际可见穿着层级、扣合/卷袖、湿度、污渍、撕裂坐标 | 已声明的层级、开合或损伤无剧情原因恢复 |
| 发型/妆容 | hair/makeup ID、分缝、长度、束发方式、散落方向、汗水/血迹 | 转面后分缝翻转；永久改变未重锁 face asset |
| 道具 | prop ID、所有者、左右手、位置、朝向、开合/电量/破损状态 | 换手、消失、尺寸漂移或已改变状态复原 |

道具尺寸用人体或场景锚点表达；例如与前臂、掌宽、桌沿高度比较。镜头外未记录的改变视为没有发生。

## 完整态 / 战损态双定型

动作冲突前先批准两套相同身份、不同状态的参考：

- `intact`：完整服装、干净皮肤、未损道具和初始发型；
- `damaged`：固定位置的伤口、撕裂、污渍、缺件和发型散乱。

转换必须由镜头中的可见事件触发。进入 `damaged` 后默认不可逆；只有剧本明确治疗、换装或时间跳跃并建立新 variant 才能退出。不要让单张表同时展示互相冲突的完整态与战损态作为生成输入。

## 阵容表与防克隆

多角色同框且存在克隆/比例风险时，建立能锁定身高、肩宽、体型和站序的阵容资产。背景从灰、白、透明或其他干净方案中按主体分离、抠图需要和代表镜结果选择，不预设中性灰。每个角色记录足以在目标像素尺度区分身份的 `required_discriminators`；数量由可辨性决定，可少可多，例如发型轮廓、服装外轮廓、年龄/肤色或永久标记。

- 每人使用独立资产 ID 和唯一短名；
- 不把多张不同脸散放进同一参考堆栈让模型求平均；
- 同框 Prompt 明写主谓宾、站位、朝向和动作，禁用含混的“they interact”；
- 背景角色也分配独立微动作时钟，但不能抢主动作；
- 同框数量或参考预算属于 provider 易变参数：快照 2026-08-24，生成前 live 校验；默认 14 天过期。

## 镜头台账、轴线与俯视拓扑

当入口、路径、轴线或身体—摄影机几何会改变执行时，建立足以消除该歧义的拓扑表示；可包含北向、坐标原点、门窗家具、固定道具、起始站位、移动路径、动作轴线和摄影机允许区。只有在这种条件下，图才作为空间真源；不因“完整圣经”标签机械要求全量俯视图。

每镜记录通用标识、可见任务和真实 QC 末态；下列连续性字段仅在该维度已声明或会跨镜影响执行时保留，无关行删除：

```text
shot_id / location_variant / time
角色坐标、朝向、屏幕方向、视线目标
camera 坐标、高度、朝向、景别、轴线侧
wardrobe / hair / prop state
主光来源、方向和阴影基准
continuity in / planned out / actual QC-passed out
approved relay frame / status
```

### 180° 轴线

为一组关系建立 `axis_id`，明确轴线两端和摄影机允许侧。正反打摄影机留在同一侧；想过轴，必须用可见中性镜头、沿轴镜头或摄影机连续跨越动作建立新侧，并在台账中变更 `axis_side`。

### 视线守恒

视线记录“角色 → 目标 → 水平/垂直角度 → 画面方向”。A 在画面右侧看向左，反打中的 B 应看向相反画面方向；目标高度变化时同步更新俯仰角。只写“看着对方”不足以验收。

### 光线与物体恒存

只有实体主光或阴影方向会跨镜影响曝光、空间或叙事时才锁定对应光源事实；未参与执行的光字段不强填。已声明光源时，换机位不等于换太阳或窗户；跨时间变化必须在镜头中可见或切到新 scene variant。倒下的椅子、碎片、弹孔、开门状态等一旦改变并会影响后续镜头，就进入 `persistent_world_state`。

模板：[continuity-ledger.md](../templates/continuity-ledger.md)。更细的 shot contract、cut 和真实末态交接见 [continuity-storyboard.md](continuity-storyboard.md#状态交接)。

## 推进门

下一镜编译前逐项回答：

- 所有引用是否为当前 `approved` 版本？
- 角色是否只依据当前 `knows / believes` 行动，未提前使用客观真相或观众信息？
- `wants / relation_power` 的变化是否有对应 `scene_event`，且 power 带 target 与方向？
- 角色身份、阵容比例和状态机是否匹配当前镜头？
- 已声明的坐标、屏幕方向、轴线侧和视线是否与上一通过镜头相容？
- 已声明的服装、发型、左右手道具和物体恒存是否继承？
- 适用时，主光、时段和阴影变化是否有可见原因？
- `continuity_in` 是否来自真实 QC 末态，而非计划末态？

任一答案为否，停在最早真源修复；不要靠给 Prompt 继续堆形容词补洞。
