# 连续性台账 Continuity Ledger — `<project_id>`

## 模式与真源

- 复杂度模式：`light / light-bible / full-bible`
- 当前剧本 / shotlist 版本：
- 角色圣经版本：
- 场景圣经版本：
- 视觉风格圣经版本：
- 真源规则：故事/人物状态来自批准剧本与本台账；物理状态来自 approved 资产与真实通过 QC 的末态。二者不得互相静默改写。

## 角色场景状态（条件表）

无角色、群众/一次性背影或不需要主观状态的项目可删除整表。只记本场相关或改变的字段；未知保留 `unknown`，不得自动补全。

| Scene / Beat | Character | `knows` | `believes` | `wants` | `relation_power(target)` | `body_state` | `scene_event` | `state_out` |
|---|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |  |

客观真相、观众信息与角色信念分开。Knowledge 写获得来源；power 写具体 target 与方向性筹码/依赖/许可/义务，不用统一数字评分。

`body_state` 只记本场可观察的身体处境：伤势、疲惫、醉意、束缚、负重、失声等会限制下一步动作的事实。它属于客观状态，与主观的 `believes / wants` 分开；未知写 `unknown`，本场未改变则不重复抄写。

## 轴线 / 拓扑登记

只有入口、路径、轴线、视线或身体—摄影机几何会影响执行时保留本节；否则删除。地图字段只填当前风险所需的范围，不为“完整”伪造全量拓扑。

| 场景 | 地图资产 | Axis ID | 轴线端点 | 允许机位侧 | 视线规则 | 当前侧 |
|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |

## 镜头台账

先删去本项目不存在的列：无角色不填角色坐标，无道具不填手位，无跨镜继承不填 relay/continuity out。已经声明的身份、状态、空间与物体恒存仍须严格守恒。

| 镜头 | `story_time_id / coverage_group` | 地点 / 时间 | 角色坐标 + 朝向 | 画面方向 / 视线 | 摄影机坐标 + 轴线侧 | 发型 / 服装 | 道具手位 + 状态 | 光线 / 世界状态 | `temporal_relation` | `handoff_strategy` | Continuity in | 计划 out | 真实 QC out / 中继帧 | 状态 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |  | continuous_time / editorial_cut |  |  |  |  | planned |

## 服装 / 发型时间线

| 角色 | 状态资产 ID | 起始镜头 | 触发条件 | 结束镜头 | 可逆？ | 必须继承状态 |
|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |

## 道具时间线

| Prop ID | 所有者 | 镜头 | 手位 / 坐标 / 朝向 | 变化前 | 可见变化 | 变化后 | 必须持续至 |
|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |

## 持续环境状态

| State ID | 场景坐标 | 变化镜头 | 结果地标 | 必须继承的镜头 | 重置 / variant 条件 |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

## 连续性缺陷记录

| Finding ID | 镜头 | 类型 | 发现机制 | 证据 | 最早需修真源 | 处理 | 复测 |
|---|---|---|---|---|---|---|---|
|  |  | identity drift / spatial mismatch / action jump / missing prop / light break |  |  |  |  | pending |

## 编译前门禁

- [ ] 所有引用均为当前 `approved` 版本。
- [ ] 适用时，角色只依据当前 `knows / believes` 行动；knowledge 更新有可见/可听来源。
- [ ] 适用时，`relation_power(target)` 的变化有 `scene_event`，方向与 target 明确。
- [ ] 已声明的身份、阵容比例和完整态 / 战损态匹配本镜。
- [ ] 已声明的坐标、画面方向、轴线侧和视线守恒。
- [ ] 已声明的发型、服装、左右手道具与持续世界状态已继承。
- [ ] 适用时，主光、阴影、时段和天气变化都有可见原因。
- [ ] covered-scene 的重叠 take 共用 story time / coverage group，未把同一事件重复推进。
- [ ] 有相邻块时，`continuous_time` 从真实 QC out 继续动作/声场且不重复已完成动作；`editorial_cut` 只写实际采用的动作、视线、屏幕方向、遮挡、cutaway、构图或声音桥策略。
- [ ] 需要 relay frame 时，它来自通过 take，且没有身份、手部、嘴型、模糊或遮挡缺陷；editorial cut 不强制 relay frame。
