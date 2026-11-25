# 模型方言与运行时适配

本文件把 [prompt-compiler.md](prompt-compiler.md) 的语义字段翻译为目标模型更容易遵循的表达。它不是 API schema，也不授权静默换模型；真实提交仍按 [provider-execution.md](provider-execution.md) 的 live schema 执行。

## 运行时门

本文件的方法层稳定，模型版本、时长、参考数、分辨率、价格、入口、音频与口型能力只按下表的**逐行证据收据**使用。每条收据分别记录 `captured_at / source_class / provider / model / account_or_endpoint_scope / observed_result / expires_at`；过期或缺字段即 `TODO_VERIFY_LIVE`，不能用一个全局日期替所有 endpoint 续期。

生成前必须从官方模型卡与实际 provider schema 核对：

```text
exact_model_id / availability / duration_enum / aspect_ratio_enum
resolution_enum / reference_types_and_limits / audio_input
generated_audio / lipsync / extension / price_or_credits
```

未核到的字段保留通用语义，并原样写 `TODO_VERIFY_LIVE: <field>`。禁止从相近版本、聚合平台营销页或 Prompt 文本反推能力。

## 2026-11-24 能力矩阵刷新（v7）

机器可读的单一事实源是 `references/model-capability-matrix.json`（逐条带 `captured_at: "2026-11-24"`、来源 URL 与来源等级，整表由顶层 `"expires_at": "2026-12-08"` 统一控期：`target_compiler.py` 编译时动态校验到期状态并写入 `capability_receipt_hash`，`python3 scripts/check_capability_expiry.py --include-matrix` 可将矩阵一并纳入到期门禁）。下表只是人读摘要，不再重复维护独立的未扫描到期字段；两者冲突以 JSON 为准，JSON 与 live schema 冲突以 live schema 为准，到期后只能触发复核，不能自动续期。来源：零成本只读 CLI 探测（`higgsfield model get`、`pippit-tool-cli model describe`）、本机 `ffprobe` 实测与当日官方文档。

| 模型 / 通道 | 采集日 | 已核事实（只在所列通道内成立） | 必记坑 |
|---|---|---|---|
| Seedance 2.5（方舟 `doubao-seedance-2-5-260628`） | `2026-11-24` | 原生 480p / 720p / 1080p；方舟 `duration` 4–30 整数秒或 -1（离线 `planning` 收据限 4–15s）；参考上限 30 图 + 10 视频 + 10 音频（视频、音频各累计 ≤30s）；响应整数秒时间戳 | 编辑要 `duration=-1` 与 `ratio=adaptive`；输入图分辨率高于输出会出指纹纹理；未认证真人脸需 `asset://` 主体库 |
| Seedance 2.0（方舟 `doubao-seedance-2-0-260128` / Higgsfield `seedance_2_0`） | `2026-11-24` | 只响应镜头序号（`Shot N`），不响应秒级时间戳；Higgsfield 通道 ≤9 图、≤3 视频、≤3 音频、总计 ≤12，4–15s | 与 2.5 的上限和语法不可互推；`fast` 模式不出 1080p |
| Seedance 2.5 @ Higgsfield / 小云雀 | `2026-11-24` | 两通道 `resolution` 枚举含 `4k`，但记为平台档，与方舟原生输出分栏；Higgsfield 支持 `draft` 480p → `draft_job_id` 升级；小云雀 `Seedance_2.5_draft` 凭 `draft_task_id` 7 天内升 1080p | 小云雀 `ret=12004` 审核失败时退出码可能仍为 0；`ARRI`、`Cooke`、`Kodak` 等品牌词触发版权拒绝 |
| Google Flow · Nano Banana 2.1 | `2026-11-24` | `1k/2k/4k`；含 mask 最多 14 张图；适合两步法先锁静帧构图 | 静帧阶段就锁可见肢体位置，视频阶段不驱动被遮挡肢体 |
| Google Flow · Veo 3.1 / 3.1 Lite | `2026-11-24` | 离散时长档 `4`、`6`、`8` 秒；画幅 `16:9`／`9:16`；参考图上限 3 张；原生音频 | `veo3_1_lite` 同时给首尾帧时强制 8 秒 |
| Google Flow · Gemini Omni Flash 1.2 | `2026-11-24` | 3–15s；文生／图生／参考生／编辑／延长五种模式；Flow 网页 360p（640x360）试拍后可升 `720p Upscaled`（1280x720） | Higgsfield 通道参考／首尾帧／延长模式 ≤10s，参考生与首尾帧互斥；Flow 敏感词误杀与 reCAPTCHA 拦截——遇人机验证即停并报告 |
| Kling 4.0 / 4.0 Flash（经 Higgsfield） | `2026-11-24` | 画幅含 `21:9`／`auto`；`kling4_0` 的 `dynamic_range` 可选 HDR；最多 10 张图（含首尾帧），图 + 视频 + Element 总计 ≤15 | HDR 只允许 1080p／4k；文生视频禁 `auto` 与参考；4.0 Flash 锁 720p 且图生只收单首帧；准确时长上限 `TODO_VERIFY_LIVE` |
| Grok Imagine Video 1.5 / 1.5 Lite / Web | `2026-11-24` | xAI 官方 1–15s、480p／720p／1080p（默认 `Image 1` 槽位）；兼容代理网关 `route=openai_compat` 用 `<IMAGE_0>` 起算（实测上限 7 张、原生 1280x720）；1.5 Lite 只收首帧，1080p 为放大 | Higgsfield 通道带参考时禁 1080p；浏览器网页通道可能静默返回 736x400 或 672x448 并夹带 `mjpeg` 封面流——分别记 `requested`、`reported`、`measured` 三列，网页下载尺寸不反推底层模型能力 |
| 小云雀（XYQ / Pippit CLI） | `2026-11-24` | 当日视频目录 9 个模型（含 Seedance 2.5 / flash / draft 与 2.0 系列），图像目录 11 个 | 模型目录动态变化（当日已无 MiniMax-H3），提交前 `model list` 现查；图像比例传数字枚举 |
| Lovart | `2026-11-24` | Seedance 2.5 可经 Agent 调用；无草稿档、无余额查询 | 常回 `generation_succeeded: false` 并反问是否继续；`--prefer-models` 非硬锁，核回执 `reported_tool`；单次可能吐多个 MP4 |
| ElevenLabs（音频主通道；网页 Seedance 2.5 代理） | `2026-11-24` | TTS Eleven v4 / v4 Turbo / Flash v2.5；音效 SFX v3（0.1–30s）；网页集成 Seedance 2.5 时 480p 与 720p 分档计价，720p 每秒积分约为 480p 的两倍多，且无草稿升级 | 480p 与 720p 的价格、上限不可混套；网页提交受 hCaptcha 门控，不绕过；只建议作配音／音效／配乐主通道，不作视频主力 |
| OpenAI Sora | `2026-11-24` | 当日 Higgsfield 视频目录已无 Sora | 不作默认路由；任何继任入口重新核 exact schema |

能力数字只在本表所列通道、所列日期成立；写进镜头规格时仍按「不得把模型能力上限写成默认值」处理，时长与分辨率由创作需要定，再由编译器对照矩阵 fail-closed。

## Mode compatibility preflight

Every real submission records the executable input contract, not a wish list:

```text
exact_model_id
primary_input_mode
allowed_secondary_inputs
incompatible_modes
live_evidence: captured_at / source_class / account_or_endpoint_scope / expires_at
```

Choose exactly one `primary_input_mode` for the job. Candidate modes include text-to-video, start-frame, first/end-frame, reference-led generation, source-plate edit, extend, and `whitemodel_reference`（白模只交空间/姿态/机位，外观由另一路图片参考承担；见 [whitemodel-previs.md](whitemodel-previs.md)）。Whether audio or another reference is primary or secondary belongs to the exact provider schema. Secondary inputs are allowed only when the current schema explicitly accepts them with that primary mode.

This does **not** declare all media types globally exclusive. It prevents a Prompt from pretending that two endpoint modes are compatible. If compatibility is unknown, write `TODO_VERIFY_LIVE: mode_compatibility` and stop before submission or use a documented two-stage/fallback path.

`block_mode` remains a directing/assembly decision defined in [cinematic-method-playbook.md](cinematic-method-playbook.md#adaptive-generation-block-routing). Provider mode is the executable input contract. The two inform each other but are not interchangeable.

## 密度分流

| 目标 | 默认密度 | 编译判断 |
|---|---|---|
| Seedance | 高密结构化 | 资产绑定、空间、镜头、动作因果、时序、音频与连续性分槽；多镜头才写显式 cut。 |
| Veo | 中密叙事 | 一条 clip 聚焦一个英雄动作或对白；用自然句写可见表演、机位和声音，参考图已经定义的外观不复述。 |
| Kling | 中高密结构化 | 先绑定人物/Elements 与说话者，再写镜头节拍、首尾状态和动作物理；多镜头才分段。 |
| Runway | 中低密单镜头 | I2V 只写运动变化、摄影机路径、环境响应与末态；避免把静态画面重新描述一遍。 |
| Higgsfield | 继承底层模型 | Higgsfield 是工作台，不是统一视频基座；密度与方言跟随实际 Seedance/Veo/Kling/WAN 等 model ID。 |
| Grok Imagine | 中密叙事 | 兼容代理网关 `route=openai_compat` 参考图用 `<IMAGE_0>` 起算占位绑定（默认通道用 `Image 1`）；一条写一个主动作，交付前按实测尺寸判断是否原生。 |
| Sora | 极简散文 | 使用少量自然语言电影句，保留主体、行动、空间、摄影机和关键声音；避免标签争抢。 |

密度是注意力分配，不是字数竞赛。只有镜头确实需要时才启用时码、参考槽或多镜头结构。

## 能力快照

> 表格只提供 preflight 线索，不是提交依据；价格不缓存。`expires_at` 是本 Skill 的复核门，不代表厂商承诺有效期。真正提交仍读取 exact endpoint 的 live schema。

| provider / model | `captured_at` / `source_class` / `account_or_endpoint_scope` | `observed_result` | `expires_at` 与运行时动作 |
|---|---|---|---|
| Volcengine / Seedance 2.5 | `captured_at=2026-09-19` / `source_class=official` / `account_or_endpoint_scope=公开文档（方舟 Seedance 2.5 教程页 2026-09-11 版、提示词指南 2026-09-18 版）；非当前账户 live schema 或登录态控制台` | 2026-09-19 复读 https://docs.volcengine.com/docs/ark/seedance-2-5?lang=zh （页面更新 2026-09-11）：模型 ID `doubao-seedance-2-5-260628`；输出分辨率 480p / 720p / 1080p、默认 720p、枚举不含 `4k`；`duration` 为 4–30 整数秒或 -1、默认 -1；参考素材上限 30 图 + 10 视频 + 10 音频（视频、音频各累计 ≤30s）；视频编辑与延长要求 `ratio=adaptive`（编辑另要 `duration=-1`），首帧/首尾帧同样 `adaptive`；不支持直接上传含真人人脸的参考图/视频。与当前能力矩阵 Seedance 条目一致；即梦产品侧延长链与方舟 API 仍分层，2.0 与 2.5 规则仍不可互推 | `expires_at=2026-10-03` 【已过期 → TODO_VERIFY_LIVE】；提交前读目标 endpoint 的 live schema / receipts，未核即 `TODO_VERIFY_LIVE: exact_model_capabilities`。 |
| Gemini API / Veo 3.1 | `2026-09-01` / official developer documentation / Gemini API Veo 页面 | 当前已读正文只确认 `8s`、原生音频、延长、首尾帧、最多 `3` 张参考图 | `expires_at=2026-09-15` 【已过期 → TODO_VERIFY_LIVE】；`4/6s`、分辨率与 Fast/Vertex 变体不从相邻 endpoint 推断。 |
| Kling first-party guide / VIDEO 3.0 | `2026-09-01` / first-party product guide / 指定 guide，非通用 API schema | `3–15s`、Native Audio、Start/End Frames、Multi-Shot 开关；关闭时为单镜头 | `expires_at=2026-09-15` 【已过期 → TODO_VERIFY_LIVE】；Elements、参考视频/声音、说话者、分辨率与账号 UI 仍查 live schema。 |
| Runway / exact model pending | `2026-08-24` / historical snapshot, source scope incomplete / 未锁 endpoint | 旧记录不足以提升当前时长、分辨率或原生对白枚举 | `expires_at=2026-09-07` 【已过期 → TODO_VERIFY_LIVE】；全部能力重新核。 |
| Higgsfield / selected base model | `2026-08-24` / historical workspace snapshot / 账号与底层模型未锁 | 工作台能力与底层模型能力必须分栏；旧 Soul ID 数量不提升为当前合同 | `expires_at=2026-09-07` 【已过期 → TODO_VERIFY_LIVE】；先发现底层 model ID、media flags、权限与价格。 |
| OpenAI / Sora product or successor | `2026-09-01` / first-party product page / 消费端产品状态，不等于 API schema | 页面记录 Sora 消费端产品已于 `2026-04-26` 停止；公开页面未确认 API 时长、分辨率或停用日 | `expires_at=2026-09-15` 【已过期 → TODO_VERIFY_LIVE】；不作默认依赖，任何 API/继任模型都重新核 exact schema。 |

若 live schema 与某行冲突，以 live schema 为准，在 generation log 记录 endpoint、时间与差异；过期行只能触发复核，不能自动续期。

## Seedance 2.5 分辨率：未提升的历史线索

- 官方公开文档未见 ByteDance 对 Seedance 2.5 原生 4K 的承诺。
- 2026-08 的若干第三方 endpoint 曾暴露不同分辨率枚举；它们只能证明当时通道不同，不能证明 ByteDance 官方叙事与 API 存在普适冲突，也不能代表当前账号。
- 2.0 的 1080p/4K 记录不得迁移到 2.5；促销中的分辨率档也不能脱离 exact model/schema 自动提升为能力。

执行结论只有一条：生成前读取当前通道的 `resolution` 枚举；未核即 `TODO_VERIFY_LIVE: resolution_enum`，模型原生输出与后期超分交付必须分开报告。

## 适配器入口

[`render_nbp_adapter.py`](../scripts/render_nbp_adapter.py) 接收 NBP v2（经 `--schema auto` 也接收图像或视频 Simplified JSON，先规范化为 v2 IR），支持 `seedance_2_5`、`seedance_2_0`、`google_flow`、`higgsfield`、`kling`、`grok_imagine`、`xyq`、`lovart` 八个标准 `--target`（另保留 `seedance`、`elevenlabs` 两个兼容别名），逐目标规则见 [prompt-compiler.md](prompt-compiler.md) 的编译链。它只生成交接结果，不提交 provider 任务；Higgsfield `media_roles` 中的 canonical `@Tag` 提交前须按 registry 解析，适配器不做解析。

- 三目标共享 NBP v2 validator 与可选 canonical registry，不复制校验规则。
- 三目标的可复制提示词逐条保留显式 `references[].role/use`，并绑定当前本地参考编号；身份、动作或声音转移边界不能只藏在 JSON 中。编号仍须在执行 adapter 中按真实上传结果核对。
- capabilities 只读取 `claims[]` 中带 `key` 的条目；同 key 默认按 `xyq→cli`、`seedance→model`、`higgsfield→platform 后 model` 选 scope，exact model 仍由收据标识。
- 先核证据再选 scope：显式未验证、已过期、来源时间异常或 provider / model 冲突的 claim 不参与参数决定；同 key / scope 的冲突值不能静默取第一条。缺完整来源的旧收据只用于带 warning 的离线规划限制，不用于强制改写参数。
- 编辑/延长的参数规则必须绑定 claim 级 exact model、当前 `task_modes` 和有效来源 / 时间 / endpoint 元数据；型号名字含某个版本号不再构成证据。缺依据时保留请求意图并输出 `TASK_MODE_CLAIM_UNVERIFIED`，执行前核实。
- 缺 claim 报 `CAP_MISSING` warning 并可继续；`CAP_EXCEEDED` 进入 `errors[]`、返回 rc 1，不猜值、不截断、不静默换模型。
- `task_mode` 由 validator 先做互斥校验；适配器不从 `use` 子串猜首帧或尾帧，帧模式只交付帧引用。
- 首尾帧从 registry 中的尺寸 / 比例检查画幅：不一致报 `FRAME_ASPECT_RATIO_MISMATCH`，缺信息报 `FRAME_GEOMETRY_UNVERIFIED`，元数据矛盾报 `FRAME_GEOMETRY_CONFLICT`；不自动裁切、拉伸或猜尺寸。提交前核实实际文件并修正，不能依赖平台自动处理。
- XYQ 的参数与首尾帧交接细则见 [adapter-xyq.md](adapter-xyq.md)。

所有 adapter 编译结果均标记 `validation_scope=planning_only`、`provider_ready=false`、`live_submission_checked=false`；通过编译只证明可以继续核验，不证明当前账户可生成。机器检查证据元数据不能代替读原始来源，更不能替代 live schema、任务终态或像素验收。

## 方言编译

### Seedance

- 保留 NBP JSON 的结构语义，编译为清楚的模块顺序；高复杂镜头才展开时序与 hard cut。
- 把 `continuity_ref` 映射为当前入口真实支持的图片/视频/音频槽；`@图片N` 只在当前 UI 仍支持时使用。
- 先锁当前镜头真正需要的人物、场景方位、核心动作因果链与末态，再加摄影与声音；相容的多阶段动作可以保留，不用长负面词库稀释主任务。
- 多人物同框先走阵容与独立资产绑定，不能靠反复写姓名防串脸。
- `continuous_block`：保护连续时间、表演、声场和一个有动机的摄影行为；不自动加入 cut、正反打、固定时间戳或第二机位。
- `covered_scene`：只有 coverage 职责与 live multi-shot 同时成立时，才在一次提交中用时码/cut；否则把 master、reaction、eyeline 或 detail 分成独立 jobs，在后期按同一 story time 装配。
- `independent_pickup`：编译为一条可验证任务，隔离对白/口型、反应、接触、特效或局部返修风险。
- `post_insert`：不交生成模型；路由到确定性文字、UI、字幕、法律文案或图层后期。
- Extend 只在 `continuous_time`、真实 QC 末态可用且 live schema 支持时优先；`editorial_cut` 不因 endpoint 有 extend 就被强制续写。
- 单次时长枚举仍以 live schema 为准。2.0 与 2.5 规则不可互推；分辨率写成通道差异（Ark / Atlas / HiAPI），按 exact endpoint 读，未核即 `TODO_VERIFY_LIVE: resolution_enum`。
- 真人脸：消费端常拦截未认证真人参考；受控认证路线用 `asset://` / 主体库，不得以换措辞绕过。提交前按 live schema / receipts 复核，未确认即标 `TODO_VERIFY_LIVE: real_face_reference_policy` 并停止。详见 [face-consistency-execution.md](face-consistency-execution.md)。

#### Seedance 2.0 / 2.5 方言

| 版本 | 时序写法 | 白模 / 多参考 | 备注 |
|---|---|---|---|
| 2.0 | 镜头序号式（镜 1 / 镜 2），不把秒级时间戳当合同 | 旧记录不得套用 2.5 白模参考 | 与 2.5 能力收据不可互推 |
| 2.5 | 整数秒时间戳可用于 `continuous_block` / 已核 multi-shot（提示词指南 2026-09-18 版原句：2.0 不响应时间戳只响应镜头序号，2.5 响应整数秒的时间戳；https://docs.volcengine.com/docs/ark/seedance-2-5-prompt-guide?lang=zh ） | `whitemodel_reference` 为候选 `primary_input_mode`；2.5 可用多视图作主体参考，2.0 不建议（同上指南） | 官方博客 2026-09-15 与提示词指南 2026-09-18 已读；实际账户 schema 仍 `TODO_VERIFY_LIVE` |

2.5 提示词指南（2026-09-18 版，URL 同上表）列出的常见问题对应本 Skill 的失败层，作为 Seedance 方言处理、不写进通用 NBP：角色对应错误 → 按人物首次出场顺序上传参考素材，并同步改 Prompt 里的图片/音频编号；字幕或台词约束不生效 → 按「角色台词（情绪）：内容」拆写，参考视频不带字幕；情绪词引发眼睛发光 → 写「正常人眼、不发光」并改用常规情绪词；画面出现指纹状纹理 → 输入图分辨率不高于输出分辨率；编辑输出偏短约 0.33s → 输入帧数取 8n+1；复杂任务拆成多个简单任务分次提交。

#### 岛式提示词（Seedance 专属）

纯文生视频或逐镜独立提交且没有跨请求记忆时，把每条 Prompt 当成孤岛：站位、姿势、服装、道具、光学与光线从零写全，不写“同上一镜”。已经提供批准首帧时，首帧负责静态事实，Prompt 只写变化；当次入口若支持 multi-shot、extend 或会话上下文，先做代表镜重测再决定是否沿用岛式写法。

### Veo

- 用完整自然句描述可见主体、一次主要行动、摄影机、实体光源与对白/环境声；避免同时塞入多个冲突动作。
- 参考图负责身份和外观，文本负责运动与表演。首尾帧、references、extend 的组合若 schema 未确认，写 `TODO_VERIFY_LIVE`。
- 对白写准确说话者、原句、语气与停顿；原生音频或口型未在本次通道确认时，不承诺同步结果。

### Kling

- 先建立 `canonical_asset_id -> element/speaker` 映射，再写动作、镜头与首尾状态。
- 对话场用明确的说话者归属；多镜头用短节拍分段，不让每段重复整套人物描述。
- 首尾帧只描述可物理连接的状态；分辨率、Elements 上限、参考视频/声音范围均以 live schema 为准。

### Runway

- T2V 写一个场景与一条主运动；I2V 把输入图当第一个事实，只描述如何变化。
- 运镜、主体运动与环境响应分清，末尾给稳定可剪辑状态。
- 没有 live 证据时，不把对白、口型或跨镜身份锁写成原生能力：`TODO_VERIFY_LIVE: generated_audio/lipsync/identity_reference`。

### Higgsfield

- 先选实际底层模型，再套对应方言；不要产出“Higgsfield 通用 Prompt”后假定各模型等价。
- 用当前 media flags 把 character、location、motion、audio、first/end frame 分配到真实槽位。
- Soul ID、Elements、Cinema Studio 是工作台能力；模型原生能力与平台后处理能力在记录中分栏。
- `4K` 只记为平台放大/后处理，不记为底层模型原生输出；提交前 `TODO_VERIFY_LIVE: upscale_path`。
- Cinema Studio 的参考能力随版本变化，不硬编码数量；提交前读取当次 live schema / receipts。
- Soul ID 的跨模型可达性只按当次 model get schema 判断，不从博客互推；适配器只发 warning，不代替平台下结论。
- 站内模型不可用或额度不足时，不静默换底层模型。

### Sora

- 仅在 live preflight 证明入口仍可用时编译；否则返回不可执行并标继任模型待查。
- 用少量自然语言句写视觉因果，不展开 Seedance 式字段标签；资产/character 只使用 schema 真正支持的绑定方式。
- 停用时间、时长、分辨率、character 限制均执行本文件快照门，不能作为长期事实。

## 不确定性与 fallback

```text
TODO_VERIFY_LIVE: exact_model_id
TODO_VERIFY_LIVE: duration_enum
TODO_VERIFY_LIVE: resolution_enum
TODO_VERIFY_LIVE: reference_types_and_limits
TODO_VERIFY_LIVE: generated_audio/lipsync
TODO_VERIFY_LIVE: price_or_credits
```

Fallback 同样必须写明替代后的 `primary_input_mode` 与失去/保留的决定性约束，不能只写“换模型”。

无法 live 校验时仍可交付 provider-neutral Prompt Contract，但必须标“不可直接提交”。fallback 需记录原模型、失败类型、是否已创建任务、替代模型及质量/成本差异；不得声称原模型成功。

## 编译后检查

- [ ] 语义合同没有因方言翻译而改变故事、资产或镜头意图；
- [ ] 每个真实提交只有一个 `primary_input_mode`，secondary/incompatible 有当前证据；
- [ ] 密度符合目标模型，没有无用槽位与标签争抢；
- [ ] 引用语法来自本次 provider，不是另一平台的记忆；
- [ ] 所有易变字段已 live 核验或带 `TODO_VERIFY_LIVE`；
- [ ] Seedance 2.5 没有默认写成原生 4K；
- [ ] Higgsfield 已写明底层 model ID；
- [ ] Sora 当前状态已核对，未被默认路由；
- [ ] 原生规格与后期交付规格分开记录。

## 证据边界

模型事实按本文件逐行收据分层：官方 API/开发文档高于第一方产品叙事，后者高于第三方 endpoint 历史线索；搜索摘要不入表，live exact schema 始终优先。

## 写作宿主观察

> 写作阶段使用何种宿主模型由用户自主选择，不预设单一宿主偏好；如接手外部已定稿剧本，直接按 [cross-host-handoff.md](cross-host-handoff.md) 作为锁定输入推进。
