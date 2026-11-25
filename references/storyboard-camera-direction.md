# AI Film Storyboard, Camera and Physical Direction — 2026-07-23

Use this reference when a narrative AI-video job needs script breakdown,
storyboards, shot-list handoff, camera direction, physical action, continuity
states, or risk-first testing. It is provider-neutral methodology, not a static
Higgsfield product manual.

## Evidence boundary

This increment was distilled from the current official Higgsfield Fresh
Releases and Academy corpus, then deduplicated against the existing local claim
ledger.

| Source | Durable method retained |
|---|---|
| [AI Storyboard Generator: How to Turn Scripts Into Frames](https://higgsfield.ai/blog/script-to-storyboard-ai) | Select boardable sequences; prompt a scene arc rather than one still; use references; choose exploratory versus fixed panel direction; review and label the board. |
| [AI Previsualization Tools for Filmmakers](https://higgsfield.ai/blog/ai-previsualization-tools) | Storyboard, animatic and 3D previs solve different planning risks. |
| [Make AI Short Films With This Exact Workflow](https://higgsfield.ai/blog/case4k) | Named assets, geometry sketches, screen-direction and outcome locks, state-specific reference sheets, reverse-angle continuity and edit-ready iteration. |
| [How to Avoid Distortions in AI Videos](https://higgsfield.ai/blog/how-to-avoid-distortions-ai-videos) | Diagnose face/background/motion separately, use single-direction moves, define action endpoints and test the highest-risk shot first. |
| [How to Make AI People Move Realistically](https://higgsfield.ai/blog/realistic-ai-human-movement) | Describe force and body response, split complex motion into physical beats and use explicit state contrast. |
| [WAN Camera Control](https://higgsfield.ai/academy/how-to-use/turn-your-video-into-cinema-using-wan-camera-control) | Camera motion carries meaning; one purposeful primary move per shot; validate movement before final resolution. |
| [Prompt like a director](https://higgsfield.ai/academy/courses/cinema-studio-complete-tour/prompt-like-a-director) | Keep subject, setting, light and camera decisions separate from model, ratio, resolution, batch and duration controls. |
| [Cinematic AI short film](https://higgsfield.ai/academy/how-to-use/how-to-make-a-cinematic-ai-short-film) | Approve character, location and prop sheets before animation; use camera language that could be handed to a cinematographer. |

Local source IDs:

```text
blog:script-to-storyboard-ai
blog:ai-previsualization-tools
blog:case4k
blog:how-to-avoid-distortions-ai-videos
blog:realistic-ai-human-movement
academy:how-to-use:turn-your-video-into-cinema-using-wan-camera-control
academy:courses:cinema-studio-complete-tour:prompt-like-a-director
academy:how-to-use:how-to-make-a-cinematic-ai-short-film
```

The normalized local map captured on 2026-07-23 contains 681 current records:
56 Academy, 259 Blog, 121 product/workflow documents, 230 YouTube videos and 15
Community posts. The curated ledger contains 87 semantic claims.

## Stability boundary

### Durable

- choosing the minimum sufficient previs layer;
- selecting decision-critical scenes for storyboarding;
- sequence briefs, panel metadata and shot-list handoffs;
- choosing the smallest coherent camera trajectory that serves the shot, with compatible staged moves allowed when geometry and representative tests support them;
- camera placement/path/speed/focus/narrative-job grammar;
- physical action chains and explicit state transitions;
- state-specific continuity references;
- screen-direction, causal-order and final-state locks;
- risk-first testing and source-first diagnosis.

### Provider adapter — verify before use

- exact reference syntax and media-role fields;
- product mode names such as Auto or Manual;
- frame and reference-image limits;
- built-in lens, light, movement or identity controls;
- first/end-frame and context-video behavior.

### Volatile or rejected as method

- model IDs, UI click paths, prices, credits, entitlements and rankings;
- fixed resolution, duration, batch, frame-count or audio guarantees;
- “viral”, “unlimited”, “best” or revenue claims;
- treating 4K as a universal cure for weak blocking, references or motion.

## End-to-end production path

```text
story premise and audience effect
→ script and visible beat map
→ choose previs fidelity by decision risk
→ board decision-critical sequences
→ approve references and storyboard panels
→ compile numbered shot list with continuity states
→ test the highest-risk shot
→ generate approved shots with one controlled retry variable
→ select takes, assemble, sound and QC
```

Do not jump from a paragraph of story directly to a giant generation prompt.
Each applicable handoff above should leave enough inspectable evidence for its downstream decision; omit stages and artifacts that carry no real execution risk.

## 1. Choose the minimum sufficient previs

| Planning question | Minimum useful artifact | Upgrade when |
|---|---|---|
| What is in frame, where is everyone, where does light come from? | storyboard | timing or moving geography is still ambiguous |
| When do actions, cuts and reveals happen? | animatic | a camera/body path must be geometrically feasible |
| Can this camera, subject and environment occupy the required positions? | 3D previs or measured blocking | only when precise geometry changes execution |

The rule is not “3D is better.” The rule is: use the cheapest artifact that
removes the current production uncertainty.

## 2. Select boardable sequences

Do not board every script line or page. Rank scenes by whether a visual decision
must be made before generation:

1. physical action or multi-character interaction;
2. emotional change that requires coverage rather than dialogue alone;
3. a reveal, transformation, transition or visual punchline;
4. specific camera, eyeline or geography requirements;
5. continuity changes in wardrobe, damage, prop ownership or world state;
6. moments whose edit will fail if coverage is missing.

Simple dialogue may need one master and two repeatable singles. A complex action
scene may need several boardable sub-sequences. Split by visible beats, not page
count.

### Sequence brief

```text
sequence_id:
story function:
who is visible:
where it occurs:
visible beats in causal order:
emotional register at start and end:
required character/location/prop/state references:
screen direction or 180-degree axis:
mandatory reveal or outcome:
incoming continuity state:
outgoing continuity state:
```

If this brief cannot state what visibly changes, the scene is not ready to
board.

## 3. Prompt a sequence, not a still

A storyboard prompt describes an arc distributed across panels:

```text
visual register / medium
+ specific subject and current state
+ location and spatial anchors
+ action arc across visible beats
+ atmosphere and motivated light
+ camera or coverage changes that matter
+ continuity and outcome locks
```

References carry information that prose should not repeatedly reinvent:

- character reference → identity, body, wardrobe state;
- location reference → geography, landmarks and light direction;
- prop reference → exact form, scale and current ownership/state;
- blocking sketch → relative positions, paths, impact point and camera side;
- approved prior panel → identity/composition bridge into the next generation.

When multiple storyboard generations share a character or place, use the
strongest approved panel or canonical source as a reference for the next
sequence. Do not trust the repeated text description to recreate the same
identity.

## 4. Match control granularity to story constraints

Use arc-level distribution when:

- exploring possible coverage;
- the order of broad beats matters but exact panel placement does not;
- several valid camera solutions exist.

Use panel-by-panel direction when:

- a reveal or punchline must land on a specific panel;
- an eyeline, reverse angle or screen-direction change is mandatory;
- an incoming/outgoing transition state must match another shot;
- client approval requires a fixed coverage plan.

The durable distinction is `explore` versus `lock`, not a product's current
mode label.

## 5. Approve and hand off the board

Review panels against the scene, not abstract prettiness:

- does the sequence communicate without an oral explanation?
- are identity, wardrobe state, props, geography and light coherent?
- do shot positions and angles provide usable edit coverage?
- does the emotional state visibly change?
- are the incoming and outgoing states measurable?
- is any panel decorative but narratively redundant?

A finished board is navigable. Keep IDs, approval state and the fields that drive the selected previs/shot-list handoff; the rest of this list is a candidate palette and should be deleted when irrelevant:

```text
scene_id / sequence_id / panel_id
approved image/reference path
story function and visible action
shot size and camera side
camera placement and intended movement
estimated duration
dialogue / ambience / SFX cue
location / props / VFX requirements
continuity_in / continuity_out
approval status and notes
```

After board approval, animate the high-risk and story-anchor shots first:
opening, reveal, emotional peak, transformation, complex interaction and final
handoff. Generate connective coverage only after those anchors prove feasible.

## 6. Camera direction grammar

“Tracking shot” is a category, not complete direction. A usable camera clause
contains:

```text
placement:
height and subject distance:
shot size / focal-length effect:
rig or path:
direction relative to subject and screen:
speed curve:
reframe or focus behavior:
start and end composition:
narrative job:
```

Example structure:

```text
Camera begins shoulder-height, 1.5 m ahead of the runner in a medium-wide frame.
A stabilized backward tracking move follows the same screen-right direction,
starting slow and accelerating only after the alarm. Reframe to keep the eyes
on the upper third; rack focus once to the approaching threat. End with the
runner foreground-left and the threat readable behind. Job: turn pursuit into
immediate danger without losing geography.
```

### Smallest coherent camera trajectory

Default to one purposeful path when it carries the shot. An orbit, dolly and
pan may coexist only when they form one motivated, geometrically continuous
trajectory and a representative test proves it readable. Split them when they
compete for attention, create incompatible inertia/geometry or make repair safer.

Micro-motion can support the primary move:

- restrained handheld drift under a tracking path;
- minor operator correction during a locked observation;
- one focus transition tied to a story reveal.

Supporting motion must not become a competing, unexplained path.

### Camera move by narrative job

| Move | Useful story job | Control note |
|---|---|---|
| locked-off | tension, observation, product/source-plate readability | give the subject internal action |
| slow push-in | realization, intimacy, threat closing | name the beat that triggers it |
| pull-back | isolation, aftermath, scale reveal | define what new information enters frame |
| side/lead tracking | travel, pursuit, relationship to environment | lock screen direction and subject distance |
| crane/rise | reveal scale or shift from personal to systemic | define start/end altitude and composition |
| restrained orbit | inspect object or change power relation | protect silhouette and background geometry |
| handheld | urgency or bodily instability | specify amplitude, frequency and whether it settles |
| POV | embodied discovery | lock eye height, blink/focus behavior and frame-edge geometry |

Camera movement should occur because story information changes, not because a
shot appears static.

### Lens versus provider controls

Focal length, field of view, compression, aperture effect and focus behavior
belong to the visible camera decision. Model, ratio, resolution, duration and
batch belong to current provider controls. Never rely on prose to override a
real control, and never hard-code archived enums into this method.

### FOV 度数阶梯与极端焦段防御堡垒

焦段词容易被模型平均；空间关系关键时同时写 FOV、透视效果、相机距离和主体占画面比例。下表是摄影决策近似，不是 provider 参数枚举：

| 水平 FOV | 约等效焦段 | 画面效应 | 适合任务 |
|---:|---:|---|---|
| 8° | 300mm | 极强空间压缩 | 远距观察、让背景逼近人物 |
| 18° | 135mm | 压缩双人距离、浅景深 | 对峙、远摄人像 |
| 29° | 85mm | 稳定面部比例、背景分离 | 情绪特写、单人对白 |
| 47° | 50mm | 接近自然观察、比例中性 | 纪实对话、产品与人物平衡 |
| 84° | 24mm | 强化前后景距离与速度 | 环境交代、狭窄空间、追焦 |
| 114° | 14mm | 边缘拉伸与眩晕 | 只在极端主观/动作意图明确时使用 |

极端焦段启用“防御堡垒”：

1. 写 `LENS/FOV LOCK`，单镜头内不允许无因内部变焦；
2. 景别变化靠真实 dolly/track 位移，不靠数码 zoom 偷换透视；
3. 锁相机起止距离、人物面部离画面边缘的安全空间和最终构图；
4. 先用最高风险构图测试脸、四肢和背景边缘；极端畸变无叙事收益时退回 29°–84° 区间。

### 四档摄影机物理寄存器

| 档位 | 物理证据 | 使用边界 |
|---|---|---|
| Locked Tripod | 重型三脚架、零平移、零人为修正 | 观察、对话、产品/source plate 可读性 |
| Heavy Dolly / Track | 有质量的轨道运动、明确起止距离与加减速 | 推拉揭示；禁止横向漂移 |
| Steadicam / Gimbal | 高频抖动被吸收，转弯仍有向心滞后 | 跟随行走；不能写成无重量飞行 |
| Shoulder / Handheld | 脚步脉冲、呼吸微晃、转向过冲与人工修正 | 纪实/危机；振幅必须与身体动作相称并可落稳 |

手持不是随机数字抖动。需要更强烈时增加操作者速度、负重和地面接触证据，而不是叠加多个 `shake`。

### 手持强度四档与连续运动闭环

这一强度轴与上面的器材/支撑轴并行；先选支撑方式，再选动作强度，不能把“手持”当成唯一档位：

| 强度档 | 可见物理表现 | 节奏边界 |
|---|---|---|
| Locked-off | 重型三脚架般静止，或只有极缓且有明确起止点的推进 | 镜头数量与停留时间由观察任务和剪辑呼吸决定 |
| Gentle handheld | 呼吸起伏、微小有机修正，画面沉淀后再移动 | 以主体可读、运动能落稳为边界 |
| Heavy handheld | 脚步颠簸、明显微调与底层高频震动；视线焦点仍清晰 | 以危机强度、可剪性和观看舒适度校准 |
| Violent handheld | 极端倾斜、快速推拉、甩镜与冲击修正 | 只在叙事失控确需且主体/因果仍可读时使用 |

这些档位是定性设计刻度，不是固定角度、镜头数、时长或 provider 参数；实际强度由题材、观看端、live 能力和代表镜校准。所有非锁定档位都必须写连续运动闭环：真实肩扛质量与呼吸使每帧处在运动中，但位移轨迹自身保持连续、可读、无掉帧撕裂；动作结束时声明继续运动还是物理落稳。

### 漫游覆盖与轴线保护

“漫游”是围绕冻结的角色、道具和场景拓扑寻找 coverage，不是让模型重造世界。先固定 master geography 与 180° 轴线，再从 wide、OTS、两侧 single、reaction、insert、high/low angle 等候选中探索足以比较关键决策的差异化机位；候选数量由歧义、预算和选择风险决定，只批准叙事必要的最小覆盖。

- 每个候选标相机坐标、高度、朝向、FOV、轴线侧和视线；
- 正反打保持在同一轴线侧，A 看画面右、B 看画面左；
- 只有剧情明确表现权力翻转或迷失时才设计过轴镜头，并给出可见过轴过程；
- 虚拟漫游改变机位，不改变门窗、家具、人物起始站位或主光方向。

### 实体光源、平方反比与可辨视差

“cinematic lighting”不能替代真实执行信息。只有光位、曝光或光影连续性会改变镜头结果时，才声明足以约束结果的实际发光体、位置/朝向、距主体关系、色温倾向、遮挡或阴影方向；未参与决策的字段不强填。已声明灯距变化时仍按物理关系校验：角色离灯距离改变，脸与背景亮度不能同时无因保持不变。2:1、4:1、8:1 只是可能的相对光比参考，不是固定档位或模型参数保证。

横移、推轨或环绕需要足以证明深度与运动方向的可辨视差层；下列是可选角色，不要求凑满五层：

1. 极前景遮挡（窗框、虚焦雨滴、栏杆）；
2. 前景次动作/道具；
3. 中景主表演；
4. 中后景环境运动；
5. 深远背景天际、雾或远灯。

被选层的相对位移速度应随深度递减；没有横向位移的锁定镜头不必硬塞视差层。

### 负空间与荷兰角递进

负空间必须承载叙事关系：可把人物压在边缘或非常规区域，让空墙、门口或阴影成为威胁方向，同时保留必要视线空间。荷兰角用于秩序逐步失稳；倾斜幅度从不易察觉到明确失衡的实际刻度由画面、观看端与代表镜决定，每次升级对应一次信息或权力变化，不能为“电影感”随机歪画面。恢复水平线同样要对应秩序恢复或角色重新掌控。

### 反射线索与语义色彩

关键身份若藏在眼睛反射、屏幕或镜面里，必须给足可读景别、干净高光与停留时间，并在目标画幅和压缩后复核；一闪而过的单帧不能承担揭示。

全片使用语义色彩时，先示范主色与唯一对比色各自代表的剧情状态，后续只随人物权限或处境变化而扩大；具体颜色按文化、实体光源与可访问性重设，不靠台词解释。

## 7. Physical action grammar

Describe an action as a force chain:

```text
cause or trigger
→ loaded body state / coil
→ acceleration
→ contact or peak force
→ reaction and weight transfer
→ follow-through
→ settled end state
```

Then add secondary responses:

- clothing and hair lag or snap with inertia;
- a held prop bends, compresses, swings or remains locked;
- feet create contact, friction, dust, water or debris;
- nearby objects receive vibration, shadow, reflection or displaced air;
- light and focus respond only when motivated by the movement.

“She runs” leaves the body and endpoint ambiguous. A better instruction names
the starting foot/body lean, the trigger, stride direction, carried object,
environment contact and final pose.

### State contrast

Motion reads as directed when it has two distinct registers:

```text
STATE A: held stillness / compression / hesitation
TRANSITION: visible cue, impact, decision or cut
STATE B: release / speed / expansion / aftermath
```

Include how long State A holds and what causes the transition. Constant
high-energy prose often averages into motion that is neither tense nor
explosive.

## 8. Spatial and causal locks

For a chase, journey or repeated crossing:

- choose one screen-direction axis and preserve it until a motivated reversal;
- define fixed landmarks rather than vague left/right when camera position may change;
- state which event occurs first;
- state who reaches what before whom;
- state the final owner/location/state of important props and characters.

Example:

```text
Direction lock: hero travels screen-left to screen-right in every pursuit shot.
Order lock: the storm reaches the hero before the hero reaches the case.
Object lock: the device stays clenched in the hero's right hand through the fall.
End-state lock: the pursuer stops at the cliff edge; only the hero exits frame.
```

When prose still permits multiple geometries, draw a simple blocking diagram.
Label subject positions, movement arrows, camera side, impact point and final
positions. Declare that the sketch controls geometry only; character and style
still come from their canonical references.

## 9. Continuity is a state machine

Do not hide a narrative state change inside an action paragraph.

```text
char-hero-clean-v1
→ char-hero-wet-v1
→ char-hero-torn-v1
→ char-hero-injured-v1
```

Each state that must recur needs:

- a canonical name and version;
- an approved reference image or sheet;
- the exact differences from its predecessor;
- first shot where it becomes active;
- continuity-in and continuity-out assignments;
- forbidden repair or regression.

Apply the same rule to:

- open/closed, intact/broken or lit/unlit props;
- day/night, dry/flooded or calm/damaged locations;
- clean/dirty, packed/unboxed or sealed/open products.

The shot list, not the model's memory, determines which state is active.

## 10. Test risk before volume

Rank shots before generation:

```text
identity intersection
+ number of interacting subjects
+ action/physics complexity
+ camera-path complexity
+ geometry/continuity dependency
+ exact dialogue/audio dependency
= shot risk
```

Test the highest-risk representative shot first. If it fails repeatedly, repair
the source or simplify the direction before generating all easier shots.

Recommended loop:

1. approve the source assets and storyboard panel;
2. verify the current provider schema;
3. generate the hardest shot at the cheapest useful settings;
4. classify the first visible failure;
5. change one source or one endpoint/motion clause;
6. repeat the same shot;
7. approve a known-good baseline;
8. expand to the remaining sequence;
9. use final resolution/upscale only after motion and continuity hold.

### Distortion diagnosis

| Symptom | First anchor to inspect |
|---|---|
| face/identity drift | character or identity reference; conflicting faces; current state variant |
| background warp | location reference, hidden reverse geometry and light direction |
| motion morph | start/end body states, force chain, interacting object and camera complexity |
| causal order wrong | event-order and outcome locks |
| object disappears or changes owner | prop reference plus continuity-in/out and final-state lock |
| scene cannot cut together | coverage, screen direction, incoming/outgoing states and shot duration |

Do not lengthen every part of the prompt in one retry. That destroys the
diagnostic signal.

## 11. 机位参照系与场景罗盘

- 从要展示的空间面反推相机位于其对侧；写相机位置与朝向，不写“某侧视角”这类结果词。
- 平面位移/转向与机高分开测试；换机位只改观察点，尺度、拓扑、锚点与主光仍是同一空间事实。
- 一场只维护一份空间罗盘：轴线侧、人物绑定锚物、人数、屏幕方向。每次 cut 后重述当前站位与视线，不用无参照的左右。
- 若目标模型代表镜证明一条无动作 master 能稳定本场空间，可作为平台经验采用；长度、短音与跨场尾音均不固化为通用规则。
- 先在 previz 的相机视图检查遮挡、叠压与构图，再导出该视角；俯视图只证明位置。
- 夜景裁去天空、四分之三地点板、逐镜变化景别/角度都只能按目标模型与故事目的选用，不是默认镜头配额。
- 方向必须声明屏幕参照或角色自身参照，一条指令内不混用。配色只写能由真实光源/材质承担的面积关系，不照搬个案百分比；烟雾等可见大气须有物理来源，天然环境雾按场景事实处理。

## 12. 运镜守恒量与落幅

- 情绪到运镜的映射只作可选理由；快切属于剪辑，不冒充运镜。复杂镜才下钻子时间码，其余停在镜头级。
- 推轨、变焦、环绕、跟拍、摇镜分别写各自守恒量与近义项区别：相机位移、FOV、视差、半径/高度/角速度、主体屏幕位置、机位旋转和地平线。能用正向不变量表达的，不堆否定串。
- 落幅同时完成静止 hold 与故事事件；由事件落点倒推速度曲线。
- 整场冻结相机语法、镜头性格与光位。类型词必须翻译为光的行为、相机与场景关系、构图惯例，否则删除。
- 相邻 cut 的曝光与色温须能解释为同一时间线上的变化；不能解释就补过渡或另立 scene variant。

## 13. 运镜模块化迭代：五槽子句、首帧适配与守恒量词典

把运镜写成可单独替换的模块，与场景、人物、动作分开；换首帧或换运镜时只动其中一块，才能按“每次只改一个变量”归因。

### 五槽运镜子句

`camera.movement`（或 adapter 的运镜段）按五槽写，§6 的机位/距离/焦段/叙事任务仍照常写在其他字段：

```text
运镜名 + 方向：pan left / arc right / orbit clockwise（成对运镜必须写方向，不写“pan”或“orbit”裸词）
路径：相机本体怎么动——旋转、平移、升降、绕行，还是只改焦距
速度：匀速、缓起缓停、急甩后落稳，或“匹配主体步速”
守恒量：运动过程中保持不变的量（见下表），用正向不变量写，不堆否定
落幅：停在什么构图、什么画面事件发生时停；需要可剪 hold 时写明
```

图生视频且首帧已批准时，补一句运镜只做增量：保留首帧的主体、服装、地点、光位、景深、焦段感与屏幕方向，只施加本运镜。这句不替代参考职责，只防止模型借运镜重画首帧。

### 首帧适配前提

运镜能否成立首先取决于首帧里有没有它需要的东西；不满足时先换首帧或换运镜，不靠加长 Prompt 硬推：

| 运镜 | 首帧必须已有 |
|---|---|
| tilt / pedestal / crane | 竖向延展的主体或建筑，以及上方/下方可揭示的落点 |
| pan / whip pan | 起点构图可读，且转向侧存在第二个可读目标或空间 |
| truck / slider / side tracking | 至少两层可辨深度（前景、主体、背景）以证明视差 |
| push past / pass-through | 靠近镜头的前景遮挡物、门洞、窗框或可穿越表面，位于画面中心附近 |
| arc / orbit | 主体四周有可见环境且背面/侧面已有资产锁定；否则绕到未定义面会重造身份 |
| dolly / zoom in | 推进终点的目标在首帧已可辨且未被裁出画面 |
| follow / reverse / low / vehicle tracking | 主体朝向与行进方向已确定，路线前方或后方有可读空间 |
| first-person / snorricam | POV：画面边缘可见手、臂或身体边缘作物理参照；Snorricam：主体近景居中并面向镜头 |
| infinite zoom / earth zoom out | 画面中心有明确的穿越目标；尺度转场的每一级世界需另行锁定或接受为非连续 |
| locked-off / time-lapse | 画内有能随时间变化的事物（光、云、人流），否则只剩静帧 |

### 守恒量与易混项词典

同一类运镜的近义项只在守恒量上不同；写错守恒量，模型会把一种运镜做成另一种：

| 运镜（成对方向省略） | 守恒量：过程中保持不变 | 易混项与区别 |
|---|---|---|
| locked-off / static | 机位、高度、角度、焦距与构图全不变 | 与 time-lapse 同为锁机位，后者额外压缩时间 |
| pan | 机位不动，绕竖轴旋转；地平线保持水平 | truck 是相机平移、朝向不变；pan 无视差变化 |
| whip pan | 同 pan，但中段允许动态模糊；起点与落点都要可读 | 本质是转场；落点糊掉即失败 |
| tilt | 机位不动，绕横轴俯仰；主体保持居中 | pedestal 是相机整体升降、镜头保持水平 |
| zoom（slow/fast/crash） | 机位与透视关系不变，只改 FOV；目标始终可读 | dolly 改距离与透视、前后景比例变化；zoom 不产生视差 |
| dolly in/out | 机高、镜头朝向与主体画面位置不变，只缩短/拉开距离 | 与 zoom 的区别在透视；需要“背景压缩/拉伸”时才组合 dolly zoom |
| truck | 镜头朝向不变，相机沿直线横移；场景横滑过画面 | slider 是短距离、慢速、以视差为目的的 truck |
| pedestal | 镜头保持水平且朝向不变，相机整体垂直移动 | crane 是穿过开阔空间的更大升降，可伴随视野尺度变化 |
| arc | 主体距离与机高不变，沿浅弧改变观察角 | orbit 是恒定半径的大角度或整圈绕行，背景围绕主体旋转 |
| push past | 前景物贴近镜头掠过，后方空间逐渐清晰 | pass-through 是从开口或表面正中穿入另一空间，落幅在“里面” |
| tracking | 主体在画面中的位置与大小稳定，环境流动 | follow（背后肩高）、reverse（正面后退，walk-and-talk）、side（侧面平行）、low（地面/腰下）、vehicle（随车）——相对位置是唯一区别，必须写明 |
| chase | 主体保持在画内，允许快速主动重构图 | 与 tracking 的区别是允许的重构图幅度和贴近程度 |
| handheld | 操作者身高与有机微晃；主体可读 | 强度与支撑档位见上文“四档摄影机物理寄存器”和“手持强度四档” |
| snorricam | 主体相对画面固定，背景围绕其运动 | 与 follow 不同：相机绑在身体上，主体不会离开画面中心 |
| crane / drone / helicopter | 主体或地点在升降、飞行全程可读 | drone push/pull 是空中前后飞行；helicopter 是高空大范围缓慢航线 |
| first-person | 人眼高度与可见肢体边缘；视角主体不换人 | 与 follow 不同：画面里不出现主角背影 |
| tilt-shift | 一条窄的清晰带横贯关键区域，上下虚化，微缩感保持 | 是镜头效果，可锁机也可微滑，不等于高机位航拍 |
| infinite zoom / earth zoom out | 起点目标始终居于画面中心，尺度连续扩缩 | 跨尺度时世界会被重造；属于转场，不承担连续性 |

### 运镜迭代流程

1. 先锁首帧与动作，按叙事任务从 §6 选一个主运镜，再用上面的首帧适配前提检查首帧是否支持它。
2. 失败时先读症状对照守恒量：变焦做成了推轨（透视变了）、绕行时身份漂移（背面未锁定）、摇镜带出横移（视差出现）。只改五槽中的一槽（通常是守恒量或落幅）重测。
3. 换运镜对比时，首帧、动作、时长与参数全部保持一致，只替换运镜子句；对比片的生成次数与费用仍按执行授权走，没有授权时只出子句不提交。
4. 选定运镜后把五槽子句写进 shot contract，相邻镜头继承运镜落幅而不是继承运镜名。

方法来源：[AI Camera Movements](https://aicameramovements.com/)（2026-11-04 抓取；46 条运镜卡与 prompt builder，按 Pan/Tilt、Zoom/Lens、Dolly/Track、Physical Moves、Human Camera、Drone/Crane、Specials 分组，每条均为 Camera/Movement/Speed/Framing/End 五槽，builder 把运镜、首帧上下文、场景动作、风格与“保留首帧只加运镜”的模型说明分段）。此处只吸收五槽结构、成对方向、守恒量与首帧分离，改写为中文守恒量/首帧适配表；未复制其逐条 Prompt。站点未提供分模型实测、速度曲线或叙事任务，相关判断仍以 §6 与目标模型代表镜实测为准。

## Shot-package template

```text
SHOT ID / story function:
Storyboard panel and approval:
Continuity in / out:
Active state variants:
Reference roles:
Blocking and screen direction:
Visible beat and causal outcome:
Physical action chain:
Camera placement / distance / path / direction / speed / focus / job:
Light and environment response:
Duration and audio cue after live validation:
Negative constraints:
Provider adapter fields after live discovery:
Risk score and proof gate:
```

## Acceptance checklist

- [ ] Previs fidelity matches the decision risk.
- [ ] Only decision-critical scenes were boarded.
- [ ] Every sequence retains the minimum applicable who/where/beat/emotional and inherited-state evidence; irrelevant dimensions are omitted.
- [ ] References have explicit, narrow roles.
- [ ] Panels are numbered, approved and handed into a shot list when the selected previs layer uses panels.
- [ ] Each shot has the smallest coherent camera behavior needed for its narrative job; any staged path is motivated and tested.
- [ ] Physical action has cause, force, reaction, follow-through and a final state.
- [ ] State changes use approved variants rather than prose memory.
- [ ] Screen direction, causal order, prop ownership and outcomes are locked.
- [ ] Props, weapons, vehicles and technology match the approved script's world, era and neighbouring shots; nothing is filled in from default association.
- [ ] Ambiguous geometry uses a labeled blocking reference.
- [ ] The highest-risk shot passed before batch generation.
- [ ] Runtime limits and provider syntax were verified live.

## Common failures

1. Boarding every line while leaving the hardest visual beat vague.
2. Treating a storyboard as attractive images rather than an edit/production plan.
3. Prompting a single still when the board needs a sequence arc.
4. Combining several primary camera paths in one short shot.
5. Naming a move without placement, speed, focus or narrative job.
6. Using action categories without body endpoints or force response.
7. Asking prose to remember torn wardrobe, damage or prop-state changes.
8. Describing spatial geometry with more words after the relation is already ambiguous.
9. Generating easy shots first and discovering the core interaction cannot hold.
10. Fixing face, background and motion distortion in the same uncontrolled retry.
11. Writing a paired move without direction (“pan”, “orbit”) or confusing near-synonyms whose invariants differ (zoom vs dolly, pan vs truck, tilt vs pedestal); see §13.
12. Choosing a move the first frame cannot support (push past with no foreground, orbit around an unlocked back side); see §13 首帧适配前提.
