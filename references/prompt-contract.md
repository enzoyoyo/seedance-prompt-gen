# Prompt Contract

## 用户面：Simplified JSON（v7 默认展示）

面向用户的可复制提示词默认是一层扁平 JSON，不是嵌套的 NBP v2。模板：[simplified-image-prompt.json](../templates/simplified-image-prompt.json)（CLI 编译 `--target google_flow`，输出 `exact_model_id: "nano_banana_2_1"`）、[simplified-video-prompt.json](../templates/simplified-video-prompt.json)（CLI 编译 `--target seedance_2_5`）。

| 键 | 写什么 | 图像 | 视频 |
|---|---|---|---|
| `mode` | 可选，`cinema` 或 `short_drama`（五维差异见 [cinema-vs-short-drama.md](cinema-vs-short-drama.md)） | 可选 | 可选 |
| `subject` | 主体身份、本镜状态、服装与手里的道具；人物用 `@char_* 角色名`（如 `@char_mira_v01 林夏`）绑定 | ✓ | ✓ |
| `action` | 一条可见因果动作与稳定末态；图像写成可见定态 | ✓ | ✓ |
| `scene` | 地点、前中后景、世界状态 | ✓ | ✓ |
| `camera` | 机位、景别／焦段感、主路径、起止构图 | ✓ | ✓ |
| `light` | 实体光源、方向、软硬 | ✓ | ✓ |
| `style` | 色板、媒介、材质 | ✓ | ✓ |
| `motion` | 主体、镜头、环境的路径与余势，可按秒分段；生成时长与剪辑净可用段不同时在此注明 `usable` 区间 | 禁用 | ✓ |
| `duration` | 已核验或待核的目标时长，如 `"5s"`；未核验通道能力时在 JSON 外注 `TODO_VERIFY_LIVE` | 禁用 | ✓ |
| `aspect_ratio` | 按发布面推导的画幅 | ✓ | ✓ |
| `audio` | 推荐结构化 `{dialogue[], ambience, music, sfx}`（对白形如 `说话者（语气，对听者）：台词`）；也兼容以 `｜` 分段的字符串 | 禁用 | ✓ |
| `refs` | 有序数组 `[{"ref": "@...", "role": "character\|location\|prop\|style\|motion\|audio", "use": "..."}]`（顺序即上传/槽位顺序）；`simplified_prompt.py` 亦兼容 `{标签: 职责}` 字典简写与数组 `continuity_ref` | ✓ | ✓ |
| `negative` | 正向化后仍残留的高风险项，0..N 条 | ✓ | ✓ |

- 空键一律省略，不写 `""`、`null`、`[]` 或占位；除 `refs`（有序对象数组，兼容字典简写）、`audio`（四键对象或分段字符串）、`continuity_ref`、`negative`（及可选 `beats`、`live_params`）外都是字符串。
- 图像规格出现 `motion`／`duration`／`audio` 即错误。
- 未点名目标模型时（含 `prompt_only`）先只输出模型中立的 Simplified JSON；仅在用户点名或选定目标模型后再编译对应方言。一次只给一镜；多镜逐镜给，先给 shot list。
- 用户点名要 NBP v2、要交给工具链，或要排查编译问题时，才展示内部 IR。

### 内部编译链（用户看不到这一层）

```text
Simplified JSON → NBP v2 IR（"nbp_version": "2"）→ 目标方言 prompt + 参数
```

1. `python3 scripts/validate_nbp_prompt.py --schema auto --type <image|video> --input <规格.json>`：识别 Simplified JSON 并由 `simplified_prompt.py` 规范化为 NBP v2 IR——从 `subject` 与 `character` 参考提取 `characters[]{ref,name,state,wardrobe}`，`camera` 按分句关键词拆入 `shot_size/angle/movement/lens_note`，`duration` 转为 `{target_s, live_check}`，`audio` 归一为 `{dialogue[], ambience, music, sfx}`，`refs`（含字典简写）与 `continuity_ref` 按出现顺序展开为 `references[]{ref,role,use}`，`aspect_ratio` 原样带入。
2. `python3 scripts/render_nbp_adapter.py --target <目标> --schema auto --type <image|video> --input <规格.json> --json`：从 IR 编译到目标方言，规则见 [prompt-compiler.md](prompt-compiler.md)。
3. 规范化补不出的必填信息（例如对白说话者非画外且在 `characters[].name` 里找不到对应绑定，报 `UNKNOWN_DIALOGUE_SPEAKER`；或空引用报 `EMPTY_REFERENCE`）一律 fail-closed 报错退回，不猜、不补默认值。

两层分工：Simplified JSON 是给人读和改的真源；NBP v2 IR 是给校验器和适配器的全保真中间层。用户改 Simplified JSON 后重新规范化，不手改 IR。

### 防误译：只译原意，不加戏

中文规格译成英文或别的 provider 语言时，否定、缺省和范围必须原样保留：

| 原文 | 正确 | 错误（实际发生过） |
|---|---|---|
| `无工牌` | `no ID badge` | `bare-chested`（把「没戴工牌」译成「赤裸上身」） |
| `不戴眼镜` | `no glasses` | 删掉这一条，模型自由发挥 |
| `外套敞开` | `jacket open, shirt visible underneath` | `shirtless` |

- 否定只否定被点名的那一件物品，不扩大到整个衣着或身体。
- 译后回读：逐条对照中文原文，确认没有新增服装、暴露程度、伤痕、年龄或人数变化；对白原句一字不改，只译舞台提示。
- 译文有歧义时宁可保留中文原词加英文解释，不选更「戏剧化」的词。

### 防遮挡肢体：看不见的不驱动

- 首帧被遮挡、出画或藏在背后的手、脚、道具，本镜不得写它的运动；要用，先在关键帧里让它可见，或拆成新镜。
- 两步法（先静帧锁构图，再图生视频）里，静帧阶段就锁定可见肢体的位置；视频 prompt 只驱动首帧里看得见的肢体。驱动一只被遮挡的手，会让前景本来稳定的手跟着崩——拿着的杯子掉了、手指重复。
- 写法：`subject` 里写清每只可见手在做什么（「左手捏借条、首帧可见」），`action` 只让这些手动；背后的手只写结果状态（「钥匙仍在老周背后」），不写过程。

## 原则

先写可迁移的镜头语义，再适配平台语法。提示词不是形容词清单，也不是永久 API schema。

复杂度决定输出；不要让所有任务套同一模板。

当结果在重复运行中漂移，先把“欠描述”当作可检验的根因假设：身份、实体光源、动作因果、机位终点、场地调度或稳定末态若留空，模型就会替你决定。只补当前失败所缺的最小可见约束，并做单变量复测；若该维度已经明确仍失败，就转为 provider/model 能力或素材问题，不继续堆 prose。这个诊断不是要求把所有细节写满。

## 三种输出密度

### Fast

单镜头、目标明确时只给：

```text
目标 + 主体/动作 + 场景/光线 + 机位/运镜 + 稳定末态 + 必要限制
```

### Directed

需要参考图、首尾帧、动作或连续性时给：

```text
Objective
Reference roles
Subject locks
Format intent
Camera
Beat map
Physics/performance
Light/material
Audio policy
Negative constraints
Continuity out
```

### 镜头最小语义合同

复杂镜头先写语义，再翻译为 provider 字段：

```text
镜头作用 / continuity in / 参考及各自职责 / 身份与道具不变量
首帧 / 分段运动变化 / 主要机位路径 / 表演与物理反应 / 尾帧
光线与材质 / 声音与后期职责 / 最可能失败项 / continuity out
```

单镜头对用户只展示真正有用的字段（Simplified JSON，见上文；v1 扁平合同是它的前身）；内部 NBP v2 必填键不省略。Dreamina `@图片N`、Higgsfield media flags、Atlas fields、Lovart attachments、XYQ 参数都是 adapter 语法，不是通用 Prompt。可复制生图/视频 Prompt 的编译规则见 [prompt-compiler.md](prompt-compiler.md) 与 [model-adaptation.md](model-adaptation.md)。

### Production package

Production 包始终写真实任务与 shot ID；asset bible、approved panels、continuity in/out、provider adapter、post responsibilities 和专项 QC 只在复用、漂移、提交或交付风险实际需要时加入。无后期职责、无跨镜继承或不需预演的任务不为格式强填。

## 五问 Brief

写 Prompt 前回答：

1. 画面里是谁/什么？
2. 在哪里？
3. 核心可见、可听或其他可交付的感官变化是什么（可为一项或相容的因果序列）？
4. 摄影机为什么、如何运动？
5. 光、色彩、材质和表演创造什么情绪？

“高级、震撼、电影级”不能回答任何一问。

## 输入模式

### Provider-neutral preflight

Before writing provider syntax, declare the executable contract:

```text
primary_input_mode
allowed_secondary_inputs
incompatible_modes
live_evidence_or_TODO_VERIFY_LIVE
```

Each real submission has exactly one `primary_input_mode`. Text-to-video, start-frame, first/end-frame, reference-led generation, source-plate edit and extend are candidate primary modes; a provider may expose a different set. Reference audio or other media may be primary or secondary depending on the exact schema.

Do not announce all media types globally incompatible. Ask whether the exact model/account/endpoint allows each secondary input with the chosen primary mode. Unknown compatibility means the package is provider-neutral but not submit-ready; use `TODO_VERIFY_LIVE: mode_compatibility`, choose a deciding constraint, or design a documented two-stage path.

This preflight is conditional on real execution. A Fast prompt or script-only delivery does not grow into a Production package merely because these fields exist.

### Text-to-video

描述足以执行的可见场景，默认只保留最小可读的动作与镜头行为；叙事确需相容的分阶段动作或复合路径时可保留，并以 live schema 与代表镜证明可执行性，不用固定数量裁剪内容。

### Image/start-frame-to-video

图片已经定义外观。Prompt 只写变化：主体动作、镜头动作、环境响应、必须保持的不变量。不要重复描述所有静态细节。

### First/end frame

用于可控变身、产品 reveal、循环、matched transition。先检查首尾帧是否真能通过一条可见动作连接。

### Reference video

明确只迁移 camera path、动作、节奏、转场或效果时序中一个小而相容、可独立验收的职责集合；保留新主体、服装、产品、场景与色彩。不要一句“完全参考视频”把身份和背景一起复制。

### Reference audio

声明主要职责：节拍、声线、口型或环境气氛。输入音频与请求模型生成音频是两个不同控制项，分别 live 校验。

### Source-plate VFX

```text
使用上传视频作为底片。
保留身份、表演、服装、产品、构图、镜头路径、焦段感、曝光、颗粒、色温和时序。
只增加/替换：<一个明确效果>。
通过投影、接触阴影、遮挡、反射、碎屑、热、水或表面反应融入原片。
不重构背景，不改机位，不改时长。
```

### Extend

Use only when the endpoint supports it and the intended handoff is `continuous_time`. Bind the actual QC-passed ending state; do not use extend to avoid an intentional `editorial_cut`.

## Reference roles

一项输入只承担小而相容、可独立验收的职责集合；职责冲突、注意力竞争或超出 live 槽位时再拆，不按固定数量凑项：

- character：脸、发型、服装、身体轮廓；
- product/prop：外形、比例、材质、标签位置；
- location：空间关系、入口/出口、主光；
- style：色板、纹理、媒介，不复制人物；
- motion：运镜/动作/节奏；
- first/end frame：边界状态；
- audio：节拍/声线/口型/氛围。

每个参考除职责外再写一条 `must_preserve`：这张输入必须被原样保留的具体事实（如骨相与肤色、标签位置与比例、入口与主光方向）。职责说明它管什么，`must_preserve` 说明验收时看什么；两者都写不出来的参考先删掉。

用户已命名的标签保持不变；新标签使用短、稳定、可读的名字。标签只是语义名，提交时翻译成目标 adapter。

## Camera clause

镜头句只保留真正改变执行的维度；移动镜头通常从下列候选中选取最小充分字段，锁定镜头或保留 source camera 的任务可只声明锁定/继承方式与叙事用途，不为格式强填：

```text
物理机位 + 景别/焦段感 + 主要路径 + 方向/速度 + 对焦/重构图 + 起止构图 + 叙事用途
```

镜头动作从场景任务反推：

- 产品可读性：锁定、微推、受控慢绕；
- 情绪揭示：近景、缓慢 push-in；
- 行进/动作：tracking、side follow、克制手持；
- 空间/监控：静态广角、深焦；
- 隐藏主体：pan/tilt/crane reveal；
- source VFX：保留原 camera path。

短镜头默认聚焦一条清晰路径；orbit、dolly、pan 等若构成相容且有动机的连续轨迹，可以分阶段共存并先过代表镜。只有几何、注意力或修复风险需要时才拆镜。

## 动作与物理

`acting_task` and `scene_event` are optional semantic sources, not new universal Prompt slots:

- `acting_task`: what a character is trying to do to a person, object or space right now, using an executable verb and current tactic;
- `scene_event`: the occurrence that changes available action, knowledge, relation, goal, physical state or perception.

Compile them into visible behavior:

```text
scene event → visible tactic → timed body/voice response → physical consequence → post-state
```

Do not paste `knows / believes / wants / relation_power` as invisible exposition. Use those state fields to prevent impossible behavior, then output what the camera or microphone can observe. “She feels sad” is not an acting task; “she keeps her mother at the table by sorting the cutlery instead of answering” is performable. Character-free transformation or atmosphere work may omit the task entirely.

复杂动作按因果链写：

```text
起因 → 蓄力/负载 → 接触/作用力 → 身体/物体反应 → 余势 → 稳定末态
```

补充真实可见证据：主光方向、影子、惯性、衣料/液体/尘土/碎屑响应、动作模糊、手指停顿、下颚收紧。不要写心理活动、嗅觉或镜头外发生的状态变化。

## Beat map

时码不是强制模板；只有多动作、多镜头或精确节奏时使用。每次 cut 后重新锚定主体位置、屏幕方向、道具与连续性状态。短片最后应留可剪辑的 hold 或明确 handoff。

复杂动作按真实片长分段，例如「0–3s：她把戒指推回桌面，手指停在杯沿；镜头从双人中景缓慢推进。3–6s：对方伸手去拿，她先一步按住戒指；镜头停在近景，杯中水仍在晃，末帧稳定。」秒数是分段写法示例，不是模型时长能力，也不是固定模板。

## 对白与声音

- 原生对白是半稳定能力，提交前核验语言、口型、音轨与 generated-audio 支持。
- 一镜优先一个清晰可见说话者；写准确台词、语气、节奏、微停顿和空间声。
- 复杂画面无法同时承载对白时，做独立 dialogue pickup，再进入后期。
- 精确字幕、CTA、品牌文案和法律文字路由为 `post_insert`，留给确定性后期。

### 语言契约

`audio.dialogue[]` 非空即代表**口播语言**：里面写的是哪种语言，角色就用哪种语言开口。它必须与发布地区一致——出海项目写中文台词就会得到中文口播，不会因为提示词其余部分是英文而自动翻译。

出海项目（`audio.dialogue[]` 为英文）的适配器 prompt 必须同时含三段，缺一段就会复发哑剧或自动烧字幕：

1. **节拍内嵌台词**：台词写在对应动作节拍里，注明说话者与起止时刻，不集中堆在末尾；NBP v2 用 `beats[].say` 表达，见下文「剧本锁」；
2. **结尾集中声明**：prompt 末尾再集中声明一次对白与语言，`All dialogue is spoken in English.`；adapter 在有 `beats` 时只声明句数与「各说一次、逐字不改」，不重复台词原文，避免被念成第二遍（两种写法哪种更稳待核实，A/B 只改这一项）；
3. **禁字幕**：显式写 `no subtitles, no on-screen text, no burned-in captions`；字幕由确定性后期生成。

三段的具体写法与口型压缩（词数与镜头时长的对应）见 [platform-overseas.md](platform-overseas.md) 的「## 英语对白与口型压缩」。

可选子键 `audio.dialogue_lang` 写 BCP-47 语言标签（`en`、`zh-CN`），只在台词文本自身判不出语言时才需要：`scripts/validate_nbp_prompt.py` 在 `dialogue[]` 非空、`dialogue_lang` 缺省且台词正文混用汉字与拉丁字母（或完全没有可判文字）时发 warning `DIALOGUE_LANG_UNSET`，不改退出码。写了这个子键就不再判定。它是可选子键，不是新根键；不写时模板与合同都不受影响。

### 对白字符串写法

- 每条 `audio.dialogue[]` 字符串形如 `说话者（语气／发声提示）：台词。`，例：`男主（咬牙、压低声音）：你再说一遍。`
- 括号内只写可听见的发声方式：语速、音量、气声、停顿、哽咽；不写内心活动。唯一例外是括号末尾的 `对<听者>`（如 `林夏（压低声音，对老周）：钥匙给我。`）：它告诉模型这句话朝谁说、视线落在谁身上，`short_drama` 模式每句必写，`cinema` 模式按需。听者名同样与 `characters[].name` 一致；画外或独白不写听者。标点按实际停顿写，逗号、句号与省略号各自对应不同的停顿长度。
- 说话者写剧本角色名，并与 `characters[].name` 逐字一致：adapter 把名字绑到该角色的参考槽（Seedance 渲染为 `Mira @图片1`），模型才知道哪张脸说哪句。身份锚仍是 `characters[].ref`，名字只是指向它的标签。`旁白`、`画外音`、语气里带 `画外`／`V.O.`／`O.S.` 的台词不需要绑定。
- 校验器 warning：说话者没有对应的 `characters[].name` 报 `DIALOGUE_SPEAKER_UNBOUND:<名字>`；台词没写说话者报 `DIALOGUE_SPEAKER_MISSING:<路径>`。两者不改退出码，但生成前必须清零。
- 字符串内不出现 `@`：校验器会把任何 `@…_vNN` 当标签并要求注册，adapter 遇到标签会走去标签／去标点路径；无标签的字符串在所有方言里原样透传。
- 一条字符串只放一个说话者；多人抢话拆成多条，或拆成独立 dialogue pickup。
- 这是字符串内的写法约定，不新增 JSON 键；新键会被判 `V2_UNKNOWN`。

### 剧本锁：beats 与 script_ref

对白戏最常见的三种失控是：台词被改写或漏说、说话者张冠李戴、台词在错误的动作时刻出口。三个可选字段把剧本锁进镜头规格：

| 字段 | 形状 | 作用 |
|---|---|---|
| `characters[].name` | 非空字符串，同镜内不重名（大小写不敏感，重名报 `V2_DUPLICATE_NAME`） | 台词说话者绑定到这张脸 |
| `beats[]` | 每项 `start_s` / `end_s` / `action` 必填，`camera` / `say` 可选；时间递增、不重叠、不超过 `duration.target_s` | 把动作、机位和台词按秒分段；adapter 渲染为 `分段：[0–1.5秒] …`，台词写进它出口的那一段 |
| `script_ref` | `source_beats[]`（剧本 beat 编号）与 `context`（一句话前情） | 镜头追溯到剧本；`context` 只进 adapter notes，不进 prompt，也不绑定媒体 |

- `beats[].say` 按顺序拼起来必须逐字等于 `audio.dialogue[]`，否则报 `V2_BEAT_DIALOGUE_MISMATCH`。台词只有一个真源，改词就两处一起改。
- 时间窗口非法报 `V2_BEAT_TIME:<路径>`。
- 每秒口播量超过启发式上限报 warning `DIALOGUE_TOO_DENSE:<路径>`。上限是 5 个汉字／秒，英文每词按 1.5 计，是经验值，不是模型实测上限。先删半句，再考虑加时长。
- `context` 写这个角色此刻知道什么、以为什么，给写 prompt 的人或 LLM 选语气用；模型拿到的只有可演的语气括号和动作。背景故事写进 prompt，模型要么忽略，要么把它画出来。
- 图像规格可以带 `script_ref`，但禁止 `beats`。
- 多镜对账：`python3 scripts/check_script_coverage.py --script <剧本> --shots <按剪辑顺序的镜头 JSON…>`，见 [prompt-compiler.md](prompt-compiler.md#剧本锁编译)。

## Negative constraints

先把“不要 X”转成可见、可执行的正向物理锁；`negative` 按实际残余风险与目标 provider 的当前能力取 0..N，0 条时省略字段，存在时只保留真正可能污染交付的有效项。字段级转译与示例见 [prompt-compiler.md](prompt-compiler.md#负面约束正向化)：

```text
保持同一张脸、产品轮廓和标签位置；
不新增产品变体；不生成伪文字、水印；
不改变背景和镜头路径；不发生镜头外状态跳跃。
```

优先正向锁定；不要堆几十个 `no`。

## 语言与格式

- 默认使用简体中文；用户指定其他语言则跟随。
- 技术字段无需固定英文，除非目标 provider 或用户要求。
- 简单请求可只输出一个复制块；复杂请求可用结构化包。
- 不强制 SFX-only；声音策略由目标决定。
- 不把 `8K`、胶片型号、镜头品牌、NON-IP 当通用质量咒语。

## 迭代

一次只改一项：源资产 → 参考职责 → 动作/物理 → 镜头/节拍 → 光线/风格 → provider/model。多个变量同时变化的结果标记为无法归因。

## NBP v2 中间规格

根对象以 `"nbp_version": "2"` 选择 v2；video 的八个必填键如下：

| 键 | 合同 |
|---|---|
| `characters` | 角色数组；有人物时每项含 canonical `ref`、非空 `state` 与 `wardrobe`。风景/产品镜允许 `[]`，校验器发 warning `NO_CHARACTERS`，不改退出码。 |
| `scene` | 非空字符串。 |
| `action` | 非空字符串。 |
| `camera` | `shot_size / angle / movement / lens_note` 四个非空字符串。 |
| `aspect_ratio` | 模型中立比例枚举，以 `scripts/validate_nbp_prompt.py` 的 `V2_ASPECT_RATIOS` 为准（B-32）；集合外值报 `V2_BAD_RATIO`，目标端合法性由适配器按 capabilities allowlist 校验。 |
| `duration` | 正数 `target_s` 与非空 `live_check`；未知时写 `TODO_VERIFY_LIVE`。 |
| `audio` | `dialogue[] / ambience / music / sfx` 四键齐全；可选子键 `dialogue_lang` 见「语言契约」。 |
| `references` | 可空数组；每项含 canonical `ref`、`character/prop/location/style/motion/audio` 之一与非空 `use`；`first_frame` / `last_frame` 是 `use` 的精确保留字面量。 |

`characters[].ref` 与 `references[].ref` 同形，均须采用 canonical `@kind_name_vN` 形状，正则以 `scripts/validate_nbp_prompt.py` 为准：`^@[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9]+(?:_[A-Za-z0-9]+)*_v[0-9]+$`，例如 `@char_mira_v01`、`@location_archive_night_v01`。`audio.dialogue[]` 必须为字符串数组，非空即代表口播语言。

可选根键 `task_mode` 取 `omni_reference / first_frame / first_last_frame / edit / extend`，缺省 `omni_reference`；其余可选键是 `subject / light / style / motion / negative[] / continuity / live_params / beats[] / script_ref`，validator 对 `live_params` 只检查 object 类型；`characters[]` 每项可加可选 `name`。`beats` 与 `script_ref` 的形状见「剧本锁」。image 使用同一规格，但禁止 `duration`、`audio`、`motion`、`beats`，其余六个核心键必填。

选择写 `continuity` 时，必须同时提供非空字符串 `story_time_id / in_state / out_state` 和 `mode: sparse|tracked`；只写起止状态仍不完整。单镜可用 `sparse`，不需要此块时整个省略，不留半成品对象。可直接沿用 [NBP v2 视频模板](../templates/nbp-v2-video-prompt.json) 的 shape。

模式一致性由 validator 关闭歧义：`omni_reference` 禁止帧 use；`first_frame` 要求恰好一个首帧且无尾帧；`first_last_frame` 要求首尾各一个；两种帧模式不得夹带非帧引用；`edit / extend` 至少一个 motion role 且只允许 motion 引用。适配器只翻译已验证模式，不从 `use` 子串猜模式。

| 错误码 | 含义 |
|---|---|
| `V2_MISSING:<key>` | 缺少根级必填键。 |
| `V2_UNKNOWN:<key>` | 出现未知键。 |
| `V2_IMAGE_FORBIDDEN:<key>` | image 出现禁用键。 |
| `V2_BAD_RATIO:<value>` | 画幅不在允许集合。 |
| `V2_DURATION_NO_LIVE_CHECK` | 时长没有非空 live 凭据引用或占位。 |
| `V2_BAD_TAG:<path>` | canonical tag 语法错误。 |
| `V2_BAD_ROLE:<path>:<value>` | reference role 非法；缺失值写 `missing`。 |
| `V2_BAD_MODE:<value>` | `task_mode` 不在五值枚举。 |
| `V2_MODE_CONFLICT:<detail>` | `task_mode` 与引用计数、帧 use 或 role 不一致。 |
| `V2_BAD_TYPE:<path> <detail>` | 字段类型、非空性或嵌套形状错误。 |
| `V2_DUPLICATE_NAME:<name>` | 同镜两个角色同名，台词无法归属。 |
| `V2_BEAT_TIME:<path>` | 分段时间非法、重叠或超出 `duration.target_s`。 |
| `V2_BEAT_DIALOGUE_MISMATCH` | `beats[].say` 与 `audio.dialogue[]` 不逐字同序。 |

`render_nbp_adapter.py` 退出码：成功为 `0`，校验失败为 `1`，`ADAPTER_REQUIRES_V2` 为 `2`；`INVALID_JSON`、`INVALID_REGISTRY_JSON`、`INVALID_CAPABILITIES_JSON` 及文件不存在为 `3`。

缺少 `nbp_version` 或值为 `"1"` 时继续走原 v1 合同；v1 模板继续有效。v2 是 provider adapter 的内部默认输入（对应 `render_nbp_adapter.py` 的八个 `--target`），不反向改变 v1 字段与行为。用户面默认是 Simplified JSON，`--schema auto` 先把它规范化为本节的 v2 IR，再交适配器；直接手写的 v2 规格照常校验。
