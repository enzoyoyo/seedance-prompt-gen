# Provider Execution

## 方法与执行分离

`seedance-prompt-gen` 产出语义合同和生产记录；provider adapter 负责实时模型发现、鉴权、上传、提交、轮询和下载。不要把 adapter 的完整 CLI/API 文档复制回来。

每次只加载一个执行 adapter。只有主路径客观失败且备选路线已获授权，才加载下一个并记录 fallback 原因；被用户否决的方法不能作为自动 fallback。Adapter 的默认省略费用说明或只打印结果 URL，不覆盖本模块的授权、预算、QC 与成片交付合同。

## 执行选择门（弹出选 provider）

真实生成图片、视频或音频前，按用户这句话里有没有点名来分三态；这道门只管「用哪个 API 执行」，不改创作判断：

| 用户说了什么 | 动作 |
|---|---|
| 明确要求实际生成并点名 provider / model / adapter | 按已授权范围开始：Preflight → 提交；model lock 生效，不静默换模型。只问截图中模型是否合适时停在评估，不创建付费任务 |
| 要生成、出图、出片、成片，但没点名 | 先输出 `### 执行选择`，停下等用户选；不提交、不猜、不默认选最贵或最熟的 |
| 只谈想法、剧本、文案、方向，没提生成 | 停在文本交付（剧本／文案／方向），不弹选择，不提 adapter |

`### 执行选择` 的表由 `scripts/list_execution_providers.py` 生成（只报凭证名与 present/missing，不回显值），当前模型再补一行推荐与理由：

```bash
python3 scripts/list_execution_providers.py          # Markdown 表，直接贴进回复
python3 scripts/list_execution_providers.py --json   # 供宿主弹窗或其他 Agent 读取
python3 scripts/list_execution_providers.py --delivery-mode video_clips --json  # v7：按交付模式过滤并输出五级发现态
```

- 宿主有交互式提问工具时，用同一批选项弹窗；没有时以这张表结束本轮回复，等用户回「用 N」或点名 adapter。
- 每行给：adapter 名、能做什么（image/video/audio/analysis）、凭证名与 present/missing、CLI 或 adapter 目录是否在、状态。缺凭证的 adapter 也列出，用户仍可选，Preflight 会显式报缺失，不静默降级。
- 推荐只写一条，理由来自当次任务（画幅、时长、参考槽位、费用、live schema），不来自「上次用过」。
- 同一作品同一会话内选定后不再重复弹；用户换 provider 时走下文「换 provider 交接清单」。
- 凭证不轮换、不替用户填、不写进任何文件；缺失时把状态写成缺凭证，由用户自己补。

## v7 交付模式与低摩擦选择

### 四种 `delivery_mode`

| `delivery_mode` | 交付什么 | 门序终点（`drama_next.py --v7`） | provider 列表 |
|---|---|---|---|
| `prompt_only` | 逐镜模型中立 Simplified JSON（仅在用户点名或选定目标模型时另附编译方言 prompt）+ dry-run 展开命令；真实提交一律 `DELIVERY_MODE_PROMPT_ONLY` | 镜头规格 | 不弹 provider；未点名目标模型时只交 Simplified JSON，点名后才编译对应方言 |
| `images_only` | 角色、场景、道具与关键帧静帧，经用户挑定 | 资产定稿（Human Gate #2） | 只列 `image` 通道 |
| `video_clips` | 通过逐镜验收的视频 take 与 `usable_in/out` | 逐镜验收 | `image + video` 通道 |
| `full_film` | 剪好、混好音、烧好字幕的可播放成片 | 终检交付 | `image + video + audio + post` 通道（含本地 `ffmpeg`） |

`sop_version: "2.0"` 的旧项目继续用 `prompt_only | tool_render` 两态，行为不变；新建 v7 项目（尤其与旧版同名的 `prompt_only`）初始化时显式传 `python3 scripts/drama_setup.py init --project <项目目录> --sop-version 3.0 --delivery-mode <mode>` 消歧。`drama_next.py <项目目录> --v7 --json` 仅对 `sop_version: "3.0"` 或显式四态 `delivery_mode` 启用 v7 倒推图，不会劫持旧版 2.0 项目；未选到的阶段不出现在倒推图里，也不为它们弹选择。

### 启动顺序、暂存解析与编号回复

已有项目目录或续接任务，**第一条命令始终先跑只读** `drama_next.py` 查看当前唯一门节点；当门序停在决策／门禁节点（或尚未建清单而准备进入生成）时，再调用 `model_gate.py resolve`：

```bash
# 0. 已有目录先只读查当前门
python3 scripts/drama_next.py <项目目录> --v7 --json
# 1. 解析本轮指令：仅写入 drama.choice_resolution 暂存，绝不静默代签 model_gate.confirmed_at
python3 scripts/model_gate.py resolve --project <项目目录> --user-words "<用户本轮原话>" --json
# 2. 用户对展示菜单回复编号时（新项目首次菜单先问 delivery_mode 一项，如回复 "2" 选 images_only；
#    已定 full_film 多项缺失时回复如 "1, 3, 2"），拿展示当时的 --request-id 与 --revision 直接落锁 model-gate，
#    或先 resolve 后不再重放旧编号与旧 revision；显式参数若与编号冲突会拒绝写盘：
python3 scripts/drama_setup.py model-gate --project <项目目录> \
  --request-id <菜单request_id> --revision <菜单revision> --user-words "2"
```

决定按以下优先级继承，命中即视为已答，不再弹：

1. 本轮用户原话（如「用 Flow 出图、Seedance 2.5 出片」「只要提示词」）；
2. 项目已锁选择（已确认的 `drama.model_gate`、`release_intent` 与 `delivery_mode`）；
3. 本会话先前的明确暂存（`drama.choice_resolution`）。

`resolve` 只对**真正缺失的必选决定**输出选择：宿主有选择器组件时给 `host_selector_payload`（`ask_question` JSON），没有时给紧凑编号 `1..N` 并结束本轮等用户回复（**STOP & WAIT**，无默认、不代答；带 `evidence: "default"` 的推断值不会自动锁进 Human Gate #1）。自然语言里有冲突（同一项点了两个值、或点了已被否决的值）时只问那一项。纯文本请求——想法、脑暴、方向（「给我三个方向」）、剧本、大纲、改台词、写文案——返回 `text_only: true`、`missing: []`，不写清单、不弹任何生成菜单。过期或不匹配的 `request_id`／`revision` 报 `STALE_MENU_ANSWER` 拒绝覆盖，保证清单字节不变。

### 五级发现态

`python3 scripts/list_execution_providers.py --delivery-mode <mode> --json` 对每个通道输出五级发现态字段（不加 `--json` 默认输出兼容 Markdown 表；未探测项为 `null`，需探测本地兼容模型网关目录时加 `--probe-network`），不跳级宣称：

| 状态 | 含义 | 证据 |
|---|---|---|
| `installed` | CLI／adapter 目录／浏览器桥存在 | 路径或版本输出 |
| `logged_in` | 凭证或登录态存在 | 只报 present/missing，不回显值 |
| `enumerates_models` | 能列出当日模型目录 | `model list` 或本地目录只读回执 |
| `operation_supported` | 目标操作（如首尾帧图生视频）在 exact model schema 里存在 | `model get`／schema 回执 |
| `quoted` | 拿到这次完整配置的报价 | 报价回执；没有就不进入付费提交 |

网页才有的通道（Google Flow、Grok Web、Higgsfield 网页工作台、ElevenLabs 网页）默认经宿主浏览器自动化桥（MCP / CDP）操作；遇到 reCAPTCHA、hCaptcha 或任何人机验证即停止并报告，由用户在可见窗口自行处理，不求解、不绕过、不换缓存地址重试。

### 棕色地带接手：先对账再推进

```bash
python3 scripts/audit_takeover.py reconcile --project <项目目录> --json          # 默认只读（同显式 --dry-run）
python3 scripts/audit_takeover.py reconcile --project <项目目录> --apply --json  # 无损写入 manifest.inventory 媒体清点
python3 scripts/audit_takeover.py reconcile --project <项目目录> --apply --tier draft \
  --choose S01=01_takes/s01_v1.mp4 --json                                       # 显式将已有视频关联为镜头待审 take
python3 scripts/drama_next.py <项目目录> --v7 --json
```

`reconcile` 自动扫描项目根目录及 `01_takes/`、`02_final/`、`clips/`、`clips_v2/`、`images/`、`output/` 下的媒体文件，按哈希与现有清单核对并归为 `matched`／`orphan`／`ambiguous`／`missing` 四类（剧本、`.srt/.ass` 字幕与旧台账列入 `support_files`）。`--apply` 只保存 `inventory` 媒体清点，不重写已有文件、不凭文件名自动认领 take；要把已有视频关联到具体镜头进入待审，必须显式传 `--choose SHOT=FILE`（可重复，配合 `--tier draft|lowres|final`，要求 `--apply`）。旧剧本对账入口 `audit_takeover.py --script <剧本> --project <项目目录>` 仍须传 `--script`。之后一切推进仍听 `drama_next.py`。

### 小项目重试配额

`sop_version: "3.0"` 项目全片重渲染上限为 `max(1, min(5, floor(0.30*N)))`（N 为镜头数），保证 1–3 镜的小项目至少还有一次重拍；单镜同档自修仍 ≤2 轮。`sop_version: "2.0"` 项目沿用原公式。

### 未知提交与余额冻结

- **未知提交冻结**：付费 create 超时、回执丢失或没拿到任务 ID 时，该通道进入冻结：先按任务列表／时间窗回读，并做一次时间更晚的余额回读；确认没有已 accepted 的任务前，同通道不再 create。
- **余额冻结**：余额回读低于「下一镜报价 + 返工预留」，或出现 402／余额不足报错时，冻结全部付费提交，给出缺口与选项（缩短、追加授权、换形式），等用户决定；不自动换收费通道、不充值。
- 冻结只停新提交，不撤销已通过验收的 take。

## 显式模型门禁（Human Gate #1 · STOP & WAIT）

v7 项目先跑上文 `model_gate.py resolve`，只为缺项弹选择；下文 `render` 四项菜单保留给 `sop_version: "2.0"` 项目与需要完整菜单的场合。

SPEC v2.0 项目（`drama_setup.py init` 默认写 `sop_version: "2.0"`）在任何实际生图、生视频或音频生成前，必须由用户自主选定四项必选，不静默预设默认值，不在同一回合替用户自问自答：

1. **图片生成模型**；2. **视频生成模型**；3. **音频方案**（BGM 模型 `bgm:<model>` / 配音与音效模型 `tts_sfx:<model>` / 组合 `bgm:<m>+tts_sfx:<m>` / 本项目无需生成音频 `none`）；4. **全局规格与交付模式**（画幅比例、总时长与镜头节奏、风格基调、「仅输出结构化提示词」`prompt_only` 或「直接调用工具渲染成片」`tool_render`）。

```bash
python3 scripts/model_gate.py render --format both    # 编号菜单 + 宿主 ask_question JSON（复用本机 adapter 探测，只报 present/missing）
python3 scripts/drama_setup.py model-gate --project <dir> --image-model <用户选> --video-model <用户选> \
  --audio-plan <none|bgm:..|tts_sfx:..> --delivery-mode <prompt_only|tool_render> --aspect-ratio <比例> \
  --pacing "<总时长与节奏>" --style-tone "<基调>" --user-words "<用户原话>"
python3 scripts/model_gate.py check --project <dir>
```

- 宿主有交互提问组件时用 `ask_question` JSON 弹窗；没有时贴编号菜单并**立即结束本轮回复**等用户逐项回复。
- `model-gate` 拒绝空原话或 `TODO`、`auto_default`、`assumed_by_agent`、`<...>` 等代填占位；画幅仍按已选平台推导。
- 未锁齐时：`drama_next.py` 在首次生图前（`identity` 门）与每次付费提交前报 `MODEL_GATE_MISSING` / `MODEL_GATE_INCOMPLETE:<field>`；`ledger_submit.py submit` 真实提交拒绝（`--dry-run` 只警告，不花钱）。
- `delivery_mode == "prompt_only"` 时真实提交一律 `DELIVERY_MODE_PROMPT_ONLY`；只交结构化提示词与 dry-run 展开的命令，用户回传成片/截图走 `eval_harness.py post-gen --clip` 轻量盲审（见 [harness-guardrails-and-eval.md](harness-guardrails-and-eval.md)）。
- 与上面的执行选择门同源：已点名 provider 只算回答了对应一项，其余项仍须用户补齐；同一作品同一会话锁定后不重复弹。

## 路由

### Hermes `image_generate`

用于角色、地点、产品/道具表、storyboard、首尾帧和 UI still。它不是视频 provider。生成静帧仍要做 downstream-use QC。

### `lovart-api`

使用条件：用户点名 Lovart、已有 Lovart project/thread、需要 canvas 工作流，或指定只在 Lovart 内可用的模型。

边界：Lovart messenger lane 默认传递用户原始描述，不自行改写。若用户明确要求本 Skill 先做 Prompt 设计，则把**用户已批准的 Prompt package**作为明确输入交给 Lovart；不要在 adapter 内再次扩写。必须遵守 config/thread 复用、确认高成本任务、下载并交付结果的规则。

### `atlas-cloud`

使用条件：需要 API/schema-driven 直连模型，或用户点名 Atlas。

执行顺序：实时 models → `display_console` 可用性 → 精确 model schema → 只构造 schema 中存在的字段 → submit → poll → download → verify。模型列表可见不等于账号有提交资格；真实 402/entitlement 要如实记录。POST 失败不盲目重试。

### `higgsfield-generate`

使用条件：用户点名 Higgsfield、Higgsfield CLI、Marketing Studio、Higgsfield 资产或专有 job-set。

执行顺序：account status → live model/workflow catalog → exact schema → 最小必要 media-role mapping 与报价 → 授权核对 → 完整素材选入/参数回读 → submit once with wait → result download/QC。普通 model list 没有某功能时，继续查 workflow catalog，不据此宣布功能不存在。Marketing Studio 的 mode slug、素材角色、时长、分辨率均以 live schema 为准。网页选素材、产品别名、执行通道、Cinema Studio 与白模底片见 [adapter-higgsfield.md](adapter-higgsfield.md)。

宿主没有对应工具时按 [host-capability-fallback.md](host-capability-fallback.md) 降级，标 `NOT_SUBMITTED` 或 `RESEARCH_SKIPPED`，不假装已提交。

### `xyq-skill`

使用条件：用户点名小云雀/XYQ/Pippit、指定 CLI 直出、首尾帧直出，或使用其综合 Agent。

Direct-model lane 要保持用户原始 Prompt，不能再扩写。若先由本 Skill 设计 Prompt，必须把它标记为用户批准的显式请求。保存 thread/run/link，轮询并下载结果。

### `xyq-short-drama-skill`

只用于服务端短剧链与文件资产。它不是通用 Prompt owner。进展与 file list 并行查询；重要剧本、场景、角色、分镜、视频产物必须下载。

## Model lock 与能力真实性

- 用户指定 provider/model 时，用该 adapter 当前支持的硬约束方式提交；不可用时停止并说明，不静默换模型。
- 图片、角色、产品或关键帧资产全部通过下游用途 QC 后，才进入高成本视频阶段；错误模型或被否决产物标记 `superseded`，不得继续引用。
- 分开报告**模型原生输出**与**后期交付规格**。例如原生 1080p 后期超分到 4K，不能写成“原生 4K”。
- 时长、比例、分辨率、参考素材数、原生音频和口型只来自本次 live schema；Prompt 里的“4K/15 秒”不是能力证明。
- 返回 timeout、running 或已有局部 artifact 时，先按 job/thread/run 回读终态；只有 terminal status、本地文件与 QC 都齐全才算完成。
- 跨平台成本不能直接比较积分数量；先锁定同一分辨率、时长、模式与音频／参考输入职责，再按当前费率换算为实际货币成本或可交付镜头数。

## Provider adapter translation

先建立：

```text
canonical_asset_id → semantic_role → provider_field/flag → upload/reference_id
```

- Dreamina web 的 `@图片N/@视频N/@音频N` 只在当前 UI 仍支持时使用；
- Higgsfield 使用 live media flags；
- Atlas 使用 model schema 字段；
- Lovart 使用 attachment/project/thread 合同；
- XYQ 使用 asset IDs 或 CLI local paths。

不要把一种语法复制到另一种 provider。

## Preflight

真实提交前记录：

- provider 与 adapter；
- 实际 model/job-set；
- schema 获取时间；
- auth readiness（只写 present/missing，不回显密钥）；
- balance/entitlement/confirmation 状态；
- request 文件路径；
- canonical asset 与 provider role 映射；
- 预期输出与 QC。

## 锁定完整交付预算

首个付费任务前及每次计费后，在现有 generation log 更新：当前可用余额（时间与账号范围）、当前 exact model + 时长/分辨率/音频/参考模式的报价或真实收据、已提交未结算项、剩余必拍镜头和关键结尾、返工预留、授权支出上限。计划同时区分原始生成时长与通过 QC 的可用区间；不能假设每条任务全段可用。

- 不能直接把余额页的通用“可生成 N 次”、旧价、别的模型报价或公开免费活动当成本次档位配额；免费须在当前账号、实际通道、exact model 与完整请求配置上确认权益已应用且报价为零。网页活动不自动覆盖 CLI/API；用工具按相同计费单位计算，未知报价、其他并发消耗和退款未确认都标不确定，不能乐观算进可花余额。
- 提交前核算本次费用后是否还能覆盖剩余必拍与返工预留。预留按本作风险和授权确定，不硬编码跨模型点数、比例或“最后三次”；在扩批前优先验证最难动作及结尾机制，给完整故事留预算。
- 提交前记录每个获准 take 的支出上限与远端 create 次数上限；区分未创建远端任务的本地参数拒绝、已 accepted 的任务和获准新 take。恢复等待不是新的 create，退款也不是自动重试许可。相同失败重复时暂停抽卡，查看污染参考、动作负载和路线设计；只有重测仍在授权内才改变最早失败变量，不为凑时长耗尽收尾预算。
- 预算、额度、权限不足或关键镜头无法在批准范围内完成时，**先停提交**，核清进行中任务与实际扣费，给出缺口及缩短/追加授权/改变形式的选项；不得擅自改成交付形式、换收费 provider、购买或充值。若已有明确降级授权，按其范围执行并留原授权，不重复询问。`stop_submit` 是预算/权限/授权不足时暂停新提交的执行动作，不是最终视觉或 brief 的 PASS/FAIL 状态；原交付是否完成仍独立验收。
- 跨通道（网页工作台 / Ark / Atlas / HiAPI / 聚合页）的积分、时长、分辨率不可直接比较；先锁同一职责再换算。
- live 检查项含 `region_availability`：提交前读目标端可用性提示（例如某模型在美国区不可用），不靠报错才发现。

### 通道能力卡与先草稿（AI 短剧）

短剧项目里每个要用的通道，先在清单登记一张能力卡（`python3 scripts/drama_setup.py channel --project <项目目录> --name <通道> --card <卡.json>`；同理决策图用 `python3 scripts/drama_setup.py present --project <项目目录> --gate previs|identity --candidate GROUP/LABEL=path`），七个问题逐条带核实日期 `verified_at`，整卡带 `expires_at`；答案来自当次 live schema、帮助输出或真实回执，不凭记忆：

| 字段 | 问题 |
|---|---|
| `draft_tier` | 有没有比成片便宜的草稿档 |
| `draft_upgradable` | 草稿能不能按任务 ID 升成成片（否则成片要整条重生成） |
| `balance_query` | 余额能不能查到 |
| `recover_by_id` | 提交后能不能凭任务 ID 查回结果 |
| `ref_transport` | 参考图怎么传（本地上传／URL／素材 ID…），填文字 |
| `plan_required` | 所需套餐档位（如 `"none"`／`"Pro"`，零成本查不到填 `"unknown"`） |
| `daily_limit` | 单日生成限额（填正整数、`"none"` 或 `"unknown"`） |

另填 `limits.max_duration_s`（单条时长上限，同样带日期），以及 `recipe`：写着这个通道三档提交命令模板、`--id-field`、回读与查余额命令的 reference 路径。卡缺项、过期，提交口直接拒绝；缺 `recipe` 时 `drama_next.py` 会提示先写配方。

`scripts/check_budget_gate.py` 在每次提交时执行，`ledger_submit.py` 内部也会调用：

- **先草稿**是短剧默认：有草稿档先出草稿，没有就先出低清；草稿整集经用户点头后才允许成片档。用户限定单次（「只出一次」）或失败不重试时让路——把额度用于已批准的实际规格，不额外生成低档样片；用 `confirm --kind one-shot` 记下原话与档位。
- **试价与风控探针**：每个通道每个档位的第一条提交必须是待拍镜头里最短的一条，结算后才放行其余；`real_public_figures=true` 时该条已结算成功的同通道 take（`ref_sha256s` 匹配当前锁定角色图）兼作真人肖像风控探针。
- **批次、失败后回读与日限额**：能查余额的通道，试价后回读余额并用 `ledger_submit.py balance --readback-file <回读输出文件>` 记录摘要（时间必须晚于试价结算），按试价实际单价估算剩余镜头，超出余额就拒绝；同通道出现任何失败或 `unknown` 的 take 后，下一次提交前必须有一条时间更晚的余额回读（`BALANCE_REQUIRED_AFTER_FAILURE_OR_UNKNOWN`）；`daily_limit` 为正整数时达当日上限即阻断（`DAILY_LIMIT_REACHED`）；查不到余额，或 `plan_required`／`daily_limit` 为 `"unknown"` 的通道，进入批次前必须有用户的继续原话（`confirm --kind unknown-cost`）。脚本自己不查余额、不联网。
- **同通道提示**：一个项目里混用「草稿可升级」与「不可升级」的通道时给出警告——草稿与成片不同源会让验收过的草稿失去参考价值；是否混用由用户定。

### 实际费用归因

1. 优先按 ledger 的 task/job ID 对扣费、退款；没有关联 ID 时，用任务时间窗、实际 display name/job type 和扣费/退款类型限定候选，并把结论标为时间/型号关联，不冒充精确任务归因。
2. 按 live 返回的名称筛选。动作控制条目可能只写功能名而不含底层模型品牌；不要用品牌与功能的关键词 AND 得到空结果后报告免费或净零。
3. 用工具去重、求和并核对查询范围/分页。账户余额差包括其他任务、并发消费及退款，不能全部归到当前视频；无法确定的费用保持未知。

### ElevenLabs / Atlas 执行注意事项

- ElevenLabs：仅当用户点名或上一 provider 额度耗尽后获准改走。记录 requested/reported model；曾观察到 Seedance 2.5 在美国区不可用，换 2.0 仍须重锁身份参考。
- Atlas Cloud：API/schema 直连；`402 Payment Required` 先停提交，不改剧本洗成通过。

## 成本路由原则

本节只写路由**原则**；具体档位价差、单次时长上限、参考图/视频/音频的槽位数量全部 `TODO_VERIFY_LIVE`，提交前按当前 provider 的报价页与 `--help`／能力接口读，不照抄任何写死的数字。

- 只有用户批准探索与多 take 预算时，才采用「便宜档跑探索，贵档只跑定稿」：先用低分辨率／快档把动作、调度、身份验通，通过后再用定稿档重出该镜。单次或失败不重试的授权直接用于已批准的交付规格，报价/素材核验不产生额外生成任务；哪个档更便宜按当次报价判断，不在本文件固定 model 名次序。
- 分辨率不够时优先「低档生成 + 后期放大」，不是直接上贵档；放大走确定性后期，见 [post-production.md](post-production.md)。
- 逐镜短生成是最贵的做法。能在一条里内部切镜完成的段落就不要拆成多条；能拆多长受当前 model 单次上限约束（`TODO_VERIFY_LIVE: max_single_duration`）。
- 超出单次上限的成片按**续写**推进（把上一段真实末帧或末段喂回去），不是各段独立生成后硬拼；续写的连续性要求见 [sequence-resume.md](sequence-resume.md) 与 [keyframe-assets.md](keyframe-assets.md)。
- 参考图、参考视频、参考音频的可用槽位数按当前 schema 读，不为「最多支持」而填满槽位；职责声明见 [face-consistency-execution.md](face-consistency-execution.md)。
- 模型 × 分辨率不兼容会在提交时直接报错，按 [adapter-xyq.md](adapter-xyq.md) 的「报错原文 → 处理动作」表处置，不预先在本文件维护兼容矩阵。

## Submit / poll / download

- 付费 POST 不因网络超时自动重发；先查已有 job/thread/run。
- 成功响应只表示任务建立；完成必须有 terminal status、结果 URL、本地下载和验证。
- 记录 provider adjustments/coercions；不要把被自动改写的参数当作原请求成功。
- 保留成功项目；只有剩余或新增明确授权允许时，才对 missing/failed items 新建重测任务。既有任务恢复、视觉拒收、退款与获准新 take 分开记，禁止重试的失败件只保留证据，不自动补产。

多镜或跨会话恢复时按[逐镜恢复与重拍](sequence-resume.md)保存任务状态和父镜版本；检查器只给下一步计划，不能发起提交。编译器输出的 `provider_ready=false` 表示还需执行期核验，不因 JSON 通过或能力收据存在而跳过本节 preflight。

## 换 provider 交接清单

额度耗尽或地域不可用而换端时，先输出再续产：

- 已完成段落与各段 `requested_model` / `reported_model`
- 批准身份参考的可达 URL（不是本机路径）
- 画幅、分辨率、帧率、声音基准
- 新 provider 首段必须先做**同一代表镜复现测试**，通过后再批量

没有这份清单就换端，等于把角色漂移和画质跳变再放大一轮。

## Fallback

Fallback 必须可追踪：

```text
attempted provider/model
failure class
whether job was created
fallback provider/model
quality/cost/capability trade-off
user-visible truth
```

不能声称使用了请求模型，实际却静默降级。

## Post-generation verification

对视频：

```bash
ffprobe -v error -show_streams -show_format -of json output.mp4
ffmpeg -v error -i output.mp4 -f null -
```

再按 [production-qc.md](production-qc.md) 分验技术、视觉与 brief：完整 decode 或播放器播到结尾仅证明文件可播放，provider `completed` 仅证明已返回产物。原动作/音乐复现的同秒对照与回放按其「要的动作 vs 实际演的动作」执行；存在音轨不证明保留了原音乐，静态脸图或首帧通过不证明整段锁脸。把确证的像素问题写成现象与证据；根因只有在隔离变量重测或可核验 provider 诊断支持时才断言。路人干扰、增加身份图或改 Prompt 是否能修好仍是待验证假设，不包装成可靠修法。

通过验收后交付实际附件与简短结果说明；未通过的文件只能标诊断/测试版，不能当终稿。保存内部任务、费用和 QC 证据，不用迟到的过程通知或原始报错代替成片。

画面与视频内容分析（关键帧比对、contact sheet 读图、逐镜看片记录）默认走终端 `agy`（可通过 `AGY_MODEL` 环境变量覆盖默认模型）：

```bash
agy -p "<要核对的问题>" --model "${AGY_MODEL:-gemini-2.5-pro}" --effort high --add-dir <素材目录>
```

`agy models` 可确认档位；`--effort` 只有 low|medium|high。宿主没有 `agy` 时按 [host-capability-fallback.md](host-capability-fallback.md) 退化，并在 QC 记录里写 `ANALYSIS_SKIPPED: agy unavailable`，不用当前模型的想象顶替。agy 的判断只是证据之一，`usable_in/out` 仍以完整回放为准。检查实际分析正文而不只看退出码：返回码为 0 但只有 timeout/partial 提示或未覆盖要求时，仍记分析未完成；保留输出和未核维度，不得按工具成功签审片 PASS。

## 授权、交付与验图细则（自 SKILL.md 下沉，逐字保留）

- 真实提交前只加载一个执行 adapter，并读 `references/provider-execution.md` 锁定完整交付预算；用最小必要配置尽早核到 exact model、输入模式、时长、分辨率与当前通道的真实报价，再做可选参考与 Prompt 润色。公开免费活动、余额页次数或另一通道权益不是本请求零费用证据；提交前再次核价，不能只凭宣传或通用次数扩批。生成次数与付费金额分开授权、分开记账：免费/Unlimited 图片也是一次生成，不能在额度未变时擅自增加诊断图或比较模型；只做用户要求的模型及张数。AI 短剧默认先草稿：有草稿档先出草稿、没有就先出低清，草稿整集经用户点头后才出成片，草稿与成片尽量同一通道；用户限定单次或失败不重试时让路，把额度用于已批准的实际规格；不得额外生成低档样片、付费静态参考或身份重训，也不把「最高风险先测」「多 take 择优」当作扩大授权的理由。
- 报价超出已授权支出时，在普通聊天中一次说清具体档位、费用和已知重大风险，询问精确新增授权；交互表单只是辅助。清楚的普通回复可作授权，超时未答不是同意；价格和范围未变时不重复询问已有有效授权。不要把催交付理解成新增扣费许可，也不要把禁止重复提交扩成永久禁止任何获准新 take。
- 用户要求原生动作/角色参考时，不擅自改成 FaceFusion、抠像合成或另一 provider；用户已否决的模型或方法，不以修复为名继续沿用。复用可恢复的原片和已批准资产，不要求重新上传或重复生成；任何备选路线仍服从原授权边界。
- 用户选定附件并要求局部修改时，以该附件为底图，只改指定特征；不要重新选角或偷偷换成最新候选。更新当前批准版本和冲突的旧 negative，不让旧拒收状态阻塞后来明确选定的方向。用户接受墨镜等遮挡时按新外观合同验收，但不把遮挡当作精确身份已通过的证据。
- 需要用户验图时，先把实际生成图片作为可见附件交付并标清模型，再问是否认可；打开预览窗、工具内部看图或写入 delivered 都不等于已经发给用户。用户说没看到时重发已有文件，不重新生成，也不在看不到图片时继续索要认可。模型对比保持可支持的共同 prompt、角色参考、构图与自动改写设置一致，逐张展示原图；原生差异如实标注，不替用户选定。
- 用户要成片时，NBP 是内部执行合同，首要交付是实际可播放文件与简短验收结论，不是 JSON、提示词、价格预检、准备好的表单或后台日志。只能把通过对应验收的文件标为终稿；有真阻塞就给一次明确决策，不用连续状态说明代替结果。终态拒收后立即同步报告、看板与防重状态：分别写清生成已结束、验收拒收、原交付未完成，并保留已消耗的单次授权；不留在旧的「待授权/验收中」状态。给用户短而直接的失败结论，诊断片明确标非终稿；整理内部记录不能替代这次实质答复。
