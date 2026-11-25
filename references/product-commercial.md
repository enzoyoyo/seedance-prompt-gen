# Product and Commercial AI Video

## 先选商业任务

不要把所有产品片写成 15 秒一镜到底形变链。先选最符合目标的 lane：

| Lane | 核心结构 | 关键 QC |
|---|---|---|
| Product hero | 产品可读 → 使用 → 单一功能证明 → macro → hero hold | 产品始终正确 |
| UGC recommendation | 人物 hook → 问题/使用 → 证明 → 口语收束 | 像朋友分享，不像品牌演讲 |
| Unboxing | 包装到达 → 触感打开 → 产品 reveal → 细节 → 初次反应 | 包装和产品都清楚 |
| Review/tutorial | 主张/问题 → 可见测试/步骤 → 证据/限制 → 结论 | 证据可见，不只说 |
| Before/after | before → 产品介入 → after hold | 机位、光线、比例一致 |
| ASMR | tactile macro → 材质/声音 → 最小剧情 | 真实表面优先 |
| Minimal loop | 干净背景 → 温和旋转/弧线 → 匹配首尾 | 可循环，无多余物 |
| Hyper Motion | 产品轮廓 → 可追踪变化 → 重新组装 → hero | 炫技不遮产品 |
| TV Spot | 情境/情绪 → 产品作为转折 → payoff → 品牌收束 | 产品与故事有因果 |
| App/UI journey | persona pain → 输入/扫描 → 结果 → 现实动作 → payoff | UI 作为锁定帧 |
| Source VFX | 实拍底片 → effect-only delta | 不重拍产品/背景 |

产品动作可作为声场切换的因果开关：在可见接触或启用瞬间压低外界噪声并进入主观音乐或内部声场，让功能收益被直接听见；切换必须由画面触发，且不能牺牲关键对白可懂度。

## Product Lock

实体产品每个 Prompt 都要从同一锁定记录继承：

```text
使用批准的产品源图；保持外形、比例、材质、颜色、标签/Logo 位置、开口/把手/边角和关键表面细节；不得重设计，不新增 SKU，不改变尺度。
```

下游镜头如果需要 orbit、侧面或 macro，产品源图必须先证明那些角度。只有正面图不能支持“360 度完全一致”的承诺。

## Brand kit 与资产

批量广告前锁：logo、色板、字体方向、产品线、包装、UI 和 campaign visual language。生成模型不负责精确品牌字、价格、CTA、法律声明或中文 UI；后期叠加。

## UGC 测试矩阵

每轮只变一个轴：avatar/persona、opening hook、setting、SKU、proof line。产品参考、品牌 kit 与核心 claim 保持不变；按待比较假设、预算和差异可辨性生成最小充分的短变体，不设固定数量，也不能凭一个长片判断格式。

## App/UI

- 锁定 landing/input/result 三类静态 UI；
- 声明 UI 是不可重绘的 still/reference；
- 精确文字在后期；
- 可选结构：人物痛点 → 输入/扫描 → 结果 → 现实行为 → payoff；
- 或 phone/UI → 穿入 screen → 数据/物体转化 → 结果 → 回到 UI。

## Motion graphics / Logo reveal 专用 Lane

只有用户明确需要连续形变、中心构图、motion design 时启用：

1. 从真正参与转化叙事且彼此可辨的产品 trait 映射最小充分视觉状态，不为数量凑 trait；
2. 每个新状态从前一状态可见形变，不凭空出现；
3. 产品/Logo 可读性需要时可锁定或极轻推；若转化概念依赖其他相容机位行为，则以代表镜证明几何和识别度；
4. reveal 前留短 hold；
5. 最终 hero/Logo 帧清楚、可后期替换精确字标。

六段/15 秒/12–13 秒 hold 是一种可缩放模板，不是平台永久规则。按 live duration 和真实节奏缩放。

## 产品变换与成对剪辑

涉及产品变身、成对视觉替身或动作接品牌图形时，读 [commercial-match-cut.md](commercial-match-cut.md)：把产品介入写成可见因果，逐区域记录变换进度；扩展细节镜只覆盖同一次事件，不让完成态无故退回初态。成对版本先定义剪点锚点、画面方向与动作相位，再各写主体物理；品牌图形收尾由已验收姿态衔接确定性后期。它是条件化方法，不把广告都改成变身片，也不照搬案例的固定镜数、时长或运镜。

## 产品失败诊断

按最早真源修：

1. silhouette/label/material → product master；
2. persona drift → avatar/character source；
3. UI corruption → locked UI frame；
4. 源正确但动作/镜头错 → motion direction；
5. offer/message 错 → brief。

对已批准 master 做局部编辑并版本化，不叠加整帧反复重绘。

## 长广告

超过可靠单段时长，按叙事转折拆 Part 1/2/3，复用同一 Product Lock、参考职责和风格基底。每段末尾提供稳定 handoff；最终在后期拼接。

## 输出包

```text
business objective
ad archetype
audience/platform/ratio intent
brand kit + product locks
reference-role table
beat map / shot list
prompt(s)
first/end/hero frame prompt(s)
post copy/CTA/legal plan
provider live-check items
QC checklist
```

Higgsfield Marketing Studio mode slug、分辨率、时长等只由 `higgsfield-generate` live discovery 决定。
