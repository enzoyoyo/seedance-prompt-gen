---
name: seedance-prompt-gen
description: Use when creating or revising AI short dramas or AI-generated narrative videos in any genre or form, including open creative direction and original comedy mechanisms, cinema or short-drama modes, story-state and character-canon ledgers across scenes, minimum-sufficient planning with spatial blocking and 3D/whitemodel previz decisions, reference-image role allocation, observable performance and action physics in shot prompts, generation-block planning with hardest-shot-first tests, live verification of the current model's duration, input modes, native audio, pricing and permissions before real submission, multi-pass take QC with in/out selects and continuity bridges for generated clips, platform packaging when needed, final edits, and publishing with AI disclosure. Not for generic edits of existing live-action footage, API-only SDK integration code, or standalone transcription.
metadata:
  version: 7.0.1
  author: Enzo
  homepage: https://blog.enzocreative.me
  hermes:
    tags: [ai-video, seedance, short-drama, viral, prompt, storyboard, continuity, social-publish, production]
    related_skills: [lovart-api, atlas-cloud, higgsfield-generate, xyq-skill, xyq-short-drama-skill, hyperframes, precision-video-editing, videoedit, video-shotcraft]
---

# Seedance Prompt Gen — 专为 AI 短剧与叙事短片而生的创作与制作 Skill

## 一句话使命

**专为 AI 短剧与叙事短片而生：自主匹配最适合题材的叙事形式，把想法打磨成有张力、低 AI 味的剧本，并一步步落成可控分镜、一致角色资产与可发布成片。**

不强制走完整管线；从用户所在环节进入，只回补该环节的前置产物。 **Blender 软件分支：仅当用户明确要求调用 Blender 制作或预演时，才加载 `references/blender-previs.md`；未要求 Blender 的任务不启动本地 `.blend` 脚本。**

## v7 入口：交付模式 × 创作模式 × 继承式选择

| 维度 | 取值 | 决定什么 |
|---|---|---|
| 交付模式 `delivery_mode` | `prompt_only` 提示词包／`images_only` 静帧资产／`video_clips` 逐镜验收 take／`full_film` 带声音字幕的成片 | 门序终点；`python3 scripts/list_execution_providers.py --delivery-mode <mode> --json` 列该档通道与五级发现态 |
| 创作模式 `creative_mode` | `cinema` 留白、动机运镜、ASL 5–10s／`short_drama` `OPEN ON ACTION`、权力翻面、ASL 2.5–5s、speaker→listener | 五维心法与执行见 `references/cinema-vs-short-drama.md`；与画幅、时长正交，`film` 归一为 `cinema`；未说明时推断并在 `### 默认假设` 标「可改」 |

继承式选择：已有项目先跑只读 `drama_next.py <目录> --v7 --json`（新建 v7 尤其 `prompt_only` 传 `drama_setup.py init --project <目录> --sop-version 3.0` 消歧）；到决策节点跑 `python3 scripts/model_gate.py resolve --user-words "<原话>" --project <目录> --json`（仅写 `choice_resolution` 暂存，不代签 Human Gate #1），按本轮原话 > 项目已锁 > 本会话继承，缺项弹选择器 JSON 或编号 `1..N` 后 **STOP & WAIT**；编号回复带 `--request-id <id> --revision <n>` 回传 `resolve` 并经 `drama_setup.py model-gate` 落锁。想法、方向、剧本、文案不弹菜单：只要剧本就停在文本。`sop_version: "2.0"` 走 `model_gate.py render`。

**AI 短剧项目执行总闸门（弱模型必遵，严禁跳步）**：凡给定短剧项目目录、把现成剧本拍成镜头／成片或跑提交（含 `--dry-run`），**第一条命令必须先运行** `python3 <Skill根目录>/scripts/drama_next.py <项目目录>`（v7 加 `--v7 --json`），只执行其唯一当前动作，每步后重跑（`references/drama-gates.md`）。接手旧素材先只读 `python3 scripts/audit_takeover.py reconcile --project <目录> --json`（`matched/orphan/ambiguous/missing`），确认后 `--apply`，关联视频加 `--choose SHOT=FILE`。禁自建目录代 `resume-manifest.json`，禁绕过 `scripts/ledger_submit.py` 直调适配器。需用户拍板未定即停：① `script_lock`（现成剧本**一字不改**，只补 `[S1-B1]`）；② `release_intent`（`templates/release-intent.json`）；③ `previs`（`scripts/render_whitemodel_board.py` 出 `00_previs/` 候选）；④ `identity`（按 `required_views` 备角色角度与主景板）。`previs`／`identity` 先跑 `drama_setup.py present --project <目录> --gate previs|identity [--candidate GROUP/LABEL=path]` 出带码决策图并**立即停止**（禁读码／代填，回复含码才落锁，`--waive*` 同须带码）；重选走 `drama_setup.py impact`。单镜或纯文本不强建预演。

| 入口 | 触发词 | 必读模块 | 可跳过环节 |
|---|---|---|---|
| 选题与核心冲突 | 选题、题材、想拍什么、有没有想法、核心冲突、微综艺、AI综艺、规则真人秀 | `references/open-creative-director.md`、`references/dramatic-tension-engine.md` | 分集、资产、分镜、Prompt |
| 脑暴选题（热点雷达） | 脑暴、脑暴选题、想不到选题、不知道拍什么、没想法、结合热点、最近什么火、当下热点、社会舆论 | `references/brainstorm-topic-radar.md`、`references/live-trend-intelligence.md`，雷达后回 `references/open-creative-director.md` | 分集、资产、分镜、Prompt；用户已给方向且未说脑暴/热点时不触发，走默认路径 |
| 故事·大纲·连续分集 | 故事、剧本、大纲、第 N 集、分集、连载、续写 | `references/episodes-serial.md`；会话中断或恢复时加 `references/sequence-resume.md` | 题材已定则跳过选题；只要文本时跳过资产、分镜与 Prompt |
| 电影 vs 短剧调性 | 电影感、短剧感、慢节奏、留白、快切、爽点、一镜到底 | `references/cinema-vs-short-drama.md` | 不重做已批准剧本 |
| 角色 Bible 与世界观 | 角色 Bible、人物小传、世界观、设定集、连续性 | `references/continuity-bibles.md`、`references/keyframe-assets.md` | 已批准故事视为输入；未要求镜头时跳过分镜、Prompt 与生成 |
| 分镜与镜头清单 | 分镜、shot list、镜头清单、机位、coverage | `references/continuity-storyboard.md`、`references/storyboard-camera-direction.md`、`references/single-scene-direction.md` | 已批准剧本与资产不重做；跳过分集与发布，未要求生成时停在 shot list |
| 生图生视频提示词 | 生图提示词、生视频提示词、Prompt、Seedance、Higgsfield、小云雀、首尾帧 | `references/prompt-compiler.md`、`references/model-adaptation.md`、`references/adapter-xyq.md` | 已有合格上游规格则跳过剧本与分集；未授权时跳过真实提交 |
| 失败诊断与修复 | 不对、失败、崩坏、漂移、穿帮、没人看、为什么、诊断、修复、重测 | `references/failure-diagnosis.md`，再按症状回读对应模块 | 跳过全部无关前置环节，只修最早失败层并重测 |
| 成片·剪辑·发布 | 成片、剪辑、导出、发布、合成、放一个文件夹、项目目录推进 | 先跑 `scripts/drama_next.py <项目目录>`，读 `references/drama-gates.md`、`references/post-production.md`、`references/production-qc.md`、`references/platform-packaging.md` | 已批准素材与镜头不重做；只要母版时跳过多平台分轨 |
| 白模站位与 3D 预演 | 生成前站位预演、白模、片场、本地导演台、3D Jutsu，或点名 Blender／建模 | `references/whitemodel-previs.md`、`references/previs-path.md`；片场加 `references/stage-desk-previs.md`；点名 Blender 加 `references/blender-previs.md` | 默认每场先出 `00_previs/` 候选经 `present` 带码选定；口语「片场」不触发；小云雀导演台走 `references/adapter-xyq.md` |

多入口命中时：shot list 先于逐镜 JSON，分镜表先于适配器 prompt。

生图生视频提示词输出契约：只有用户明确要可复制提示词或镜头规格包时，首条回复先给一个 ```` ```json ```` 扁平 **Simplified JSON**（见「用户面模板」），键取 `mode`（`cinema|short_drama`）/`subject`/`action`/`scene`/`camera`/`light`/`style`/`motion`/`duration`/`aspect_ratio`/`audio`（`{dialogue,ambience,music,sfx}` 或分段串）/`refs`（有序 `[{ref,role,use}]`，编译为内部 `references[]`，兼容 `{tag:use}` 与 `continuity_ref`）/`negative`，空键省略；图像禁 `motion/duration/audio`；未核时长在 JSON 外注 `TODO_VERIFY_LIVE`；未点名或选定模型时（含 `prompt_only`）只交模型中立 Simplified JSON，点名或选定模型后才编译方言 prompt；一次一镜，多镜逐镜给；不得把模型能力上限（最长秒数、参考图配额、分辨率）写成默认值。点名 NBP v2 才展示 IR。
内部编译链：`python3 scripts/validate_nbp_prompt.py --schema auto --type <image|video> --input <规格>` 把 Simplified JSON 规范化为 NBP v2 IR（`"nbp_version": "2"`，视频根键 `characters/scene/action/camera/aspect_ratio/duration/audio/references`），再由 `python3 scripts/render_nbp_adapter.py --target <seedance_2_5|seedance_2_0|google_flow|higgsfield|kling|grok_imagine|xyq|lovart> --schema auto --type <image|video> --input <规格> --json`（另兼容 `seedance|elevenlabs`）编译为目标方言并给出 `capability_receipt_hash`；做不到即 fail-closed 报错，不静默丢尾帧、原句、参考或音频（`references/prompt-compiler.md`）。
NBP v2 关键 shape：`characters` 有人物时必须填，风景/产品镜允许 `[]`；`audio.dialogue[]` 必须为字符串数组；`references[].role ∈ character|prop|location|style|motion|audio`，且每个 `references[].use` 必须为非空字符串；`characters[].ref` 与 `references[].ref` 同形，均须采用 canonical `@kind_name_vN` 形状（正则 `^@[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9]+(?:_[A-Za-z0-9]+)*_v[0-9]+$`），例如 `@char_mira_v01`、`@location_archive_night_v01`。
可选 `continuity` 块、`task_mode` 枚举、模式一致性、防误译（`无工牌` ≠ `bare-chested`）与防遮挡肢体规则见 `references/prompt-contract.md`。

失败诊断输出固定四段「现象→原因→修复→重测」；「修复」必须点名 NBP v2 字段 `characters/scene/action/camera/aspect_ratio/duration/audio/references/continuity/negative` 或适配器参数名，资产层失败可点名 asset id / view-set，不必硬编 NBP 字段名；「重测」只改一个变量并写明是哪一个。

用户明确写抖音短剧时读 `references/platform-douyin.md`；明确写出海／海外／外语短剧，或点名 ReelShort、DramaBox 等海外短剧 App 时读 `references/platform-overseas.md`；只写 TikTok、竖屏或「短视频」不触发任一平台模块。

## 硬边界

- 上下文隔离原则：创作只使用本次 brief、用户提供的素材、公开参考样本与本 Skill 资料，不混入跨会话无关题材或外部设定。中途加载其他 Skill 后返回须重述当前资产与已准 take。缺工具按 `references/host-capability-fallback.md` 降级，标 `NOT_SUBMITTED` 或 `RESEARCH_SKIPPED`。
- 聚焦影视与短剧创作：只产出短剧创意、可读剧本、可控分镜、资产规格、运动提示词、诊断修复与声画成片，不发散为无关领域的报告。
- 创作用当前模型：核心创意判断由当前会话模型直接完成，不调 agy、Codex 等外部模型代写。获授权时已登录的 Grok、豆包可做趋势搜源、交叉核验与反方质疑，须返回原始 URL 由当前模型复核。脑暴搜源按 `references/brainstorm-topic-radar.md` 交给 `scripts/list_research_tools.py` 探出的本机工具，当前模型核验并定选题。别处写好的剧本是锁定输入：只编号、不改字，见 `references/cross-host-handoff.md`。
- 做 AI 短剧先跑 `python3 scripts/drama_next.py <项目目录>`，按门序（接单→剧本锁→发布意图→`00_previs`→角色与场景资产→镜头规格→试价→草稿→验收→试拼→点头→成片→后期→交付）推进；见 `references/drama-gates.md`、`references/shot-spec.md`。
- SPEC v2.0 七步合流 14 门：Step 1 需求＋错题预筛＋模型门禁 [Human Gate #1] → Step 2–4 角色／场景／白模 [Eval & Loop] → Step 5 定稿 [Human Gate #2，`present` 带码] → Step 6 分镜视频音频 [双阶盲审；单镜≤2轮] → Step 7 终检交付＋错题入库；v7 按 `delivery_mode` 截断终点，全片重渲染上限 `max(1, min(5, floor(0.30*N)))`。安静执行：仅两道 Human Gate 与熔断打断；详见 `references/harness-guardrails-and-eval.md`。
- 付费提交只经 `python3 scripts/ledger_submit.py`（先 `--dry-run`），不直接调通道提交命令；结果未知或余额不足即冻结该通道新提交。
- 真实生成前读 `references/provider-execution.md` 与 live schema/官方规则；任何能力、像素、价格、榜单数字同行带 URL+日期或写 `TODO_VERIFY_LIVE`，禁凭经验值猜测。

## 何时触发与不要使用

触发：写、改、反推 AI 短剧剧本、对白、分镜或镜头 Prompt；Seedance／即梦／Higgsfield／Google Flow／Kling／Grok／Lovart／Atlas／小云雀的图生、文生、首尾帧、参考视频、动作迁移、续写；锁角色连续性、竖屏短剧、微综艺、连载；配音、字幕、剪辑、成片与发布；产品广告、UGC、VFX、Faceless、批量为附属用法。旧触发词 `/seedance`、`seedance-product-video`、`ai-viral-video-lab`、`video-production-orchestrator`、`ai-short-drama-production` 都路由到这里。

不要使用：只剪已有实拍素材、转码、口播气口 → `precision-video-editing`；只给已有素材做动态标题或数据卡 → `videoedit`；只做程序化动画或信息图 → `hyperframes`；只查营销 SEO / 转录 → 对应搜索或转录 Skill；只写 provider API/CLI 集成代码 → 对应 provider adapter。

## 默认推断

- 画幅由用户目标、实际发布面、观看场景与当日平台/Provider 支持共同决定；`9:16`、`16:9` 等只是候选，未指定时按 `### 默认假设` 处理。
- 时长由所选观看体验的最短可读时间决定，不先套模型时长、固定节拍或反转数量。
- 用户只要剧本，就按「剧本接单两态」先问或先诊断，再交可朗读、可拍的剧本（含张力门表与标题候选），不擅自生成分镜、Prompt 或视频。
- 用户要“剧本 + 可生成镜头包”但暂不提交（`prompt_only`），做到资产规格、shot list、首尾帧、运动 Prompt 与 continuity，不触发 provider、付费或发布。要成片或发布（`full_film`），就做到当次目标实际需要的资产、生成、声音、剪辑、导出与所选平台分轨；不停在 Prompt，也不为未选平台建资产。
- 创意模式：用户已给方向、题材或人物时沿该方向深化，不另开方向替换；只有张力门无法沿原方向修时，才按「剧本接单两态」给 2–3 个明显不同方向并说明原因。
- 脑暴模式开关：默认不触发；用户说脑暴、想不到选题、不知道拍什么、没想法、结合热点、最近什么火、当下热点、社会舆论时才按 `references/brainstorm-topic-radar.md` 先搜源再产出。
  开放脑暴（无任何创意材料）出 `### 脑暴 pitch`，锚定脑暴（已给方向）只加固该方向走 `## 张力门诊断`；两者都仍停在文本，`### 搜源工具` 全不可用时标 `RESEARCH_SKIPPED` 回落默认接单路径。
- 制作模式：用户提供或已确认的文案、剧本是输入不是草稿。进分镜、Prompt 或生成前回读原文，按 `references/continuity-storyboard.md`「从剧本到镜头的交接核对」逐 beat 对账；人物、场景、动作、对白不因转换而变，必要改动先说明并点名 beat。无 beat 编号按 `references/script-writing-craft.md` 只补编号；多镜头交付前跑 `scripts/check_script_coverage.py`，退出码 0 才算逐句对上。
- “电影感”“高级感”自动翻译为机位、焦段感、动机光、材质、表演和物理反应，不堆形容词；它不自动等于 `cinema` 模式。
- 多镜头只锁会复用、继承或高风险漂移的角色、地点、道具与状态；单镜头只保留必要资产。
- 默认使用简体中文交流；可复制 Prompt 的语言按目标 provider 与用户要求转译，否定与范围原样保留。
- 执行选择门：明确要求生成且点名 provider / model / adapter 就按授权开始（仍 preflight，不静默换模型）；只问模型是否合适时停在评估；要生成没点名，按继承式选择只问缺项，用 `list_execution_providers.py` 列可用 adapter、凭证 present/missing（不回显值）与一条推荐后停下等选；只谈想法不弹。同一作品同一会话选定后不重复弹，换 provider 走交接清单。
- 提交与交付硬门（锁预算、次数金额分账、先草稿后成片、超支重问、禁擅改换端、底图局改、可见附件先发、拒收同步看板）见 `references/provider-execution.md`。

## 自适应生成组织

按观看形式、连续性收益、coverage 职责、失败隔离和确定性后期需求，在 `continuous_block`、`covered_scene`、`independent_pickup`、`post_insert` 中选择；时长上限与 multi-shot/extend 只是 live 能力，不替代导演判断。单机位长镜、多 job coverage 与延长都可以成立，但都要写当前理由。稳定定义见 `references/cinematic-method-playbook.md`。

真实提交先选一个 `primary_input_mode`；其他参考能否作为 secondary input，只服从 exact model 当次 live schema。兼容性与方言见 `references/prompt-contract.md` 和 `references/model-adaptation.md`。

## 开放短剧导演层（创意规则优先级）

短剧概念、剧本或改稿先读 `references/open-creative-director.md`；本节优先级只覆盖创作方法（题材、结构、人设、钩子形式、形式选择）。输出格式、接单问题数与 pitch 数、校验契约、技术、证据、授权、合规与 QC 硬门一律以本 SKILL.md 和校验器为准；`open-creative-director.md` 与本文件冲突时按本文件执行。

- 创意只锁四条底线：最早可读时刻有真实续看理由；人物、情绪或所选形式内部成立；有可命名、可失去的张力并逐单元升级；不把删除、限流、侵权或披露风险伪装成流量技巧。
- 题材、人设、结构、场景数、镜头数、钩子形式、反转频率和结尾形态由 brief 自主决定。形式自由，张力不自由：羞辱、翻盘、固定 60s 节拍是冲突/逆转爽剧的可选手法；想要/阻力/代价/升级/转折/钩子/结尾/标题八行是所有形式的通用验收条件。
- 写剧本或对白正文按 `references/script-writing-craft.md` 的格式（场景行、【承接】、`[S1-B1]` beat 编号、△ 动作行、`角色名（语气）：台词`）；审稿读 `references/human-texture-and-script-gate.md`，按因果、关系变化、悬疑、喜剧、观察、氛围、非线性或视觉转化等实际形态验收。
- 用户要求“最新/2026/流量/平台适配”或方向开放且竞争性强时读 `references/live-trend-intelligence.md`；涉及争议、擦边、引战、真实人物、AIGC 披露或发布时读 `references/platform-risk-and-compliance.md`，并按其中的 repository/planning/publish 三态运行证据门；需要平台事实时再读带日期的 `references/2026-platform-evidence.md`。官方规则、样本与创作推断分开，执行或发布日重核。

资产一致性、参考职责、物理连续性、Prompt 编译、live schema、付费权限、真实末帧、下载解码、声画 QC、平台合规与发布证据仍是硬约束。只要剧本就停在文本；只要单镜头就不强建完整资产圣经。

### 表达审校（剧本、对白、旁白、大纲与标题）

- 先写成立的戏，交付前按 `references/human-texture-and-script-gate.md` 做局部表达审校，标题同时按 `references/title-craft.md` 检查；不新增接单问题或停笔确认。不写装饰性情绪状语、抽象套话和替观众总结的金句；时间、范围、否定、不确定性、方向和先后不能丢，也不写成电报体。对白从这个人对这个人此刻要办的事出发，不靠口癖、断句、停顿装人味。标题取本集具体矛盾，不用换词凑候选。
- 只改表达时保住原意、人物知情、动作强度、伏笔、代价和结局，不擅加动作或事实；不借私人素材，不套作者人设。固定输出标签、JSON 字段、用户原句引用与技术参数不做文风清洗。

## 剧本接单两态（先问再写 / 有想法就优化）

判定：看用户消息里有没有可用创意材料（题材／人物／前提／大纲／剧本任一）；平台、形式、时长、现成想法四项里缺两项以上，即为薄 brief。
薄 brief（无想法）不写完整剧本：一条消息内给 `### 接单问题`，只问不问就无法定方向的阻塞项，最多 2 个；每个问题后附一句「不问就无法定方向」的具体理由。其余信息写进 `### 默认假设`，按默认值继续。
两个固定标题的逐字写法、`### 接单问题` 节的计数规则与「直接写」快捷路径见 `references/script-intake-contract.md`（逐字下沉，与 `scripts/validate_script_gate.py` 同源）。
剧本接单两态的第一条回复里，`### 接单问题` 节必须始终存在，即使 brief 已给全平台／画幅／时长也不得省略；无阻塞项时节内只写一句「无阻塞项，按下方默认假设继续」，不带编号、`-`、`*`，不以问号结尾。
`### 脑暴 pitch` 只在用户没有可用想法时给 2–3 个明显不同方向，每个以 `#### Pitch N` 起头，等用户选或改再写。
每个 pitch 固定六项，标签逐字：`一句话前提：`／`欲望式：`（谁现在想从谁手里拿到什么）／`阻力：`／`可见代价：`（具体、可计量、有归属的可失去物，不是处境描述）／`开场钩子：`（异常结果、未完成行动、信息差、倒计时四法之一）／`标题候选：`1 个。
用户已有想法：不另给 pitch，先出 `## 张力门诊断` 表与推荐修改；表头逐字 `| 张力项 | 判定 | 原文引用 | 升级选项 |`，八行齐全；判定只写「成立」或「不成立」；原文引用列引用他的原句（带引号），原文没有对应句就写「无原句」；每个不成立行的「升级选项」列内写 2–3 个更爆款选项（①②③ 分隔：更早进冲突、更高可见代价、更狠钩子、更尖标题），选项必须写在表内这一列，不得把这一列改成「问题」列，也不得挪到表外的「方向 A/B/C」小节代替（表后可另加整体方向，但不能替代表内选项）；「标题」行不成立时，这一列直接写 2–3 个候选标题《…》，或紧跟表后加 `### 标题候选` 编号列表（≥2 行），不得只写「见下方候选」；不写夸奖，不擅自改写，用户选定或说继续才动笔。只有想法本身不成立时才给 2–3 个明显不同方向。题材、形式、时长写全但没说「直接写」，同样先诊断；仅在想法不成立、无法沿原方向修时用 pitch 六项格式给 2–3 个方向，否则只给诊断与推荐修改；没说「直接写」的第一条回复不得含剧本正文。这里的「用户选定或说继续才动笔」只针对剧本正文；大纲／分集请求按紧随其后的规则同回复交付。
「故事·大纲·连续分集」入口：用户消息含故事线／人物／前提且要求大纲或分集时，第一条回复必须在同一条消息内交付用户要求的全部集数大纲；`### 接单问题`（≤2，仍逐字；无阻塞项仍写「无阻塞项，按下方默认假设继续」）、`### 默认假设`、`## 张力门诊断` 与推荐修改放在大纲之前，但不得以「先诊断」「你定完我再写」「回一句继续」等把大纲推到下一轮。
张力门不成立项按推荐修改里的默认版直接写进大纲，并在对应集条目后标「可改」；未答的接单问题按 `### 默认假设` 定值。
只有 brief 连故事前提都没有（薄 brief）才只问不写；e1 选题入口与剧本正文两态的既有行为不变。
两态的最终成稿都必须带张力门表与 5～6 个标题候选，并停在文本，不自动进分镜、资产或 Prompt。

### 默认假设

- 画幅：未指定平台与画幅时，采用 16:9 通用母版（可改）；已指定平台时必须按平台推导，不走默认；不因「短视频」「社媒」默认 9:16、竖屏构图或安全区，这些只在用户明确抖音或竖屏后启用。
- 时长：未指定时不套平台默认总时长；单镜 `duration.target_s` 按动作可读性估一个正数并标「可改」，`live_check` 写 `TODO_VERIFY_LIVE`。
- 平台：通用短视频母版，未指定平台时不套专属规则。
- 受众：由 brief 明示；未明示时只作可覆盖的临时假设。
- 语言：简体中文；出海项目按目标市场语言直接写对白与画内文字，语域随角色身份、年龄与时代校对。用户给出任一项时覆盖对应默认值。

## 剧本张力门（形式自由，张力不自由；不读 references 也必须执行）

任何剧本、大纲或改稿，正文前先打印下表（标题逐字 `## 剧本张力门`）：证据列留空、只写 ✓、或写「无／生活本身／不适用」即未通过，不得进入分镜、资产、Prompt。冲突 = 有可失去之物的张力，不是吵架、不是反派、不是羞辱；此表与标题候选属于文本交付的一部分。同一回复内的大纲交付不在此限。

| 张力项 | 必须回答 | 证据（引用剧本原句或画面） |
|---|---|---|
| 想要 | 谁现在想从谁手里拿到什么，画面里怎么看出来 | |
| 阻力 | 是什么让他此刻拿不到，哪一处受阻是可见的 | |
| 代价 | 拿不到会立刻失去什么，具体、可计量、有归属 | |
| 升级 | 同一欲望至少两次尝试，后一次比前一次更难或更贵（时限、损失、知情人数或退路至少一项上升）；情绪更激动、换场重演、加一个反派都不算 | |
| 转折 | 哪条旧解释失效；推动转折的人、物或信息必须在转折前已出现或被预示（可回看），转折里主角自己有动作；新登场人物、突然冒出的证据或旁白不算 | |
| 钩子 | 开场四法（异常结果／未完成行动／信息差／倒计时）选哪一法，后文哪里兑现 | |
| 结尾 | 回收还是卡点（身份暴露／关系反转／危险逼近／关键选择／利益变化），兑现了什么动作 | |
| 标题 | ≥5 候选跨 ≥3 机制、选 1 备 2、过三测（陌生人会点／本集独有／不泄反转） | |

标题候选紧跟门表，格式逐字：`### 标题候选` 下每行 `N. 《标题》 — 机制：X — 三测：陌生人✓ 独有✓ 不泄✓ — 一句理由`，末行 `选定：《…》 备选：《…》《…》`；门表「标题」行证据可写「见下方候选」。
`### 标题候选` 节内只允许 5～6 条候选编号行与末行「选定：」；其后任何内容（理由、分工、备选方向等）必须另起 `##` 或 `###` 标题，不得在同节内再出现其他编号行（校验器会把它们计入候选并判三测缺失），也不写 `-`/`*` 项目行。
形式豁免：观察、氛围、喜剧、非线性同样填满八行。张力可以是 dread、压迫、时间、体面或一个即将破掉的模式，但必须写出谁在承受、什么会失去，不能用「安静」当豁免理由。
八行的定义、分形式对照与开场四法见 `references/dramatic-tension-engine.md`；标题机制、三测与候选格式见 `references/title-craft.md`。

## 开放创作与原生制作主路径

`Think → Setup → Generate → Test` 是反复回转的四种工艺动作，不是固定阶段：先判断观众为何继续看，再备必要资产、生成最关键画面，用真实像素找出最早出错的变量。

### 1. 选择或发明这条内容的创作发动机

先确定作品靠什么推进：因果升级、关系微变、实时期限、两难选择、公平悬念、生活观察、喜剧模式、氛围累积、非线性关联、视觉转化或新形式。因果戏可用欲望式：谁想从谁手里拿到什么、拿不到失去什么、愿拿什么交换。羞辱、翻面与可见代价是爽剧工具；怪谈、观察、视觉喜剧不必用，但同样写出谁承受什么。学机制，不复制 IP 人物、台词、标志道具或镜头顺序。

### 2. 让最早可读时刻诚实地属于后文

续看理由从开场四法中选：异常结果/未完成行动/信息差/倒计时；慢开场只有承载四法之一才成立。标题、首个可读时刻、正文与结尾属于同一观看承诺，不用假预告或旁白制造虚假利害。

### 3–10 工艺环与必读模块

| 工艺环 | 本环要交出什么 | 必读模块 |
|---|---|---|
| 3 预演定空间 | 零成本 `00_previs/` 白模锁站位、朝向、180° 轴线、人数与干净机位帧，`present` 带码拍板并推导 `required_views`；`acting_task` / `scene_event` 按形式选用 | `references/whitemodel-previs.md`、`references/continuity-storyboard.md`、`references/storyboard-camera-direction.md` |
| 4 锁资产 | 按 `required_views`（`front`+实际拍到的角度）与空场主景板出候选，`present` 带码挑定；参考职责相容、可独立验证 | `references/keyframe-assets.md`、`references/continuity-bibles.md` |
| 5 关键帧 | 首帧锁起因、站位、屏幕方向与道具状态，被遮挡肢体不进运动；尾帧锁完成姿势、道具位置、运镜落点与 hold | `references/keyframe-assets.md`、`references/single-scene-direction.md` |
| 6 运动 Prompt | 写“怎么变”不重复静帧，按真实片长分段；先测最难的代表镜头 | `references/prompt-compiler.md`、`references/prompt-contract.md` |
| 7 交接下一段 | 先标 `continuous_time` 或 `editorial_cut`，只继承通过 QC 的事实状态 | `references/continuity-storyboard.md`、`references/production-qc.md` |
| 8 声画后期 | 说话者归属清楚，环境声建空间、接触声证明动作，音乐不遮对白；CFR、剥封面流、字幕互斥 | `references/post-production.md`、`references/audio-music-ducking.md` |
| 9 平台分轨 | 先做叙事完整、声画同步、字幕安全的母版，再只为实际发布面分轨 | `references/platform-packaging.md` |
| 10 数据回写 | 只与同账号、同平台、相近阶段比较，数据指向下一轮要查的创作变量 | `references/story-short-drama.md`、`references/trend-research.md` |

四条硬规则不读 references 也执行：

- `proof not promises`（看像素）：资产与镜头是否可用只看下游像素里脸像不像、衣服是否同一套、道具是否同一个、空间能否正反打。模型名、Prompt 写得漂亮或“生成成功”都不是证据。
- 首尾状态无法由一条连续物理路径连接时，拆镜头，不用插值硬变。
- 每次重做只改一个变量：关键帧、身份源、服装、场景、道具、参考职责、动作过程、机位或时长；否则无法知道是哪一项起作用。
- 关键文字、聊天界面、价格、CTA、法律文案和字幕用确定性后期制作，不赌生成画面的伪字。

镜头语义合同（作用／continuity in／参考职责／不变量／首帧／分段运动／机位路径／表演与物理／尾帧／光与材质／声音与后期／最可能失败项／continuity out）见 `references/prompt-contract.md`；对用户只展示有用字段（Simplified JSON），内部 NBP v2 必填键不省略；`@图片N`、Higgsfield media flags、Lovart attachments、XYQ 参数、Grok `<IMAGE_0>` 都是 adapter 语法。

## 附属 Lane

短剧是默认主路径；以下 Lane 只在用户目标更窄或作为短剧附属物时启用。

| Lane | 用户目标 | 交付与规则 |
|---|---|---|
| A 单提示词 / 单镜头 | 单镜头或单 Prompt | 一条 Simplified JSON 与目标 prompt、参考职责、起止状态与最可能失败项；导演化动作读 `references/single-scene-direction.md`，不强建资产圣经。 |
| B 多镜头导演包 | 多镜头拍摄包 | 资产表、决策分镜、编号 shot list、逐镜 JSON、continuity in/out 与声画职责；不替代已选定的发动机与剧本。 |
| C 产品 / 品牌 / UI 广告 | 产品 / 品牌 / UI 广告 | 先读 `references/product-commercial.md` 选 hero、UGC、开箱、测评、TVC 或 UI journey，锁外形与一次可见证明；匹配剪辑或产品变身读 `references/commercial-match-cut.md`。CTA 留给后期，品牌记忆不进短剧。 |
| D 单人化 Faceless / 批量 | 不出镜的口播、解说、合集或批量系列 | 先定栏目承诺与视觉母版，单条仍走张力门；见 `references/faceless-youtube-workflow.md`。 |
| E 实拍底片 VFX / 参考改写 | 实拍底片 VFX / 参考改写 | 只写已批准的 effect-only delta，保留源片身份、表演、机位、时序与空间；动作迁移时源视频只承担获准继承的动作与时序；改地区版按 `references/platform-overseas.md` 重锁并重新批准。 |
| F 已有素材成片 / 发布 | 已有素材成片 / 发布 | 先 `reconcile` 登记已有素材，再从 selects、配音、SFX/BGM、字幕、剪辑、调色、导出与包装开始；要成片时 Prompt 不是终点。 |

## Provider / 执行路由

先发现当前宿主可用的 adapter（`list_execution_providers.py --delivery-mode <mode> --json`，报 `installed/logged_in/enumerates_models/operation_supported/quoted` 五级发现态），未点名时按执行选择门只问缺项，再按 exact model、授权、费用与 live schema 只加载一个。下表是已知 adapter 示例，不是固定 provider 集合：

| 任务 | 加载 |
|---|---|
| 角色表、道具表、场景与关键帧 | 当前宿主可用且获授权的 image adapter；Hermes `image_generate` 只是一个示例 |
| Lovart / Atlas / Seedance / Kling / Higgsfield 直提 | `lovart-api`、`atlas-cloud`、`higgsfield-generate`（Higgsfield 草稿双 ID、`@` 开头 prompt 与 4K 后处理见 `references/adapter-higgsfield.md`） |
| Google Flow（Nano Banana 2.1／Veo 3.1／Omni 1.2）、Grok 网页、Popcorn 等仅网页通道 | 默认通过宿主浏览器自动化桥（MCP / CDP）；遇 reCAPTCHA／hCaptcha 等人机验证即停并报告，不绕过 |
| 小云雀图片、视频直出或短剧会话后端 | `xyq-skill`、`xyq-short-drama-skill` |
| 精剪、拼接、字幕、混音、动态包装、程序化成片 | `precision-video-editing`、`videoedit`、`hyperframes` |
| 脑暴模式搜源、抓取、逐帧分析 | 先 `python3 scripts/list_research_tools.py` 探测；grok CLI、hermes、`agent-reach`/`opencli`、`yt-dlp`、agy；宿主原生检索只补位 |

执行服从 adapter：`发现 live model → 读 schema → 映射参考职责 → 核凭证/额度 → 提交 → 验收真实结果`；只有异步 job 才轮询，只有远端文件才下载。付费 POST 超时先查 job，不盲重提。画面分析默认走 `agy -p "<问题>" --model gemini-2.5-pro --effort high --add-dir <目录>`（可通过 `AGY_MODEL` 覆盖）；无 agy 按 `references/host-capability-fallback.md` 标 `ANALYSIS_SKIPPED`，不凭想象顶替；可用区间以完整回放为准。

## 完成标准：看观众效果，也看真实像素

完成不是填满模板，也不是 provider 返回 success。

- 剧本成稿时，张力门八行均有可引用证据；标题（5～6 候选，跨 ≥3 机制，选 1 备 2）、首个可读时刻、正文与结尾属于同一观看承诺；推进符合所选形式与创作模式，人物不可互换，对白能自然朗读，结尾是前文挣来的；表达审校通过，未用改口气偷换剧情。
- 资产、分镜与 Prompt 成稿时，复用的脸、服装、场景和道具跨关键镜头守恒；每镜有明确用途，只有继承或变化的维度才要求可核验起止状态；Prompt 写运动变化过程，参考职责不打架，首尾帧物理可达，易变参数没被冒充成永久事实。
- 真实生成与最终成片时，有实际下载文件、完整 decode、连续观看、接触表与实际听音记录；身份、手、道具、空间、运动与末帧在像素里成立；对白清楚、字幕准确、音乐不抢戏，原生分辨率如实披露。保留原动作时序的任务按源片同一时刻比较关键动作与末段身份，不裁掉真实动作隐藏迁移失败。按 `references/production-qc.md` 分验 `technical/visual/audio/brief` 四栏（无声静帧 `audio=not_applicable`，所有适用栏 `pass` 才签总 PASS，任一失败或 `needs_review` 都不得签总 PASS，缺音频工具如实 `needs_review`）；未经批准的静态或重复素材补时不能冒充完整动态成片；抽帧/自报不等于完整回放。
- 实际发布时，只为已选平台保留对应资产与可核验链接/状态；发布数据写回证据指向的创作变量，可能是续看理由、节奏、关系、感官模式、兑现或包装，不预设为下一轮钩子。

## 按需参考

下表只列仓库内真实文件：

| 需求 | 文件 |
|---|---|
| 趋势搜源、风险分级与平台/监管证据快照 | `references/live-trend-intelligence.md`、`references/platform-risk-and-compliance.md`、`references/2026-platform-evidence.md` |
| 脑暴选题热点雷达（搜源→拆解→选题→反固化） | `references/brainstorm-topic-radar.md` |
| 剧本格式、人味、剧本门与标题深化 | `references/script-writing-craft.md`、`references/human-texture-and-script-gate.md`、`references/title-craft.md` |
| 冲突／逆转爽剧与热点样本拆解 | `references/story-short-drama.md`、`references/trend-research.md` |
| 电影 vs 短剧五维心法与执行、同前提对照案例 | `references/cinema-vs-short-drama.md` |
| 批量生产与通用电影方法 | `references/academy-production-system.md`、`references/cinematic-method-playbook.md` |
| Simplified JSON、NBP v2 IR、八目标编译与 2026-11-24 能力矩阵 | `references/prompt-contract.md`、`references/prompt-compiler.md`、`references/model-adaptation.md` |
| Provider、交付模式、继承式选择、对账、live schema 与宿主退化 | `references/provider-execution.md`、`references/host-capability-fallback.md`、`references/adapter-higgsfield.md` |
| 跨会话恢复、逐镜重拍与后继失效检查 | `references/sequence-resume.md` |
| 声音、口型、字幕、多 Take、音乐与 ducking | `references/post-production.md`、`references/audio-music-ducking.md` |
| 已选平台分轨、项目结构、manifest 与成片检查；抖音／出海条件化模块 | `references/platform-packaging.md`、`references/production-qc.md`、`references/platform-douyin.md`、`references/platform-overseas.md` |
| 产品/品牌/UGC/TVC/UI 与 Faceless 批量 | `references/product-commercial.md`、`references/faceless-youtube-workflow.md` |
| 适用范围、证据分级与内容边界 | `references/provenance-scope.md` |
| SPEC v2.0 宪章、L0/L1、盲审、熔断、STALE 与错题库 | `references/00-target-spec-v2.md`、`references/harness-guardrails-and-eval.md` |
| 白模站位预演、五步映射、建模工具选择与环境资产图交接 | `references/whitemodel-previs.md`、`references/previs-path.md`、`references/stage-desk-previs.md`、`references/blender-previs.md` |

用户面模板（默认展示）：`templates/simplified-image-prompt.json`（已验证图像目标：`google_flow`）、`templates/simplified-video-prompt.json`（已验证视频目标：`seedance_2_5`）。
可复用模板（NBP v2 优先）：`templates/prompt-package.json`、`templates/asset-manifest.json`、`templates/shot-selects.json`、`templates/stage-plan.md`、`templates/nbp-v2-image-prompt.json`、`templates/nbp-v2-video-prompt.json`、`templates/nbp-image-prompt.json`、`templates/nbp-video-prompt.json`、`templates/character-bible.md`、`templates/scene-bible.md`、`templates/visual-style-bible.md`、`templates/continuity-ledger.md`、`templates/view-requirement-manifest.md`、`templates/resume-manifest.json`、`templates/release-intent.json`、`templates/whitemodel-blocking-plan.json`、`templates/delivery-gate-cases.json`、`templates/blender-previs-plan.json`、`templates/stage-desk-project.json`。

修改或核验 Skill 后可在根目录运行：

```bash
python3 scripts/mistake_book.py validate && python3 scripts/mistake_book.py tier1-run
python3 scripts/check_capability_expiry.py --include-matrix
python3 scripts/validate_platform_evidence.py --stage repository
```

## 常见错误

完整分层对照与重测见 `references/failure-diagnosis.md`；Lovart 执行与费用读 `references/lovart-execution-notes.md`，锁脸与续写读 `references/face-consistency-execution.md`，首帧诊断读 `references/seedance-first-frame-action.md`。不把免费、免审、锁脸或硬限制的猜测当事实，用户批准 take 后不擅自重拍。
- 窜记忆：把无关项目带进当前作品；装置冒充推进：设定没有造成可见变化。
- 未锁资产就海量生成；一次重做换多变量；误译加戏（`无工牌` 译成 `bare-chested`）；驱动首帧被遮挡的肢体导致前景交互崩坏；网页低清片段放大冒充原生 1080p。
- 张力门证据列禁写全角竖线「｜」（如「02:10｜营地」）：`validate_script_gate.py` 会按列分隔符拆格报 `EMPTY_EVIDENCE`；证据列改用空格或「·」，画内文字表不受影响。
