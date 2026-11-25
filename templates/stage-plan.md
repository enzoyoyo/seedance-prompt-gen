# AI 视频 / 短剧制作看板

按作品形式与用户要求删减行；无关字段直接删除，不写虚构的 N/A。它是薄看板，不是固定阶段、审批门或 12 张能力卡的填空表。用户只要剧本时，保留 Brief、`title` 与 `tension_gate`、Scene/Beat truth 与适用的角色状态，删除 provider、生成和发布行。

## Brief / selected form

- 请求交付物：
- `selected_form`：
- 观看承诺 `viewer_promise`：
- 最早续看理由 `continuation_reason`：
- 标题 `title`（选 1 备 2，来自 ≥5 候选）：
- 张力门 `tension_gate`（想要／阻力／代价／升级／转折／钩子／结尾／标题各一句 + 引用证据）：
- 目标平台 / 画幅 / 已知限制（仅在相关时）：
- lane-specific gate（仅在已选择相应 Lane 时）：

## Scene / beat truth

| Scene / Beat | `story_state_in` | `scene_event`（可选） | `obstacle` | `stake` | `escalation_or_turn` | `acting_task_by_character`（可选） | `story_state_out` / aftereffect |
|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |

`scene_event` 只记录实际改变可能性、知情、关系、目标、物理或感知状态的事件。`acting_task` 只记录角色此刻可演的策略；无人物、观察、氛围、非线性或纯视觉内容可删除相应列，以自己的空间、感官、节奏或解释变化验收。`stake` 全片不得为空；观察／氛围形式可以是时间、体面、安全或模式将破，但要写出谁在承受。

## Character scene state（条件表）

| Scene / Beat | Character | `knows` | `believes` | `wants` | `relation_power(target)` | Trigger / changed fields |
|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |

只填本场相关或改变的字段；未知保留 `unknown`，不得补写小说式背景。客观真相、观众信息与角色信念分开。

## Production board（按需删行）

| 工艺块 | 输入 | 决策 / 产出 | 验收证据 |
|---|---|---|---|
| 分批资产解锁 | 当前集真实需求 + 后续集计划 | 首批只解锁当前集必要资产；后续随剧情确认扩产 | 当前集无缺口，未提前堆积无用资产 |
| 最小充分资产 | 下游镜头 + 复用/漂移风险 | 身份/服装/道具/地点的 `required_views` 与 approved IDs | 每个所需视图像素可读；无固定 Sheet/panel 仪式 |
| 空间预演（条件） | 站位、路径、视线、轴线歧义 | 二维位置图；仅几何改变执行时升级 blocking/3D | 更复杂表示确实减少歧义，否则降级 |
| Generation routing | scene truth + 风险 | `block_mode + rationale + temporal_relation + fallback` | 时长/机位数没有替代导演理由 |
| Input preflight | exact model + 引用职责 | `primary_input_mode + allowed_secondary_inputs + incompatible_modes + live_evidence` | 未核兼容写 `TODO_VERIFY_LIVE`，不得直接提交 |
| Prompt 包 | approved assets + shot contract | 可见 `acting_task/scene_event`、表演与物理因果、机位、稳定末态 | 参考职责不打架；情绪已转为可见策略/响应 |
| 最难代表镜 probe | 全片身份/空间/接触/表演风险 | 最能证伪路线的一镜 + failure class | 通过后才扩产；失败只改最近根因 |
| 生成 | 当前唯一 adapter + live contract | 本地片段 + job log | 下载、完整 decode、逐镜观看 |
| Best-take selects | 全部候选 take | `select/reject + reason + usable_in/out` | 完整运动、画面-only、音频-only、音画合看、小屏复核 |
| 声画后期 | selects + 剧本 | 对白/SFX/BGM/字幕/`post_insert` | 听清、卡点、精确文字可读、状态桥相符 |
| 成片导出 | 选定媒体 | `renders/final.mp4` | 完整 decode + 全片回放 |
| 平台分轨 / 发布 | 母版 + 当日官方规则 | 平台切片、文案、披露、链接/状态 | 承诺与所得未拆散；发布事实可核验 |

## Stop / repair points

- 张力门任一行无引用证据，或 `stake` 全片为空：先修剧本，不进入分镜、资产或 Prompt。
- form、观看承诺或 `story_state_in/out` 仍不可读：先修当前创作层，不锁重资产。
- 角色提前使用未获知事实，或 relation power 无事件便变化：先修 state ledger。
- required view、空间或代表镜未通过：停在最早真源，不批量生成。
- live schema、模式兼容、额度或权限未核：不付费提交。
- `continuous_time` 没有真实 QC 末态，或 `editorial_cut` 没有事实/动作/视线/声音桥：不编译下一段。
- “成片”没有本地可播放文件、完整回放和 selects 证据：不称完成或进入发布。
