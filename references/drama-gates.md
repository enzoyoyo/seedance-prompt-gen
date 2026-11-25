# AI 短剧制作门

只管「AI 短剧从接单到交付成片」这一条线；口播、代码视频、单张图不走这里。门只查不变量，不规定镜头数、时长、节拍结构、题材结构、提示词句式、字幕或音乐风格。

## 入口

进项目先跑，做完每一步再跑：

```bash
python3 scripts/drama_next.py <项目目录>
```

输出四样：`gate`（卡在哪道门）、`next`（现在唯一允许做的事）、`command`（对应命令）、`read`（这一步该读的 reference）。它只读，不写清单、不提交、不联网。空目录也能跑，从接单门开始。输出与自己的判断不一致时，以输出为准；觉得门错了就报给用户，不绕过。

## 门序

| 门 | 通过条件 | 记录它的命令 |
|---|---|---|
| 接单 | 需求用用户原话记进清单 | `drama_setup.py init`、`intake` |
| 剧本锁定 | 剧本带 beat 编号，`script.lock.json` 的摘要与文件逐字节一致，带用户确认原话 | `lock_script.py` |
| 发布意图 | 见下「发布意图」，全项齐，敏感词命中逐条有用户决定，可选 `lexicon` 专名锁通过 | `drama_setup.py release-intent` |
| 白模与站位预演 | 锁定剧本 beat 中出现的每个场景都在 `00_previs/` 有带旁路 `.blocking.json` 的选定站位板（或经带码决定逐场 `--waive-scene`／整集 `--waive`）；先 `present --gate previs` 出带码决策图交用户看，再凭用户回复中的确认码落锁 | `render_whitemodel_board.py`、`drama_setup.py present`、`previs` |
| 角色多角度与场景资产 | 按选定白模板旁路推导的各角色 `required_views`（`front` + 机位拍到的角度；豁免白模或无旁路工具退回 `front`+至少一非正面；板上非 `"extra": true` 演员 id 必须与身份角色一致）及主要场景空场主景板（`--scene-ref`）先 `present --gate identity`，再凭确认码落锁 | `drama_setup.py present`、`identity` |
| 镜头规格通过 | 见 `shot-spec.md` | `validate_shot_spec.py` |
| 试价 | 该通道该档位的第一条提交是待拍镜头里最短的一条，且已结算；`real_public_figures=true` 时该条已结算成功的同通道 take（`ref_sha256s` 匹配当前锁定角色身份图）兼作零额外花费的肖像风控探针（重锁身份后旧探针自动失效，探针失败阻断同通道批量） | `ledger_submit.py submit` |
| 草稿批次 | 余额已凭回读输出文件（`--readback-file`）记录摘要且覆盖剩余镜头估算；同通道任一 take 失败或 `unknown` 后须有时间更晚的余额回读；`balance_query=false` 或 `plan_required`／`daily_limit` 为 `unknown` 时须有用户的继续原话；数字 `daily_limit` 达当日上限即阻断 | `ledger_submit.py balance` / `confirm --kind unknown-cost` |
| 逐镜验收 | 每个镜头有一条四项验收全过的 `approved` take（`identity` 与 `continuity` 均须附绑定该 take 摘要的对比图文件） | `ledger_submit.py accept` |
| 草稿整集 | 只用 `approved` 的草稿 take 拼出整集（支持 `--prefix` 先拼分幕粗剪） | `assemble_cut.py` |
| 你点头 | 用户看过草稿整集，用原话确认 | `ledger_submit.py confirm --kind draft-cut` |
| 成片 | 成片档逐镜提交并逐镜验收通过 | `ledger_submit.py submit --tier final` |
| 后期 | 拼接（可选 `--fade-ms` 防爆音、`--check-seams` 切点黑场／冻帧门禁）、配乐、字幕按用户要求做完并登记产物：每个产物须经 `ffprobe` 解码出视频流与帧且音画流时长差 `≤ 0.25s`（否则报 `POST_OUTPUT_AV_DURATION_MISMATCH`）；`native_bgm=false` 且含音轨时须有匹配 `output_sha256` 的 `.remix.json` 旁路证据（或显式 `--waive-remix`） | `drama_setup.py post-done` |
| 交付 | 平台披露问题用户已答；只加用户要的标识 | `drama_setup.py deliver` |

用户说「只出一次」时：`ledger_submit.py confirm --kind one-shot --tier <档位> --user-words "<原话>"`，试价、草稿整集、你点头三道门让路，直接按该档位提交；此后别的档位一律拒绝。

## 项目清单

一个项目一个 `resume-manifest.json`（沿用 `sequence-resume.md` 的清单与 `takes[]`），短剧专属状态都在顶层 `drama` 块：`script`、`shot_spec`、`clips_dir`、`translations`（路径）；`intake`；`release_intent`；`previs`（`00_previs/` 每场选定站位板或 `waived_scenes`，附已消费 `decision` 审计记录）；`identity_assets`（`characters` 多角度视图、`scenes` 主景空场板、`likeness_preflight`，附 `decision`）；`presentations`（待决展示与加盐哈希，确认码永不明文落盘）与 `presentation_log`；`impacts`（重选门后的受影响镜头与 take 台账）；`channels`（通道能力卡，见 `provider-execution.md`）；`budget`（`one_shot`、`balances`、`unknown_cost_confirmations`）；`approvals.draft_cut`；`cuts`；`act_cuts`（分幕粗剪）；`post`；`delivery`。清单只经脚本写，不手改。

## 展示 → 带码决定与改动影响

`previs` 与 `identity` 两道门先展示、后决定：

1. 备好候选文件后运行 `python3 scripts/drama_setup.py present --project <目录> --gate previs|identity --candidate <组>/<标签>=<文件> …`，在 `00_previs/` 生成带「组 / 标签」、跳过选项与右上角随机短确认码的决策图（一道门一次展示共用一个码，候选多时自动分页）；标准输出与清单都不含明文确认码，连续输错若干次后该次展示自动作废须重跑 `present`。
2. 执行 Agent 把生成的决策图文件发给用户看，**立刻停止等待回复**。确认码只属于用户本人，Agent 严禁从图片读取、转述或代填确认码；该机制是防模型随手代填 `--user-words` 的工程摩擦，不是密码学证明。
3. 用户回复所选标签与确认码后，运行 `drama_setup.py previs` 或 `identity`（所选文件须在已展示候选内且摘要未变，`--waive`／`--waive-scene`／`--waive-multi-angle`／`--waive-scenes` 同样须经 `present` 并带码）。
4. 中途重选某场白模或替换某张身份／场景图时，脚本不自动作废已有素材，而是在返回 JSON 与 `drama.impacts` 中列出受影响的镜头与已有 take，并由 `drama_next.py` 在 `note` 持续提示，直到用户拍板后用 `drama_setup.py impact --project <目录> --id <impact_id> --decision keep|redo --user-words "<用户原话>"` 结案（保留／重拍决定不需确认码，但必须是用户本人原话）。

## 付费提交只走一个口

```bash
python3 scripts/ledger_submit.py submit --project <目录> --shot <镜号> --tier draft|lowres|final \
  --id-field <适配器会打印的任务ID字段> [--dry-run] -- <适配器命令…>
```

- 适配器命令不自己拼：照通道能力卡 `recipe` 指向的配方抄（小云雀 `adapter-xyq.md`、Lovart `lovart-execution-notes.md` 的「短剧提交配方」）；`drama_next.py` 在试价与草稿批次门会指出来。卡上没有 `recipe` 的新通道，先在它的适配器说明里按同样格式写一份配方再提交。
- 占位符由规格展开：`{prompt}` `{duration}` `{ratio}` `{model}` `{shot_id}` `{tier}` `{refs}` `{refs:--flag}`（本地路径）、`{ref_urls}` `{ref_urls:--flag}`（规格 `refs` 里登记的上传后 URL）、`{draft:<ID字段>}`（取该镜已通过草稿的任务 ID，用于草稿升级）。
- 先 `--dry-run`：只跑门、只打印将执行的命令，不写台账、不执行。
- 真提交：门过 → 台账先写一条 `preparing` → 执行适配器 → 从输出里取 ID 写成 `submitted`。若非超时退出、输出里没有 ID 且命中余额／积分不足特征词，直接结算为 `failed`（`reason: "PRE_SUBMIT_INSUFFICIENT_BALANCE"`，`retry_eligible: true`，退出码 1），充值回读余额后同镜同档可直接重提；其余超时、非零退出或输出里没有 ID 一律记 `unknown`（退出码 2），之后该镜该档位拒绝再提交，直到按 ID 或通道自己的历史查回并 `settle`。
- 同镜同档已有在途或成功的 take：直接跳过，不重复花钱。
- `settle` 记结果（文件、时长、实际扣费、回执模型）；失败必须是回读确认的终态（`--terminal-confirmed`），没确认就仍是 `unknown`。
- 退出码：0 通过／已跳过，1 被门拒绝，2 结果未知，3 输入错误。

## 发布意图

首条付费提交前必须齐：

- `platforms`：用户点名的发布平台；没定就写空并置 `platform_undecided: true`。
- `aspect_ratio` + `aspect_ratio_source` + `aspect_ratio_reason`：**点了平台，画幅必须由平台推导**（`source: platform`，理由写清依据与核实日期），不得落回默认母版；只有平台未定时才用 `master_default`。镜头规格的 `ratio` 必须与此一致。
- `target_duration_s`、`real_public_figures`、`on_screen_text`、`native_bgm`：如实填布尔值（`target_duration_s` 为正数），用于显式落锁用户决定（如生成阶段是否带原生配乐）。`real_public_figures: true` 时，一句自填的 `--likeness-preflight` 文字不再放行批量：必须有一条已结算且 `succeeded` 的同通道探针 take（即最短试价镜，不额外花钱），其参考图摘要等于当前锁定的该角色身份图；身份图重锁后旧探针失效。
- `sensitive_terms` / `sensitive_decisions`：平台敏感词表由当次核实得到；脚本在对白里命中的每个词，都要有一条用户决定（保留／改词／后期处理）。脚本不替用户改剧本。
- `lexicon`（可选）：生造品牌名／专有名词词表（`canonical` 标准拼写、`forbidden_variants` 禁用变体、`phonetic_hint` 读音提示）；剧本、镜头 `line`、`prompt`、译文表或后期烧录／导出字幕（`burn_chinese_subtitles.py --project`）出现禁用变体即报 `LEXICON_VARIANT_FORBIDDEN`，根治跨镜拼写与 TTS 读音漂移。
- `labels`：`policy` 固定 `user_requested_only`。`requested` 只放用户要求加的标识。平台要求的披露写进 `disclosure_questions` 当面问用户，记 `user_answer`；不自动加，也不自动不加。交付时 `labels_applied` 超出 `requested` 或有问题未答，交付门不过。

## 逐镜验收

每条下载回来的 take 过四项，各带证据，缺一不能 `approved`：

| 项 | 怎么查 | 证据 |
|---|---|---|
| `lines` | `check_spoken_lines.py --project <目录> --take <take_id> --asr-model <本机已有模型>`：转写后与规格台词逐词比，查出没说、说一半、说了别镜的词 | 它写出的报告文件（绑定该文件摘要） |
| `identity` | `make_identity_sheet.py --project <目录> --take <take_id>`：身份参考与首中尾帧并排，写出图像与绑定 `clip_sha256` 的 `.json` 旁路，人看 | 对比图文件（校验存在、非空且旁路绑定该 take 摘要） |
| `beat_action` | 从头看到尾，beat 里写的动作有没有发生 | 一句所见 |
| `continuity` | `make_continuity_sheet.py --project <目录> --take <take_id>`：把上一在用镜 `approved` 尾帧与本镜首中尾帧并排出图并写 `.json` 旁路，核位置、道具、光向与情绪衔接 | 衔接对比图文件（校验绑定该 take 摘要及上一镜尾帧摘要） |

结果只有 `pass` / `deviation` / `fail`。`deviation` 是用户知情接受的偏差，要写清偏在哪。判废必须写可见原因；重拍要在规格里新增一条 `supersedes` 旧镜、且只改一个变量的条目（见 `shot-spec.md`）。拼接脚本只收 `approved`。

## SPEC v2.0：模型门禁、双阶盲审、跨档熔断、全依赖 STALE 与增量 Human Gate #2

新项目（`init` 固定写入 `drama.sop_version: "2.0"`；既有 v1 历史项目保持只读与回归兼容）在 14 道门之上强制合流以下闭环不变量，门名与门序不变；全文见 `harness-guardrails-and-eval.md`：

| 不变量 | 何时拦 | 记录 / 解除它的命令 |
|---|---|---|
| Human Gate #1 模型门禁：图片模型、视频模型、音频方案（含无需音频）、全局规格与交付模式四项由用户原话选定（禁默认/auto/随便） | 首次生图前（`identity` 门）与每次付费提交锁内重验；真实提交缺门禁报 `MODEL_GATE_MISSING`（`--dry-run` 仅警告），已锁门禁与 `shots.json` 模型或画幅不一致一律硬拦；`prompt_only` 禁付费提交 | `model_gate.py render --project <目录>` → STOP & WAIT → `drama_setup.py model-gate` |
| 双阶盲审接入生产入口：提交前锁内过 Pre-Gen 并编译注入命中 L1；验收前强制过 Clean-Room Post-Gen 独立视觉盲审 | Pre-Gen `FAIL` 直接阻断 `ledger_submit.py submit`（含 `--dry-run`）；Post-Gen 缺失、`FAIL`、`SKIPPED`、`INCOMPLETE` 或 `mock` 一律阻断 `ledger_submit.py accept --verdict approved`；Post-Gen `FAIL` 自动将 take 置 `rejected` 并推进自修或跨阶作废 | `eval_harness.py pre-gen` / `eval_harness.py post-gen --project <目录> --take <take_id> --track dual` |
| 双重预算熔断：单镜同档自修重跑 ≤2 轮（`preparing` 锁内预留）；全片跨全档位累计重渲染 ≤ min(5, ⌊30% 活跃生成镜头⌋) | 第 3 轮重跑报 `CIRCUIT_BREAKER_LOCAL_LIMIT`，跨档超上限报 `CIRCUIT_BREAKER_GLOBAL_LIMIT`；`spend_history` 不可冲销（`STALE` 不清零已发生消费）；触发时当场落盘裁决包 | `eval_harness.py escalate` 出人工裁决包，交用户定 |
| 跨阶回退与全依赖 `STALE`：Step 6 查出 Step 2/3/4 根因时沿 `角色/场景 → 白模 → 根镜与修订链 → 在途与历史 takes` 作废 | 作废旧 `presentations` 与旧粗剪批准；未以新资产哈希完成增量带码重签前，`drama_next.py`、`submit`、`confirm`、`assemble_cut.py`、`deliver` 全拦 `INCREMENTAL_HUMAN_GATE_2_REQUIRED`；v2 禁用 `impact keep` 或旧片 `reuse` 洗白强制作废 | `drama_setup.py invalidate --stage <character / scene / previs> --target <id> --reason <根因>` → 修源头与白模 → `present` → 带码重锁新哈希 → 重生成波及镜头 |

清单新增键：`sop_version`、`model_gate`（附 `model_gate_log`）、`spend_history`、`repair_queue`、`stale`（`previs_scenes`、`shots`、`takes`、`pending_gate2`、`resolved_gate2`、`invalidated_shas`）、`asset_loops`（`eval_harness.py asset-round --reserve / --settle`）。

## 接手别人的项目

见 `cross-host-handoff.md`：先 `audit_takeover.py`，再回到本页的门序。
