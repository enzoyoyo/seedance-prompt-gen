# Prompt Compiler

## v7 编译链：Simplified JSON → NBP v2 IR → 目标方言

用户看到的是扁平 Simplified JSON（字段表见 [prompt-contract.md](prompt-contract.md#用户面simplified-jsonv7-默认展示)）；适配器吃的是 NBP v2 IR；真正提交的是目标方言。三层各管一件事，任何一层都不替另一层做决定。

```bash
# 1. 规范化 + 校验（Simplified JSON 与手写 v2 都接受）
python3 scripts/validate_nbp_prompt.py --schema auto --type video --input shot.json
# 2. 编译到目标方言，只生成交接结果，不提交
python3 scripts/render_nbp_adapter.py --target seedance_2_5 --schema auto --input shot.json --json
```

`--schema` 取 `auto | simplified | nbp_v2 | nbp_v1`（校验器与编译器均接受显式 `--schema nbp_v1`，编译器对旧 v1 统一以退出码 `2` 返回结构化 JSON `ADAPTER_REQUIRES_V2`）：`auto` 先看根对象 `nbp_version`（`"2"` 为 `nbp_v2`，`"1"` 为 `nbp_v1`）；无版本号时，仅当字段属于 `DISPLAY_FIELDS`、含核心内容键且至少带一个 v7 特征键（如 `mode`、`refs`、`aspect_ratio`、`creative_mode`、`task_mode`、`duration_s`、`live_params`、`beats`，或单键 `{"prompt": ...}`）才判为 `simplified`，否则（如仅含 `{action, continuity_ref}` 的旧扁平规格）归为遗留 `nbp_v1`。`--target` 设八个标准目标，另保留两个兼容别名（`seedance` 指向 2.5 家族／旧收据路径，`elevenlabs` 对应网页 Seedance 2.5 分档计价与边界核验）：

| `--target` | 方言要点 | 编译时必须检查 |
|---|---|---|
| `seedance_2_5` | `beats[]` 渲染为整数秒时间戳（`[0-3s]`，小数秒报 `INTEGER_SECOND_TIMESTAMPS_REQUIRED`）；对白 `角色（情绪）：内容`；支持多视图与白模参考 | 方舟 `ark` 实测收据记录支持 `4..30` 整数秒（以及供应商侧自动时长枚举 `-1`，该值仅属供应商收据范围；本地规划／NBP v2 IR 校验强制 `duration.target_s > 0` 且 `endpoint="planning"` 限 `4..15` 整数秒）；参考数与 `ratio=adaptive` 按 `references/model-capability-matrix.json` 核对 |
| `seedance_2_0` | `beats[]` 只输出镜头序号（`Shot 1`／`Shot 2`），不强制也不写秒级时间戳 | 2.0 边界独立（`4..15s`、参考上限 `9/3/3` 总计 `<=12`），绝不混套 2.5 |
| `google_flow` | 按引用自动冠 `Text:`／`Ingredients:`／`Frames:`；Veo 3.1 一条 clip 一个英雄动作，Omni 1.2 区分五种模式，Nano Banana 2.1 做两步法静帧 | Veo 离散时长 `4/6/8s`（参考或 1080p 需 `8s`）；Omni 带参考／首尾帧／延长 `<=10s`；Flow 敏感词表 |
| `higgsfield` | 跟随实际底层 model ID；prompt 若以 `@` 开头自动加 `Prompt: ` 前缀防 CLI 误判为本地路径 | 底层模型、`media_roles`、CLI `draft_job_id` 与 REST `draft_id` 互斥，见 [adapter-higgsfield.md](adapter-higgsfield.md) |
| `kling` | 首尾帧映射进交接参数 `start_image`／`end_image`，普通参考进 `image_references`／`video_references`（正文槽位 `Image 1`） | 含首尾帧 `<=10` 图、总计 `<=15`；`kling4_0` 的 `live_params.dynamic_range="hdr"` 仅限 `1080p`／`4k` |
| `grok_imagine` | 仅本地代理 `live_params.route="openai_compat"` 用 `<IMAGE_0>` 起算占位（上限 7 图）；默认 `xai_api`／`grok_web` 用 `Image 1` | `grok_web` 显式传 `model`／`resolution` 报 `WEB_MODEL_OR_RESOLUTION_UNVERIFIED`，分记 `requested/reported/measured` 并事后 `ffprobe` |
| `xyq` | 图像（`seedream_5_5`）把比例译成整数 `ratio` 枚举、正文用 `<Picture 1>`；视频输出比例与 `task_type` 中间交接值 | 视频通用 `ref_limits` 未固定，带参考离线编译报 `REF_LIMITS_UNVERIFIED`；版权词与 `ret` 码见 [adapter-xyq.md](adapter-xyq.md) |
| `lovart` | `attachments` 列表 + 首行强加立即单条生成指令 | 通用 `ref_limits` 待 live 核验；`--prefer-models` 非硬锁，核回执 `reported_tool`，见 [lovart-execution-notes.md](lovart-execution-notes.md) |

### 编译输出

每次编译输出同一组字段：

```text
prompt_text / parameters / ordered_bindings / unsupported_requirements / capability_receipt_hash
```

- `ordered_bindings`：canonical 标签 → 目标槽位（`@Image 1`、`Image 1`、`<Picture 1>`、本地代理 `<IMAGE_0>`）的有序映射；顺序就是上传顺序。
- `unsupported_requirements`：规格要求了但目标做不到或未核验的项（尾帧、某条原句、超限或未核参考、音频、矩阵过期）。非空即编译失败（`ok: false`），不交付半成品 prompt。
- `capability_receipt_hash`：对 `{matrix_digest, target, exact_model_id, capability_row, parameters}` 计算的 SHA-256（若在进入目标编译前发生早期 schema／JSON 错误则为 `null`），写进 generation log；矩阵、目标模型行或展开参数任一变化时哈希即变。

### Fail-closed：报错，不静默丢

旧行为里最贵的失败是「编译成功但悄悄少了一样」：尾帧没传、台词被改写、第三张参考被截掉、音频被关掉。v7 一律报错：

| 情况 | 动作 |
|---|---|
| 目标不支持尾帧／首尾帧模式 | 报错，列出可选目标或改为拆镜，不降级成只给首帧 |
| 参考数超过目标上限或矩阵标 `TODO_VERIFY_LIVE` | 报 `REFERENCE_LIMIT` 或 `REF_LIMITS_UNVERIFIED`，不按顺序截断或放行未核配额 |
| 时长不在目标枚举或区间内 | 报错，不就近取整 |
| 对白原句无法在目标里原样承载或说话者未绑定 | 报 `UNKNOWN_DIALOGUE_SPEAKER` 等错误，不改写台词 |
| 目标没有原生音频而规格要求原生对白 | 报错并建议独立 dialogue pickup，不静默关音频 |
| prompt 以 `@` 开头（Higgsfield CLI）或含路径样式的 `@…` | 报错或按适配器已验证的转义写法改写，并在输出中注明 |
| 能力矩阵已过 `expires_at` | 默认报 `CAPABILITY_RECEIPT_EXPIRED` 阻断编译（仅显式 `--allow-expired` 降为 warning） |

### 确定性

在**同一份输入规格、同一版 `references/model-capability-matrix.json` 与同一有效期状态**（编译日期未跨过矩阵 `expires_at`，或显式固定 `--today`）下，同一 `--target` 的输出逐字节相同；字段排序、标签编号、空白都固定，因此可用哈希判断「规格与矩阵均未变就不用重编」。编译通过仍是 `planning_only`：它不证明账号可提交，提交前仍按 [provider-execution.md](provider-execution.md) 做 preflight。

## 默认产物

先把镜头语义编译为 NBP 中间规格，再按目标模型翻译。v2（`"nbp_version": "2"`、嵌套；见 [prompt-contract.md §NBP v2](prompt-contract.md#nbp-v2-中间规格)）是上文八个 `--target` 共用的内部 IR，用户面由 Simplified JSON 承担；v1 扁平合同只保留给 `nbp_version` 缺省或为 `"1"` 的旧规格。

以下扁平骨架、白名单、机器规则与字段表只适用于 v1：

```text
subject / action / scene / camera / light / style / motion / duration /
audio / continuity_ref / negative
```

v1 生图白名单为 `subject / action / scene / camera / light / style / continuity_ref / negative`；生视频白名单为完整 11 字段。类型由 validator 的 `--type image|video` 声明，不能在 JSON 内新增第 12 个类型键。

v1 只输出当前镜头有用的字段；除 `continuity_ref` 与 `negative` 使用字符串数组外，其余字段均为字符串，不建嵌套对象；空字符串、`null`、空数组、默认占位字段全部省略。上述“只输出有用字段／不建嵌套／空字段省略”只对 v1 生效；v2 按链接合同保留必填键。

v1 机器规则：根必须是 object；未知键、字段类型错误、纯空白字符串、空数组、空数组项与重复数组项均报错。`negative` 为按风险取用的 0..N：没有残余风险时省略字段；存在时必须是非空、不重复字符串数组，条数再受目标 provider 提交前 live 上限约束。生图出现 `motion / duration / audio` 视为错误。

| 字段 | 写什么 | 常见省略条件 |
|---|---|---|
| `subject` | 主体身份、当镜状态和正向不变量 | 无主体的纯环境镜 |
| `action` | 一条可见因果动作与稳定末态 | 纯资产定型图 |
| `scene` | 地点、空间关系、前中后景和世界状态 | 无场景语义且背景已由资产测试锁定的干净底板 |
| `camera` | 机位、景别/FOV 感、单一主路径、起止构图 | 不涉及摄影的结构图 |
| `light` | 实体光源、方向、软硬、光比/阴影职责 | 无影资产底板可并入 `style` |
| `style` | 色板、媒介、纹理和排他性视觉行为 | 资产已完整承载且无额外风格 |
| `motion` | 主体、摄影机和环境的速度/路径/余势 | 静态生图 |
| `duration` | 创意目标时长及 live 校验状态 | 静态生图 |
| `audio` | 对白、现场声、参考音轨或后期职责 | 无音频职责 |
| `continuity_ref` | 当前批准的 canonical `@` 资产标签 | 真正无连续性依赖的试验镜头 |
| `negative` | 正向化后仍无法表达的高风险残项，数量按风险与 provider live 能力取 0..N | 无残余风险时省略字段 |

合法示例优先见 [nbp-v2-image-prompt.json](../templates/nbp-v2-image-prompt.json) 与 [nbp-v2-video-prompt.json](../templates/nbp-v2-video-prompt.json)；v1 旧文档仍见 [nbp-image-prompt.json](../templates/nbp-image-prompt.json) 与 [nbp-video-prompt.json](../templates/nbp-video-prompt.json)。

## 编译顺序

1. 从 shot contract 读取 `objective / continuity in / visible action / camera job / actual state`。
2. 只解析当前 `approved` 资产 ID；`candidate / rejected / superseded` 立即停编译。
3. 把静态事实放入唯一字段，避免同一服装、镜头或光线在多处重复争权。
4. 将否定句改成正向物理锁，只把不可转译的高风险项留在 `negative`。
5. 依据目标模型选择密度；未知时保留简化 JSON，并标 `TODO_VERIFY_LIVE`。
6. 用目标 adapter 的 live schema 把 canonical 标签展开为参考槽、附件或文本语法。
7. 在 v1 或 adapter 最终序列化阶段，输出前删除空字段；NBP v2 阶段必填键与合法空数组不得删除。检查 JSON 合法性和 continuity in/out 相容性。

### 外来教程与长 Prompt 的编译预检

用户要求学习或改用教程时，先对照正文、分镜时间线、参考绑定和 Recreate/UI 参数，不直接复制提交。逐项核对 `characters[].state/wardrobe`、`references[].ref/use`、`aspect_ratio`、`duration.target_s`、`action` 与 `camera`：同一人物不能有矛盾尺度，同一槽位不能混指不同资产，镜头正文与总数/时码不能互相冲突，变换完成态不能在下一镜无说明地复原。用户当前 brief 与批准资产优先；仍有关键冲突就记录待裁决项，不猜来源中的哪一段正确，实际参数仍走 live schema。

把反复出现的规则、失败句、计数与禁令压成「本镜目标 → 唯一真源/不变量 → 动作与机位 → 交接状态 → 声画分工」；硬性可观察失败条件移入 QC，`negative` 只留正向锁定后仍存在的风险。保留因果与精确状态，按下面的节拍预算拆分，不以原文长度证明可执行。匹配剪辑与变换类的预检实例见 [commercial-match-cut.md](commercial-match-cut.md)。这些是语义人工核对，现有结构校验器不会自动发现全部正文冲突。

### 条件化序列化层级

多镜头且目标方言允许层级时，把跨镜头共用的视觉/连续性规则置于镜头块之前，把每镜局部动作与机位留在中间，并把全局音频政策放在镜头块之后。它是“共享规则只声明一次”的层级原则，不是固定三层模板：单镜头可以折叠；在 v1 或 adapter 最终序列化阶段，音频不相关时删除；provider 不支持结构块时由 adapter 改写为等价语法。

全局层不得塞入镜头局部时码，镜头层不得重复整份视觉圣经，音频层不得偷偷改变动作或剪辑。具体块数、字段名和顺序仍由当前风险与 live schema 决定。

## 资产 ID 与标签协议

canonical ID 属于资产清单；`@` 标签是 Prompt 中的稳定别名。建议：

```text
@char_mira_v01
@outfit_mira_courier_damaged_v02
@prop_brass_key_v02
@location_archive_night_v01
@style_amber_noir_v01
@frame_s03_relay_v01
```

规则：

- 标签只含字母、数字和下划线，以 `@kind_` 开头并带版本；
- 完整格式为 `^@[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9]+(?:_[A-Za-z0-9]+)*_v[0-9]+$`；
- kind 必须匹配语义角色：常用映射为 `char→character`、`outfit/wardrobe→wardrobe`、`prop→prop`、`location→location`、`style→style`、`frame→first-frame/end-frame`；
- 一个标签只解析到一个 canonical asset 和一个批准版本；
- 标签名稳定，不用 `@image1` 之类 provider 槽位冒充 canonical ID；
- 同一资产在 `subject` 与 `continuity_ref` 重复出现时，编译器去重引用，不复制整段描述；
- 无法解析、版本歧义或源文件缺失时输出错误，不猜测最像的文件。

编译登记表至少包含：

| canonical tag | kind | approved source/version | semantic responsibility | target-provider binding |
|---|---|---|---|---|
| `@char_mira_v01` | character | `char-mira-face-v01` | face, hair, build | live adapter resolves |

### 多参考交接与运镜落点

用户素材标签、canonical tag、provider 槽位分栏保存。用户给的 `@Image 1` 等原始标签原样保留在映射表，NBP 内转换为已登记的 canonical tag，最终槽位由执行 adapter 绑定；不在原始素材说明中悄悄改号，也不把外部标签直接塞进 NBP 冒充可解析资产。

参考职责有冲突时，逐条在 `references[].use` 写清“取什么、舍什么、画面中取谁”：身份由批准角色资产定义；瞬时姿态、手持物与空间位置由通过 QC 的前镜末态定义；动作或摄影机参考只提供声明的运动。多人图注明位置或可见特征，不默认选中间人物。若两份批准真源互相矛盾，先解决真源，不能要求模型折中。

例如：角色图定义人物身份与本场服装；舞蹈参考只取脚步和节奏，舍弃其中的人物、衣着、背景与声音；前镜末帧确定开场手位。动作参考要求换手而末态仍需左手持物时，将交接动作写进 `action`，否则退回修改参考职责。

运镜术语落到 `camera.movement` 的实际路径与停止条件：谁相对谁移动、向哪边、什么画面事件后停止。“慢推”写成朝目标接近并在证物可辨认时停；“跟拍”交代人物行进方向与相机相对位置。成对运镜必写方向；五槽写法、首帧适配前提与近义运镜守恒量见 `storyboard-camera-direction.md` §13。`audio` 分开保留说话者、逐字对白、现场声和音乐职责。只为本镜真正需要的事件写时序，不套固定切镜秒数。

方法来源：dexhunter 的[引用用途与运镜语汇](https://github.com/dexhunter/seedance2-skill/blob/e06c7c63a766d623004a2807881c30685ce517af/zh/SKILL.md)和 Emily 的[参考职责分离](https://github.com/Emily2040/seedance-2.0/blob/d2b529947a43880e2b8b9a411c8a154f024d3dc9/references/reference-transfer-contract.md)。此处独立改写并适配 NBP；上游模型参数、标签方言和配额不迁移。

目标方言展开示意：canonical `@char_mira_v01` 可在某个 adapter 中映射为参考图槽、Element、LoRA/token 或附件句柄；这些值生成前实时读取，不写回通用 Prompt。Seedance 的 `@图片N`、Higgsfield media flags 等都属于 adapter 层。

`validate_nbp_prompt.py` 会扫描所有字符串字段，不只检查 `continuity_ref`；正文使用的 tag 必须登记进 `continuity_ref`。不提供 registry 时只证明结构和 tag 语法，输出 `syntax_only` 警告。提供 registry 时，prompt package 必须先完整通过主 validator 且为 `provider_ready`；asset manifest 的命中项必须含合法 `entity_id / version / asset_kind / approved_source_path / source_sha256`。两种 registry 都要求每个 tag 恰好解析一次、状态为 `approved`、kind 与语义角色匹配，并实算源文件哈希；否则 `tag_resolution` 为 `failed`，不能宣称已解析。

## Prompt package 生产门

`templates/prompt-package.json` v1.3 使用 `package_status: planning|provider_ready`。planning 允许 candidate 并返回警告、`provider_ready: false`，同时禁止选择 provider adapter；`rejected / superseded` 在任何活动包中都报错。provider_ready 要求所有引用为 `approved`、canonical tag 与版本唯一、source path 存在且 SHA-256 与文件实算一致；这里表示“资产和结构已可进入 adapter”，不声称已选择 adapter、提交任务或通过像素 QC。

顶层 `continuity_mode: sparse|tracked` 是显式机器路线，由实际 block、跨镜复用/继承和已声明风险选择；不得从 `production_class` 自动推断，也不得把镜头数当唯一阈值。任何 production class 都可在没有跨镜继承职责时选择 `sparse`；一旦身份、服装、道具、scene/light、轴线或持续世界状态需要跨镜守恒，或其漂移风险足以影响交付，就选择 `tracked`。

`sparse` 可省略 `continuity_rules`、每镜 `continuity_in / continuity_out / continuity_changes` 与 camera axis 状态，也可只登记实际需要的规则/状态维度；若声明 state，必须成对声明 in/out，已声明的每个 identity/prop/scene/light/style/world-state 维度仍按已登记规则严格校验。若声明任一 camera axis 字段，则 axis/side/transition/coord 必须成套且通过几何校验。

`tracked` 保留完整连续性门：必须提供完整 `continuity_rules`，每镜 state 必含 `characters / props / scene_variant / light_sources / persistent_world_state`，并要求 camera axis 状态、精确 change 和相邻交接。结构化 state 记录角色 asset/坐标/朝向/画面方向/服装、道具 owner/hand/state、scene variant、实体光和持续世界状态；camera 记录 axis/side/coord。`tracked_props` 的 `allowed_configurations[{asset_version,owner,hand,state}]` 防止把各自合法的状态与位置任意交叉，`scene_variants` 登记允许的实体光组合，`scene_transitions[{from,to}]` 只放行真实地点/时段转换。validator 比较上一镜 out 与下一镜 in，并要求 `continuity_changes[{path,from,to}]` 精确覆盖 in→out 差异。

两种 mode 都使用同一严格枚举：character 一旦声明仍必含 `eyeline_target`。`facing = north|south|east|west|camera|away`，`screen_direction = left|right|center|offscreen`，`hand = left|right|both|none|inside|attached|environment`，axis side 为 `left|right|on_axis`，`axis_transition = none|visible_cross|neutral_reset|along_axis|new_axis`；非 `none` 需写 reason，首个已声明 axis 的镜头必须为 `none`。变化示例：`{"path":"props.blue-envelope.owner","from":"heqing","to":"luoxing"}`。

`prompt` prose 仍是人读/编译产物，validator 只检查其中 canonical tag 的格式与 registry 解析，不做自然语言语义理解；输出固定含 `structural_only: true` 与 `prompt_semantics_checked: false`。因此绿灯只证明包结构、资产门和声明连续性，不替代 prompt 人审或真实生成后的视觉 QC。

在 Skill 根目录运行：

```bash
python3 scripts/validate_prompt_package.py --input /path/to/prompt-package.json
python3 scripts/validate_nbp_prompt.py --type image --input /path/to/nbp-image.json --registry /path/to/prompt-package.json
python3 scripts/validate_nbp_prompt.py --type video --input /path/to/nbp-video.json --registry /path/to/prompt-package.json
```

## 负面约束正向化

先问“正确的画面遵守什么物理事实”，再写锁定：

| 原始否定 | 正向锁定 |
|---|---|
| 不要多手指 | 每只可见手具有五根解剖分离的手指，关节与抓握接触连续 |
| 不要脸崩 | 头骨比例、眼距、鼻唇位置和永久标记在全镜头保持不变 |
| 镜头不要漂 | 摄影机固定在锁定三脚架上，位置、俯仰和水平角保持恒定 |
| 道具不要消失 | 道具始终由右手握持，方向和尺寸相对掌宽保持恒定 |
| 不要跳轴 | 摄影机始终留在已登记的轴线同侧，双方视线方向互补 |
| 不要背景复原 | 已倒下的椅子和地面碎片作为静态地标持续存在 |

`negative` 只留难以正向化且会污染交付的残项，例如伪文字、水印、未授权 Logo 或模型自生字幕。数量按实际残余风险与当前 provider 能力取 0..N；0 条时省略字段，存在时每条都必须有效且不重复。不要粘贴通用 negative 词库，也不要同时写相互矛盾的正负命令。

## 引语通道与材质覆盖

圣经里的直投引语不扩展默认 JSON 字段：`Speech` 编入 `audio`，`Movement` 编入 `action/motion`，`Stillness` 编入 `subject` 或动作末态，唯一附着音轨约束编入 `audio`。引语内部不写角色名，身份仍由 `@char_*` 解析。`audio.dialogue[]` 里的说话者与 `characters[].name` 逐字一致，adapter 据此把台词绑到那张脸的参考槽；身份仍由 `characters[].ref` 解析；写法见 `prompt-contract.md` 对白与声音节。

参考图的剪裁与目标材质冲突时，必须声明职责边界和唯一正向材质，例如：`@glove_cut_v01 provides cut and coverage only; final surface is 100% matte black leather with no metallic response.` 将它放入 `subject` 或 `style`，不另造空泛的 `material_override` 键，也不让模型做两种材质的折中平均。

## 节拍预算

单次生成默认承载 **1 个主动作 + 1 个反应**。超出就拆 job 再剪，不靠加长提示词或拉长 `duration.target_s` 把多拍塞进一条。

塞多拍的稳定后果是模型只演最静态那一拍：要「推门冲入」得「扶门蓄势」，要「破门而入」得「门关着等待」。一次塞五个镜头的后果更大——「把五个镜头塞进一次生成，结果侧翼战机变成登陆舰，机甲路线和场景关系也发生变化」，这时错的不是额度，是打包粒度。

因此 `action` 里写「动作进行中」的可见状态，不写动作的准备姿态：首帧就落在动作已经开始的那一刻（`OPEN ON ACTION`，写法见 [seedance-first-frame-action.md](seedance-first-frame-action.md)），`motion` 只描述这一主动作的路径与余势，反应写成它的后果而不是第二个独立事件。

拆 job 时每条仍是完整的因果链，用通过 QC 的真实末态接下一条；不要把一个动作切成「蓄力」「接触」「余势」三条各自不成立的生成。逐拍验收回 [production-qc.md](production-qc.md#要的动作-vs-实际演的动作) 的对照表。

## 剧本锁编译

剧本是台词的唯一真源。镜头规格只搬运，不改写；装不下就回剧本改，改完重新对账。

1. **剧本先编号**：每个 beat 用 `[S3-B2]` 起头，动作行以 `△` 开头，对白行写 `角色名（语气）：台词`；写法见 [script-writing-craft.md](script-writing-craft.md)。
2. **逐镜搬运**：`script_ref.source_beats` 列出本镜覆盖的 beat。台词原样复制进 `audio.dialogue[]`，说话者名与 `characters[].name` 一致。语气括号可以改写成可演的发声提示，台词正文一个字不改。
3. **需要口型时机就写 `beats[]`**：一段只放一个说话者；`say` 放在台词真正出口的那一段；说话前留一段反应或动作，说完留一段 hold 给剪辑。
4. **单镜校验**：`python3 scripts/validate_nbp_prompt.py --type video --input <镜头.json>`，`DIALOGUE_SPEAKER_*` 与 `DIALOGUE_TOO_DENSE` warning 清零后再提交。口播太密就先删半句，删句要回剧本删。
5. **多镜对账**：

```bash
python3 scripts/check_script_coverage.py --script <剧本.md> --shots <按剪辑顺序的镜头 JSON…>
```

台词正文逐字比较，只忽略空白、引号和全半角差异；语气括号不比较。退出码 `0` 全部对上，`1` 有错，`3` 文件或 JSON 读不了。

| 码 | 含义 | 修法 |
|---|---|---|
| `UNCOVERED_BEAT:<beat>` | 剧本 beat 没有镜头覆盖 | 补镜，或回剧本删掉这个 beat |
| `UNKNOWN_BEAT` / `SHOT_UNREFERENCED` | 镜头引用了不存在的 beat，或没写 `script_ref.source_beats` | 修 `script_ref` |
| `MISSING_LINE` | 剧本台词没在任何镜头出现 | 放回覆盖该 beat 的镜头 |
| `EXTRA_LINE` | 镜头台词在剧本里找不到：被改写或自创 | 换回剧本原句；确要改词就先改剧本 |
| `LINE_BEAT_MISMATCH` | 台词放进了不覆盖其 beat 的镜头 | 移到正确镜头，或补 `source_beats` |
| `SPEAKER_MISMATCH` | 说话者与剧本不符 | 修说话者名，再核 `characters[].name` |
| `ORDER_MISMATCH` | 按剪辑顺序，台词先后颠倒 | 调镜头顺序或镜内台词顺序 |
| `UNATTRIBUTED_LINE` | 镜头台词没写说话者 | 按 `说话者（语气）：台词` 补全 |
| `SCRIPT_NO_BEAT_IDS` / `DUPLICATE_BEAT_ID` | 剧本没编号或编号重复 | 回第 1 步 |
| `DUPLICATE_LINE`（warning） | 多机位 coverage 重复同一句 | 允许；剪辑只留一条 |

对账只证明规格与剧本一致。生成后是否真说对、说话者口型是否对上，仍按 [production-qc.md](production-qc.md) 看真实回放。

## 物性不变量

不得随时间改变的物性写死在三处，不新增 NBP 根键：

| 写哪里 | 写什么 |
|---|---|
| `characters[].state` | 本镜物性的当前值：`风衣下摆带深色雨水痕，非破损污迹`、`风衣浅卡其色` |
| `negative` | 该物性的错误变体：`darkened entire trench coat`、`stain spreading to collar` |
| `continuity.in_state` / `out_state` | 同一物性在本镜起止各复述一次，两端取值相同才算不变量 |

不写容易发生的漂移：长镜后半段外套底色逐渐变暗变色、水痕向领口蔓延改变场景语义。道具归属同理：`@prop_brass_key_v02 由右手握持` 只写在 `characters[].state` 一处，其余字段引用不重述。

判定是不是物性不变量：它在本镜里如果变了，故事性质就变了。是，就三处都写；不是，就只写 `action`，不要为格式填满。

## 密度分流

NBP 简化 JSON 始终作为语义真源，最终表达按模型当前行为分流：

### 高密结构化

当镜头包含多角色站位、分秒动作、硬切、精确轴线、复杂道具或目标模型经 live 文档/实测证明偏好结构化输入时，保留字段边界，并展开时间、空间、物理和连续性锁。

### 极简散文

当镜头语义简单，且目标模型经 live 文档/实测证明长标签会造成注意力争抢时，把 JSON 压成能完整保留当前主体、动作、场景、摄影、光线、运动及必要连续性/音频职责的最短充分自然电影散文。句数和分段由真实语义密度与目标模型行为决定；不得为了“简洁”删除身份、道具状态或物理因果。

### 未知目标

不猜模型偏好：交付简化 JSON，给 `TODO_VERIFY_LIVE: prompt density and reference syntax`，待 live schema/最小 A/B 测试后再序列化。

密度偏好会变化。**模型偏好快照 2026-08-24，生成前 live 校验；默认 14 天过期**：当时研究将 Seedance/Kling 类归为偏高密，将 Sora/Flux 类归为偏极简；版本、入口或行为变化时以 [model-adaptation.md](model-adaptation.md) 的当前核验记录为准。

## 高密模式的两套参考

以下只在高密模式按风险取用，不是默认模板，更不能强迫单镜头填满。

### 十大模块参考

1. 镜头类型与画幅意图；
2. 主体身份与资产绑定；
3. 服饰与道具；
4. 环境与空间纵深；
5. 实体光源与光比；
6. 光学焦段/FOV 与景深；
7. 摄影机物理运动；
8. 动作与物理演变；
9. 时序与音画对位；
10. 正向物理及连续性锁。

### 14 字段分镜参考

`scene_id`、`shot_id`、`timecode`、`aspect_ratio`、`lens_fov`、`camera_rig_movement`、`subject_block`、`wardrobe_props`、`environment_depth`、`lighting_shutter`、`primary_action`、`secondary_environmental_motion`、`diegetic_audio_cue`、`continuity_locks`。

这 14 字段属于 production metadata/高密镜头规范；编译到默认 JSON 时合并到语义对应字段，不新增 14 个空键。例如 `subject_block + wardrobe_props` 合入 `subject`，`lens_fov + camera_rig_movement` 合入 `camera`，两类动作合入 `action/motion`。

## 生图与生视频差异

### 生图

- 资产图关闭无关摄影行为；背景与光线按目标模型、主体分离度、抠图需求和下游代表镜测试选择中性灰、白、透明或其他干净底板，不固定某一灰度；
- 场景关键帧可以使用 `camera/light/style`，但动作写成可见定态；
- 不输出无意义的 `duration/audio/motion`；
- 身份/服装依赖与最小充分视图见 [keyframe-assets.md](keyframe-assets.md)。

### 生视频

- `action` 写因果链，`motion` 写主体/镜头/环境路径与余势；
- `duration` 是创意目标，不是模型永久能力；提交前按 live schema 验证；
- `continuity_ref` 指向批准的身份、状态、地点和 relay frame；
- `audio` 明确原生生成、唯一参考音轨或后期职责，不能含混叠加。

## 编译增量：唯一归属、全局常量与镜头差量

- 可验收的品牌名、品类名或宣传语列为具体内容清单；精准字形仍交确定性后期，不用抽象形容词冒充检查项。
- 单镜需要分段时只写起势、过渡、收尾的职责与顺序，时间由真实动作和目标时长分配，不套固定秒表。
- 换角度先写空间不变量，再写相机位置/朝向/机高的变化；两段不混写。
- 正式镜头沿用同一语义骨架，按风险展开；不新增另一套固定块数。提示词密度由机位数与参考已承载的信息决定，不按模板字数。
- 跨镜常量只声明一次；重复特效或动作先固定触发、传播和速度机制，每轮只改一个变量。
- 只有 live schema 中真正构成硬控制的变量才移入控件；正文不再重复。序列按「全局约束 → 逐镜差量」编译，并用正向名额列出角色及出场关系。
- 圣经引语必须可原样粘入目标字段。有强参考时文字只补构图、动作与参考未承载的信息；正典锁定图无参考可依时才保留高描述密度。
- 一项事实只有一个归属。被反复漏掉且影响验收的要素可提升为靠前的 `CRITICAL` 块，但数量按当前风险决定，不固化上限，也不跨块重复。

## 输出检查

- JSON 是否能被标准解析器读取？
- 在 v1 或 adapter 最终序列化阶段，是否只有允许字段，且没有 `null`、空串或空数组？
- 每个 `@` 标签是否格式合法、登记在 `continuity_ref`，并通过 registry 唯一解析到当前 approved 资产？
- 同一事实是否只占一个主要字段？
- negative 是否已优先正向化，并按实际残余风险与当前 provider live 能力只留下 0..N 个高风险项？
- 密度选择是否有目标模型的 live 依据；未知项是否标 `TODO_VERIFY_LIVE`？
- 时长、参考数量、分辨率等易变参数是否标快照日期并在提交前 live 校验？
- 对白字符串是否不含 `@`，语气提示是否只在括号内且可听见？
- 每个说话者是否对应一个 `characters[].name`，`beats[].say` 是否逐字同序等于 `audio.dialogue[]`？
- 多镜时 `check_script_coverage.py` 是否退出码 `0`？
