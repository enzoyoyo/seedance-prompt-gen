# 逐镜恢复与重拍

多镜项目在中断恢复、重拍或接受实际剧情偏差时读取。只要文本或单镜、没有下游继承时不建立这套台账。既有 [continuity-ledger](../templates/continuity-ledger.md) 仍记录故事与物理状态，[shot-selects](../templates/shot-selects.json) 仍记录选片；恢复表只回答当前任务该从哪里继续。

## 最小恢复包

保留当前 brief / 剧本 / shotlist 路径与版本、当前资产 manifest、已选 take 与真实末态、任务 ID、失败原因和下一步。用这些已确认的文件续接，不传整段聊天历史，不把凭据写进交接。

从 [resume-manifest.json](../templates/resume-manifest.json) 复制需要的镜头条目，沿用 `shot_id` 和 `source_take`；planned 示例不是已生成素材。每镜记录修订号、阶段、状态，发生过 provider 提交的才填 provider、exact model 与 job ID。不得用提示词、目标时长或文件名冒充任务成功。

填表合同：`submitted` 表示是否真实提交过；实际生成任务必须有 `provider / exact_model_id / job_id`。`stage` 使用 `planning / execution / qc`，`state` 使用下表对应的机器状态。已验收状态 `accepted / accept_with_deviation` 必须有 `source_take / qc_record / observed_end_state`；这些字段只是证据指针和人工结论，检查器不验证文件内容。确认失败时，`failure` 写 `kind / reason / terminal_confirmed / retry_eligible`，`changed_variables` 写本次准备改变的字段。

## Take 台账与判废隔离

镜头记录「做到哪一段」，`takes[]` 记录「哪一条 take 被判废、为什么、替代者是谁」。只在同一镜产生过多条 take 时建这张表；单条通过的镜头不建。

| 字段 | 写什么 |
|---|---|
| `take_id` | 全 manifest 唯一的 take 标识；`edit_list` 与 `source_take` 都引用它 |
| `shot_id` | 所属镜号，必须在 `shots[]` 中存在 |
| `status` | `candidate`（已下载待审）/ `approved`（通过 QC，可进剪辑）/ `rejected`（判废） |
| `reject_reason` | `status=rejected` 时必填，写可见失败而不是「不行」 |
| `supersedes` | 本条替代的旧 `take_id`；无替代关系写 `null` |
| `file_sha256` | 实际文件摘要，64 位十六进制；未算写 `null` |
| `requested_model` | 提交时点名的 exact model id |
| `reported_model` | 回执里实际执行的 model id |

判废 take 记 `status: rejected` 并禁止进入剪辑表：`rejected` 的 `take_id` 不得出现在 `edit_list`，也不得作为任何 `source_take` 或父镜快照的 `source_take` 被续接。同一 `shot_id` 至多一个 `approved`；要换选就先把旧条改成 `rejected` 并写 `reject_reason`，再让新条 `supersedes` 它。`requested_model` 与 `reported_model` 不一致时检查器报 `MODEL_DOWNGRADED` 警告、不改退出码；这条只说明本 take 由哪个模型实际生成，画质基准按实际模型重新核，不按点名模型宣称。

有后继继承时，父镜链接同时保存当时选用的 take、修订号与已观察末态。换 take、重新验收或接受新的末态后更新父镜修订号，先查依赖链再续拍。恢复检查读取快照，不能根据自然语言推断两条状态是否等价。

### 提交时落账（AI 短剧）

短剧项目的 `takes[]` 由 `scripts/ledger_submit.py` 在提交当时写入，不事后补记。在上表之外每条 take 还带：`spec_id`（规格里的条目）、`tier`（`draft`／`lowres`／`final`）、`job_state`（`preparing` → `submitted` → `succeeded`／`failed`，说不清就是 `unknown`）、`job_ids`（通道返回的全部任务 ID）、`origin`（`generated`／`reused`）、`prepared_at`／`submitted_at`／`settled_at`、`duration_s`、`cost`、`changed_variables`、`acceptance`（四项验收及证据）。

- `preparing` 或 `unknown` 的 take 会挡住同镜同档的再次提交：先按 ID 或通道历史查回，再 `settle`。没拿到 ID 的那条，镜头行的 `job_id` 写成 `UNRECOVERED:<take_id>` 占位，表示「可能已扣费、ID 待找回」，不是未提交。
- 盘点：`python3 scripts/validate_resume_manifest.py --input <清单> --clips-dir <片段目录>`。片段目录里任何一个视频文件在台账里没有记录（`CLIP_WITHOUT_LEDGER_RECORD`），或记录既无任务 ID 又不是声明的复用（`CLIP_RECORD_WITHOUT_JOB_ID`），都不通过。
- 成片档 take 出现在台账里而草稿整集未获用户确认（也没有「只出一次」记录），清单校验不通过。

## 状态决定下一步

| 现场状态 | 下一步 |
|---|---|
| 已通过 `accepted / accept_with_deviation` 且依赖未变化 | 保留当前 take 与选片区间 |
| 已提交 `submitted`、运行中 `running`、网络超时或终态未知 `unknown` | 按已有 job ID 回读；没有 ID 时先核对账号任务列表，不能自动重提 |
| 生成完成但未审片 `succeeded` | 下载、解码、回放并填真实末态 |
| 已确认失败 `failed`、已拒绝 `rejected` 或待修 `repair` | 记录失败层与拟改变的一个变量，准备新 take；先确认旧任务终态与既有授权 |
| 父镜被拒绝、替换或末态有变 | 标记依赖镜待重排，沿依赖链重查；无关成功镜继续保留 |
| 新镜只完成规划 `planned` | 补齐当前缺的资产、连续性和 live preflight，再决定执行 |

这些动作是计划，不自动上传、删除、重试或付款。通过表结构检查也不代表模型参数、资产、成片或发布已验收。

用户已确认镜头通过，但尚未提供 take 或 QC 记录路径时，保留这个用户结论，先补回证据指针；不要捏造路径让检查变绿。此时 `needs_replan` 也可能只是记录不全，不能解释为必须重拍该成功镜。运行中的任务即使依赖已失效，也先按 `poll_existing_first` 查清终态，再决定新计划。

## 计划末态与实际末态

剧本计划与通过回放确认的实际结果分栏保留。生成把下一镜的动作提前完成时，先决定该偏差是否仍满足故事：拒绝则修当前镜；接受则更新 `completed_beats`、真实末态与后继计划。不能嘴上接受偏差，后续仍照旧剧本再演一遍。`accept_with_deviation` 只接受仍满足批准 brief 的可控变化；不能把逃亡改成跟随、把道具形变写成剧情设定，或把动态结尾缺失写成已批准静帧方案。若需改变核心承诺，保留原计划并取得改案授权后重排；像素/因果硬伤仍回最早失败层修复。

父镜为 `accept_with_deviation` 时，后继的 `parents[]` 条目须在完成重排后写 `deviation_reviewed=true`，并同步其 `source_take / revision / observed_end_state`；只改这个布尔值不能消除过期快照或重复剧情事件。

`reserved_beats` 表示留给后续的动作；若已在成片发生，不能继续保留为尚未发生。`advances_beats` 只记录新推进，不能与继承链已经完成的事件重复。同一 story time 的 coverage 可以重复表现同一事件，使用 `source_beats` 指向原事件并留空新的推进，不能为了通过检查另编事件编号。

只有已通过 QC、已登记真实末态的 take 能作为执行续镜的父节点。当前镜被拒绝、待修、只有生成成功或只有“看起来完成”的文字结论时，不把它交给后继。若改变空间、时间或机位意图，明确采用 `editorial_cut` 及对应桥接；连续接力才从真实末态延续，不强制所有镜头做视频延长。

## 宿主中断

轮次上限、额度耗尽、上下文压缩都会在没有告警的情况下结束当前会话。先写 manifest 再停：把已完成镜的 `state / source_take / observed_end_state`、`takes[]` 的当前 `status` 与 `edit_list` 落盘，再做别的动作；不要把「已批准哪条 take」只留在对话里。

- 轮次或额度接近上限时先写盘，再决定是否继续提交；没有额度就停在 `planned`，不要用降级模型补完。
- 上下文被压缩后回到本任务，只从 manifest 与资产清单重建状态，不从被压缩的摘要里回忆已批准 take。
- 同一会话中途加载过其它 Skill 再回到本 Skill，重述当前作品的资产与已批准 take，不沿用另一 Skill 的风格结论。
- 恢复后第一步是核对 `takes[]`：`rejected` 条目仍是 `rejected`，不因为「记不清了」重新取用。

## 运行检查

```bash
python3 scripts/validate_resume_manifest.py --input /path/to/resume-manifest.json --json
```

结果按镜给出恢复动作，检查身份唯一、父镜是否存在、依赖循环、父镜快照变化、必要任务身份、显式剧情事件的重复推进，以及 take 台账：`rejected` 是否进了 `edit_list` 或续接输入、同镜是否出现两个 `approved`、`reject_reason` 是否缺失、`supersedes` 是否指向不存在的 take。非法结构返回非零；修完结构后仍需按报告处理待重排与待核状态。它不调用 provider，不读取媒体像素，不验证自然语言因果，也不替代 [production-qc](production-qc.md) 的实际回放。

## 来源与取舍

独立实现自 Emily 的[项目状态](https://github.com/Emily2040/seedance-2.0/blob/d2b529947a43880e2b8b9a411c8a154f024d3dc9/references/sequence-project-state.md)、[续镜交接](https://github.com/Emily2040/seedance-2.0/blob/d2b529947a43880e2b8b9a411c8a154f024d3dc9/references/continuation-handoff.md)和[重拍协议](https://github.com/Emily2040/seedance-2.0/blob/d2b529947a43880e2b8b9a411c8a154f024d3dc9/references/retake-protocol.md)中的状态与依赖思路。源剧本修改范围结合 shuohao 的[节拍认领](https://github.com/eternityspring/shuohao-skills/blob/4322897e6d2bdaf66365534fd40194360c75a85f/skills/novel-storyboard/SKILL.md#L46-L55)。只吸收可验证行为，不导入上游整套 schema、固定时长、工具调用或未核模型能力。
