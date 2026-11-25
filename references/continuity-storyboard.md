# Continuity, Assets and Storyboard

## 资产不是附件，是连续性的真源

多镜头项目先建立 canonical asset IDs，再映射到 provider 字段。聊天记忆、文件名和旧 `@` 标签不能决定当前权威版本。

建议类型：

- character
- wardrobe/state variant
- location
- product
- prop
- brand kit
- UI
- style
- source video
- first/end frame

每项记录：稳定 ID、名称、版本、源路径/哈希、批准状态、用途、provider reference、失败时 correction source。

## 角色定型

项目级角色/场景/风格圣经、服化道时间线与轻重分级见 [continuity-bibles.md](continuity-bibles.md)；本文件只维护资产真源、分镜和逐镜状态交接，避免重复定义。

本节只定义“能否作为连续性真源”的最低门；身份/服装依赖、最小充分视图、中性灰底板与中性唇起始帧见 [keyframe-assets.md](keyframe-assets.md)，两处不重复维护。

最低可读性门：

- 只覆盖 shot plan 真会辨认的视角、比例、服装结构与身份细节；
- 每个所需视图有足够像素，光线不会把环境色或戏剧阴影烘焙进身份真源；
- 同一角色的身份、肤色、体型、比例与当前服装 variant 相容；
- 不用含多个冲突脸的 sheet 充当身份锚；
- 一次性背影、不可辨认群众或单一正面近景允许使用更小的 view set。

服装、伤口、污渍、携带道具等反复状态要生成独立 variant，不靠 prose 记住。视图不足时按真实下游缺口扩建，不按固定 panel 数补齐。

## 产品与道具

先写 `required_views / downstream_shots / minimum_pixel_readability`。正面、侧面、3/4、顶部、比例、材料、重复细节与 exploded view 都只是候选 palette；只生成能消除当前运动、遮挡、比例或结构歧义的最小充分视图。

## 地点

地点资料只证明当前镜头会用到的 geography。wide、3/4、入口/出口、主体移动路径、关键空间关系和主光方向都是候选职责；按下游镜头选择最小充分集合。需要空间证明时，漂亮局部图不能代替可执行 geography。

## Style lock

把身份/产品/地点和风格分离：

- asset sheet 锁事实；
- style reference 锁色板、媒介、纹理和光线；
- shot prompt 只写当前动作。

长项目用一段全局 style/continuity prefix，加独立命名镜头（1a、1b、2a），不要把整份风格说明复制到每镜。

场景级视觉基线先锁类型语汇、主光逻辑与色彩关系；焦段或机位可以因镜头职责改变，但每次偏离都要有可见动机，不能让默认值逐镜漂移。

## 最小充分分镜

### 从剧本到镜头的交接核对

只在需要分镜时，为本次覆盖的剧本动作或对白设稳定 `beat_id`，并记录源剧本版本；剧本已按 [script-writing-craft.md](script-writing-craft.md) 编号（如 `[S3-B2]`）时直接沿用，不另起一套。镜头表补 `source_beats / advances_beats / story_time_id`：前者指向本镜表现的原文，第二项只列真正推进的新事件，第三项沿用现有 coverage 时间标记。动作与对白不能在转成分镜时被静默删改；逐镜 JSON 写好后用 `scripts/check_script_coverage.py` 对账，规则见 [prompt-compiler.md](prompt-compiler.md#剧本锁编译)。

同一事件的全景、反应镜和正反打可以共用 `source_beats` 与 `story_time_id`；只在一处登记事件推进，不让人物在剪辑里重复完成同一个动作。需要覆盖的剧情点都有去向，刻意留在画外、声音或剪辑省略中的点注明处理，不为“覆盖完整”硬加无作用镜头。

对白逐字回对说话者、否定词、称谓、数字与关键信息；用实际朗读或已生成音频估计可读窗口，装不下就调表演、拆块或回改剧本，不能为凑时长擅删台词。配音编号直接回指镜号和源对白。

改稿时先点名变动的 `beat_id`，重查引用它的镜头与其连续性后继；无关的已通过镜头保留。接受生成中提前发生的剧情动作时，把它记入已完成事件并重排后续，见[逐镜恢复与重拍](sequence-resume.md)。

方法来源：shuohao 的[剧本节拍与镜头对账](https://github.com/eternityspring/shuohao-skills/blob/4322897e6d2bdaf66365534fd40194360c75a85f/skills/novel-storyboard/SKILL.md#L46-L55)，按本 Skill 的 coverage 与开放形式规则改写；不采用上游固定分段时长、切镜频率或特定模型对白标记。

按风险选择：

- storyboard：构图、位置、光线；
- animatic：时序、动作、剪辑节奏；
- 3D previs：只有精确镜头/身体/空间几何会改变执行时才需要。

当复杂运镜、动作或轴线让 approved previz 成为必要表示时，它是摄影轨迹、速度/缓动、机高、角度、构图、blocking 与时序的权威；静帧仍可锁身份、服装和材质，但冲突时不得覆盖这些相机/时间维度。若 previz 的透视、分辨率、人物-场景融合或空间可读性不足，就降级/回修到能证明执行的 storyboard 或 animatic；身份仍走独立资产 QA，不拿 previz 冒充。

不要为每句对白画 panel。优先：动作、情绪复杂 coverage、reveals、转场、屏幕方向、continuity state change。

每个 sequence brief 记录稳定 ID 与叙事/可见任务；who、where、visible beats、情绪起止、references、screen direction、continuity in/out 只保留会改变当前规划、生成或交接的适用维度，不为格式强填。

## Shot contract

每个镜头的通用核心是稳定标识、叙事/可见任务、状态变化（如有）、生成状态与可执行 QC。其余字段按 `production_class / block_mode / declared risks` 保留；不存在的 panel、coverage、reference、轴线或 handoff 不得伪造：

```text
scene_id / sequence_id / shot_id
story_time_id / coverage_group (when applicable)
story function
approved panel (when it is the selected planning representation)
continuity in (when inherited state exists)
temporal_relation / handoff_strategy
visible action
camera job
reference roles (when references are used)
continuity out (when a downstream block must inherit state)
risk class
provider/QC status
```

## 状态交接

稳定连续性不是“上一条视频名”，而是通过 QC 的结束状态：

```text
人物位置与朝向
身体姿势和动作余势
表情/呼吸
服装、伤口、污渍
左右手道具位置
产品状态
环境与主光
镜头高度、景别和运动尾势
可用末帧路径/哈希
```

生成下一段前从真实结果更新，不为原脚本硬续。失败结果不能成为下一段源头。

每个相邻片段先标一种 `temporal_relation`：

### `continuous_time`

从实际 QC-passed out 继续：保留人物/道具位置、动作方向、速度、重心、表情/呼吸、声场与镜头尾势；需要时选稳定 relay frame。不得重复已经完成的动作，也不为制造 coverage 强制换机位。

### `editorial_cut`

继承身份、所有者、物体状态、知情等事实，但允许因剪辑意图改变角度、景别或时间。明确使用 match-on-action、视线、屏幕方向、遮挡、cutaway、构图或声音桥中的实际策略；不要求相似尾帧，也不把 relay frame 当硬门。

### Covered-scene overlap

同一场景事件的 master、OTS、reaction 或 detail coverage 可共享 `story_time_id / coverage_group`。这些 take 表示同一故事时刻，不按拍摄/生成顺序重复推进事件或互相覆盖 state out；装配时选择一致的表演阶段与物理事实。

## Cut 规则

- 每次 cut 同时重新锚定人物位置、朝向、道具和空间；
- 连续追踪复杂度服从 provider 能力、人物接触/遮挡、身份区分与代表镜结果；必要时拆分 blocking 或 coverage，不使用固定人数阈值；
- 出画后不要在同镜头无解释回归；
- 镜头外发生的状态默认不存在；
- 已标为画外的对白保持画外；若叙事必须看见说话者，应回到分镜重设计，不在生成时临时追加反打、近景或转向。
- 反射面会增加身份和空间歧义，只有叙事必要时使用；
- whip pan 要定义实际主体、方向、持续时间、落点景别与相容 screen geometry；对白可在落稳后开始，也可因明确剪辑/声音意图使用 pre-lap，但要验收可懂度与落点关系。

## 测试最危险镜头

批量生成前先测试最高风险的代表镜头：

- 身份/脸；
- 地点/空间；
- 产品几何/标签；
- 动作物理；
- 因果顺序；
- 连续性状态。

失败时回到最早的对应真源修复，再跑同一测试。一次只改一个 source 或 motion clause。

## 组级预演与可见节拍

- 首尾帧接力解决镜间衔接；多人、多动作、多镜场次先做组级预演，把关键板分别注入对应片段，解决整组站位、方向与动作统一。两者不互相替代。
- 分镜锁意图、共同身份/地点和节拍时长；板证明“看起来怎样”，shot list 说明“怎样执行”，并保留镜头目的与必要连续性。
- 格数按可见节拍和最低像素需要决定；单批生成上限查 live schema，超出就拆批，不压掉节拍凑额度。
- 粗场景描述可用于提前探视觉，但剧本张力门、承诺与标题仍须通过。
- 需要空间定位时，只要求一种能独立指定各角色相对位置的表示；具体工具留给 adapter。姿势与支撑物必须成对成立，不固化来源未证明的操作先后。
- 多人对白预演可用固定座位与唯一代理色绑定角色，供跨机位核对站位和遮挡；代理色只是制作期身份键，不传给成片外观。

## 切点运动与首帧状态

- 中途要出现的物件优先从首帧已在场状态开始，再让它改变状态；无可见进入路径的凭空出现列为高风险。
- 相邻镜至少让摄影机运动或主体位移中的一项保持方向连续；换方向必须由转身、打断或视点转移等可见事件解释。
- 可用动作未完成的中间态进入下一镜，让两段读成一条连续运动；不为追求连贯而继承失败 take。

## Approved 与 superseded

生成图/视频默认 `candidate`。只有按下游用途通过才变 `approved`；错误模型、错误角色、错误产品或旧版本标为 `rejected/superseded`，不得再喂给下游。

详细摄影与分镜规则见 `storyboard-camera-direction.md`。
